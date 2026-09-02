"""Survey candidate GitHub repos for the properties this backtest actually needs.

The README claims a general pipeline with Kubernetes as the first corpus. That claim is
untested, and picking corpus #2 by reputation is how you spend a week writing an adapter
for a repo that cannot answer the question. This measures the candidates first.

**The decisive property is retargeting.** A `slipped` outcome exists only because work is
moved from one release to a later one and leaves a timestamped trace. Everything else can
be worked around; this cannot. A repo where issues are milestoned once and never moved has
no positive class, and an adapter for it would produce a backtest with nothing to predict.

Five things are measured per repo, in rough order of how fatal their absence is:

1. `retarget_rate`  -- share of sampled milestoned issues that moved between milestones.
2. `milestone_cov`  -- share of issues carrying a milestone at all.
3. `dated_ms`       -- milestones with a `due_on`, i.e. an actual release calendar.
4. `org_families`   -- label prefixes that look like team/area ownership (the SIG analogue).
5. `scope_labels`   -- label families that look like a release-team scope decision. This is
                       the S0 control analogue, and its absence means the new corpus cannot
                       reproduce the one comparison this project measures everything against.

Reads `GITHUB_TOKEN` from the environment. Unauthenticated runs work but are capped at 60
requests/hour, which is roughly four repos.

    python tools/corpus_survey.py --out out/corpus_survey.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"

# Ownership label prefixes vary by project; these are the shapes seen in practice.
ORG_PREFIXES = ("sig", "area", "team", "wg", "component", "feature", "topic")
# Labels that read as a release-team scope decision rather than a description of the work.
SCOPE_HINTS = ("tracked", "milestone", "planned", "committed", "accepted", "triage", "release")

CANDIDATES = [
    # The reference row. This corpus is known to work -- the whole backtest runs on it --
    # so it calibrates the survey: any candidate should be read against how kubernetes
    # itself scores, not against an absolute threshold. Note the enhancements repo, not
    # kubernetes/kubernetes: the commitment artifact lives with the KEPs.
    "kubernetes/enhancements",
    # Kubernetes-ecosystem: structurally closest, weakest as a generalisation test.
    "kubernetes-sigs/cluster-api", "kubernetes-sigs/kubespray", "kubernetes/kubernetes",
    "openshift/enhancements", "istio/istio", "knative/serving", "cilium/cilium",
    "containerd/containerd", "etcd-io/etcd", "argoproj/argo-cd", "grpc/grpc",
    # CNCF-adjacent, independent governance.
    "envoyproxy/envoy", "prometheus/prometheus", "grafana/grafana", "hashicorp/terraform",
    "helm/helm", "open-telemetry/opentelemetry-collector", "vitessio/vitess",
    # Company-run products: genuinely different governance, the strongest generalisation test.
    "microsoft/vscode", "microsoft/TypeScript", "elastic/kibana", "elastic/elasticsearch",
    "golang/go", "rust-lang/rust", "python/cpython", "nodejs/node", "denoland/deno",
    "JetBrains/kotlin", "dotnet/runtime", "dotnet/aspnetcore", "flutter/flutter",
    "angular/angular", "facebook/react", "vuejs/core", "sveltejs/svelte",
    "apache/airflow", "apache/spark", "ansible/ansible", "saltstack/salt", "godotengine/godot",
]


class Client:
    def __init__(self, token: str | None, sleep=time.sleep):
        self.token, self._sleep, self.calls = token, sleep, 0

    def get(self, url: str):
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "program-risk-backtest-survey",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self.calls += 1
                    return json.loads(r.read()), dict(r.headers)
            except urllib.error.HTTPError as e:
                self.calls += 1
                if e.code in (403, 429):
                    wait = int(e.headers.get("Retry-After") or 2 ** attempt)
                    self._sleep(min(wait, 60))
                    continue
                return None, dict(e.headers)
            except Exception:
                self._sleep(2 ** attempt)
        return None, {}


def label_families(issues) -> collections.Counter:
    fams = collections.Counter()
    for i in issues:
        for l in i.get("labels") or []:
            name = str(l.get("name", ""))
            head = name.split("/")[0].split(":")[0].split("-")[0].strip().lower()
            if head:
                fams[head] += 1
    return fams


def survey_repo(client: Client, repo: str, timeline_sample: int = 10) -> dict:
    """One row of the survey. Returns partial data rather than raising on a 404."""
    row = {"repo": repo, "error": None}
    meta, _ = client.get(f"{API}/repos/{repo}")
    if meta is None:
        # `None` is a fetch failure; an empty dict is a valid-but-sparse response and must
        # not be mistaken for one, or a real repo gets dropped from the survey silently.
        row["error"] = "repo unreadable"
        row["verdict"] = verdict(row)
        return row
    row["stars"] = meta.get("stargazers_count")

    ms, _ = client.get(f"{API}/repos/{repo}/milestones?state=all&per_page=100")
    ms = ms or []
    row["milestones"] = len(ms)
    row["dated_ms"] = sum(1 for m in ms if m.get("due_on"))

    # Coverage from a general sample. PRs are excluded: a busy repo's recent page is
    # mostly pull requests, and counting them collapses the ratio toward zero.
    issues, _ = client.get(f"{API}/repos/{repo}/issues?state=all&per_page=100&sort=updated")
    issues = [i for i in (issues or []) if "pull_request" not in i]
    row["issues_sampled"] = len(issues)
    row["milestone_cov"] = (sum(1 for i in issues if i.get("milestone")) / len(issues)
                            if issues else 0.0)

    # Retargeting is measured on issues that ACTUALLY CARRY a milestone, fetched with
    # `milestone=*`. Reusing the recent sample was wrong: `sort=updated` skews to new and
    # untriaged issues, so a project that milestones its planned work heavily can still
    # show zero milestoned issues on a recent page -- which is how the first run of this
    # survey rejected repos holding 39 dated release milestones.
    milestoned, _ = client.get(
        f"{API}/repos/{repo}/issues?state=all&per_page=100&sort=updated&milestone=*")
    milestoned = [i for i in (milestoned or []) if "pull_request" not in i and i.get("milestone")]
    row["milestoned_found"] = len(milestoned)

    fams = label_families(issues)
    row["org_families"] = ",".join(k for k, _ in fams.most_common(20) if k in ORG_PREFIXES) or ""
    row["scope_labels"] = ",".join(k for k, _ in fams.most_common(30)
                                   if any(h in k for h in SCOPE_HINTS)) or ""

    moved = checked = 0
    for i in milestoned[:timeline_sample]:
        tl, _ = client.get(f"{API}/repos/{repo}/issues/{i['number']}/timeline?per_page=100")
        if tl is None:
            continue
        checked += 1
        seen = [e for e in tl if isinstance(e, dict) and e.get("event") == "milestoned"]
        if len(seen) > 1:
            moved += 1
    row["timelines_checked"] = checked
    row["retarget_rate"] = moved / checked if checked else None
    row["verdict"] = verdict(row)
    return row


def verdict(row: dict) -> str:
    """Plain-language read. Retargeting is disqualifying in a way nothing else is."""
    if row.get("error"):
        return "unreadable"
    if not row.get("timelines_checked"):
        return ("no milestoned issues anywhere" if not row.get("milestoned_found")
                else "milestoned issues found but timelines unreadable")
    rt = row.get("retarget_rate") or 0.0
    if rt == 0:
        return "REJECT — no retargeting observed, so no positive class"
    notes = []
    if not row.get("dated_ms"):
        # NOT a downgrade. Kubernetes' own calendar is built from the sig-release repo into
        # adapters/k8s/calendar.yaml, not read from GitHub milestones -- so a candidate
        # with a documented public release schedule can supply one the same way. Scoring
        # this as disqualifying rejected golang/go, which has 51k milestoned issues and a
        # more regular release cadence than Kubernetes.
        notes.append("calendar needed from outside GitHub")
    if not row.get("org_families"):
        notes.append("no org units, so cross_org and org_overcommitted cannot run")
    if not row.get("scope_labels"):
        notes.append("no scope label, so no S0 control")
    if row.get("milestoned_found", 0) < 20:
        notes.append("thin milestoned population")
    grade = "STRONG" if not notes else ("viable" if len(notes) < 3 else "weak")
    return grade + (" — " + "; ".join(notes) if notes else " — retargets, calendar, org units and a scope label")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="out/corpus_survey.csv")
    ap.add_argument("--repos", nargs="*", default=CANDIDATES)
    ap.add_argument("--timelines", type=int, default=10, help="timelines sampled per repo")
    args = ap.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"{'authenticated' if token else 'UNAUTHENTICATED (60 req/hr, ~4 repos)'}; "
          f"{len(args.repos)} candidates", file=sys.stderr)
    client = Client(token)

    rows = []
    for repo in args.repos:
        row = survey_repo(client, repo, args.timelines)
        rows.append(row)
        rt = row.get("retarget_rate")
        print(f"  {repo:40s} cov={row.get('milestone_cov') or 0:.2f} "
              f"ms={row.get('milestoned_found', 0):>3d} "
              f"retarget={'--' if rt is None else f'{rt:.2f}'}  {row.get('verdict')}", file=sys.stderr)

    cols = ["repo", "stars", "milestones", "dated_ms", "issues_sampled", "milestone_cov",
            "milestoned_found", "timelines_checked", "retarget_rate", "org_families",
            "scope_labels", "verdict", "error"]
    import pathlib
    out = pathlib.Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out} ({client.calls} API calls)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
