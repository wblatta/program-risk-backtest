"""Entry point: spike | fetch | build | backtest."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CACHE = Path("cache")
OUT = Path("out")


def cmd_spike(args) -> None:
    from adapters.k8s.fetch import clone_or_update
    from adapters.k8s.config import REPOS
    from adapters.k8s.kep_yaml import parse_kep_yaml, KepParseError
    repo = CACHE / "k8s" / "enhancements"
    clone_or_update(REPOS["enhancements"], repo)
    rows, errors = [], []
    for path in sorted(repo.glob("keps/sig-*/*/kep.yaml")):
        try:
            m = parse_kep_yaml(path.read_text())
        except KepParseError as e:
            errors.append({"path": str(path.relative_to(repo)), "error": str(e)})
            continue
        rows.append({"dir": path.parent.name, **m.__dict__})
    out = OUT / "k8s" / "spike.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"keps": rows, "errors": errors}, indent=1, default=str))
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"{len(rows)} KEPs parsed, {len(errors)} errors -> {out}")
    print("by status:", dict(sorted(by_status.items(), key=lambda kv: -kv[1])))


def cmd_fetch(args) -> None:
    from adapters.k8s.adapter import K8sAdapter
    K8sAdapter(CACHE).fetch()
    print("fetched into", CACHE / "k8s")


def cmd_build(args) -> None:
    from adapters.k8s.adapter import K8sAdapter
    from core.store import Store
    a = K8sAdapter(CACHE)
    s = Store(CACHE / "store.sqlite")
    s.init_schema()
    items, orgs, ms, evs = a.work_items(), a.org_units(), a.milestones(), a.events()
    s.replace_corpus("k8s", items, orgs, ms, evs)
    # `today` (UTC) decides which milestones are labelable at all -- outcome_events skips
    # any milestone whose release is still in the future -- so it is part of what produced
    # the committed out/k8s/*.csv and is printed rather than left implicit.
    print(f"today (UTC): {a.today.isoformat()}")
    kinds: dict[str, int] = {}
    for e in evs:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    print(f"{len(items)} items, {len(orgs)} org units, {sum(m.is_scheduled for m in ms)} scheduled milestones, {len(evs)} events")
    print("by kind:", kinds)

    # Ruling 2: every excluded/dropped KEP directory, counted and printed --
    # nothing lost silently.
    print(f"excluded {len(a.excluded_zero_dirs)} kep-number-0 dirs (process docs, not enhancements):")
    for d in a.excluded_zero_dirs:
        print("  -", d)
    print(f"dropped {len(a.dropped_collision_dirs)} colliding dirs (kep-number shared with another directory):")
    for dropped, kept in a.dropped_collision_dirs:
        print(f"  - {dropped}  (kept {kept})")
    print(f"filtered {a.unknown_milestone_targets} target_set events referencing an unknown milestone")

    # Ruling 4: every exceptions.yaml that exists but yielded nothing, and why.
    print(f"skipped {len(a.skipped_exceptions)} exceptions.yaml files that yielded no requests:")
    for sk in a.skipped_exceptions:
        print(f"  - {sk.path} ({sk.milestone_id}): {sk.reason}")


def cmd_backtest(args) -> None:
    from adapters.k8s.config import CONFIG
    from backtest.metrics import by_org, rows_frame, signal_metrics
    from backtest.run import run_backtest
    from core.store import Store
    from signals import SIGNALS
    from signals.base import DEFAULT_PARAMS
    s = Store(CACHE / "store.sqlite")
    ms, orgs, evs = s.load_milestones("k8s"), s.load_org_units("k8s"), s.load_events("k8s")
    if args.min_minor:
        ms = [m for m in ms if m.ordinal >= args.min_minor or not m.is_scheduled]
    rows = run_backtest(evs, ms, orgs, CONFIG, SIGNALS, dict(DEFAULT_PARAMS))
    out = OUT / "k8s"; out.mkdir(parents=True, exist_ok=True)
    by_id = {m.id: m for m in ms}
    rows_frame(rows).to_csv(out / "rows.csv", index=False)

    import collections
    dist = collections.Counter(r.outcome for r in rows)
    print(f"{len(rows)} rows | " + " ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))

    for cut, sig_name, org_name in (("evidenced", "signals.csv", "by_org.csv"),
                                    ("full", "signals_full.csv", "by_org_full.csv")):
        table = signal_metrics(rows, by_id, L=DEFAULT_PARAMS["L"], cut=cut)
        table.to_csv(out / sig_name, index=False)
        by_org(rows, cut=cut).to_csv(out / org_name, index=False)
        print(f"\n--- {cut} cut ---")
        print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))



def cmd_fetch_issues(args) -> None:
    """Fetch KEP tracking issues + label timelines into cache/k8s/github/.

    Needs a token: unauthenticated GitHub allows 60 requests/hour and a full pass is
    ~1,300, so an unauthenticated run would take most of a day. With a token the budget
    is 5,000/hour and a cold pass fits inside one hour; re-runs read from disk.
    """
    import os
    from adapters.k8s.github import GitHubClient
    from adapters.k8s.tracking import fetch_tracking
    from adapters.k8s.adapter import K8sAdapter

    token = os.environ.get(args.token_env)
    if not token:
        print(f"No token in ${args.token_env}. Unauthenticated is 60 req/hour; a full pass needs ~1300.")
        print(f"  export {args.token_env}=<a token with public_repo scope>   then re-run")
        if not args.allow_unauthenticated:
            return

    numbers = sorted({int(i.rsplit("-", 1)[1]) for _, i in K8sAdapter(CACHE)._kep_dirs()})
    if args.limit:
        numbers = numbers[:args.limit]
    client = GitHubClient(token=token, reserve=args.reserve)
    dest = CACHE / "k8s" / "github"
    print(f"fetching {len(numbers)} tracking issues into {dest} ...")
    recs, stopped = fetch_tracking(dest, numbers, client)
    print(f"  {len(recs)}/{len(numbers)} complete | requests={client.requests_made} "
          f"(304s={client.not_modified}) | budget remaining={client.remaining}")
    if stopped:
        reset = client.reset_at.isoformat() if client.reset_at else "unknown"
        print(f"  stopped early to stay clear of the rate limit; budget resets at {reset}.")
        print(f"  everything fetched is on disk -- re-run to resume where it left off.")


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spike").set_defaults(fn=cmd_spike)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    fi = sub.add_parser("fetch-issues")
    fi.add_argument("--limit", type=int, default=0, help="only the first N KEPs")
    fi.add_argument("--token-env", default="GITHUB_TOKEN")
    fi.add_argument("--reserve", type=int, default=50, help="stop with this much budget left")
    fi.add_argument("--allow-unauthenticated", action="store_true")
    fi.set_defaults(fn=cmd_fetch_issues)
    bp = sub.add_parser("backtest")
    # Default 0 = every scheduled milestone (v1.19-v1.37), which is what the committed
    # out/k8s/*.csv were produced from -- a bare `cli.py backtest` must reproduce them.
    # `--min-minor N` is the opt-in "recent cycles only" cut (see docs/sprint-1-notes.md).
    bp.add_argument("--min-minor", type=int, default=0)
    bp.set_defaults(fn=cmd_backtest)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
