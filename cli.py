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
    from backtest.metrics import CENSOR_DAYS, by_org, by_stage, rows_frame, signal_metrics, uncensored_milestones
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
    # Right-censoring: milestones released too recently for their slips to have surfaced.
    # Their rows deflate the base rate, which inflates every lift measured against it.
    open_ids = {m.id for m in ms} - {m.id for m in uncensored_milestones(ms, days=args.censor_days)}
    censored = [r for r in rows if r.milestone_id not in open_ids]
    # Count only milestones that actually carry rows: the calendar holds v1.38-v1.60
    # placeholders with no release date, which are "open" but empty and would inflate this.
    dropped_ms = sorted({r.milestone_id for r in rows} & open_ids)
    if dropped_ms:
        print(f"censoring: {len(rows) - len(censored)} rows dropped from the uncensored view "
              f"({', '.join(dropped_ms)} released < {args.censor_days} days ago)")
    by_id = {m.id: m for m in ms}
    rows_frame(rows).to_csv(out / "rows.csv", index=False)

    import collections
    dist = collections.Counter(r.outcome for r in rows)
    print(f"{len(rows)} rows | " + " ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))

    for cut, sig_name, org_name, stage_name in (
            ("evidenced", "signals.csv", "by_org.csv", "by_stage.csv"),
            ("full", "signals_full.csv", "by_org_full.csv", "by_stage_full.csv")):
        table = signal_metrics(rows, by_id, L=DEFAULT_PARAMS["L"], cut=cut)
        table.to_csv(out / sig_name, index=False)
        # The decision-point view, published beside the designed metric rather than
        # instead of it. findings.md's headline is a freeze-point number; before this it
        # came from an uncommitted one-off computation and could not be reproduced.
        freeze = signal_metrics(rows, by_id, L=DEFAULT_PARAMS["L"], cut=cut, evaluation="at_freeze")
        freeze.to_csv(out / sig_name.replace(".csv", "_at_freeze.csv"), index=False)
        # Same tables with the censored tail removed. Smaller sample, unbiased denominator.
        signal_metrics(censored, by_id, L=DEFAULT_PARAMS["L"], cut=cut).to_csv(
            out / sig_name.replace(".csv", "_uncensored.csv"), index=False)
        signal_metrics(censored, by_id, L=DEFAULT_PARAMS["L"], cut=cut, evaluation="at_freeze").to_csv(
            out / sig_name.replace(".csv", "_at_freeze_uncensored.csv"), index=False)
        by_org(rows, cut=cut).to_csv(out / org_name, index=False)
        stages = by_stage(rows, cut=cut)
        stages.to_csv(out / stage_name, index=False)
        print(f"\n--- {cut} cut, first-fired ---")
        print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        print(f"\n--- {cut} cut, at freeze ---")
        cols = ["signal", "fired", "precision", "recall", "lift", "lift_ci_lo", "lift_ci_hi"]
        print(freeze[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        print(stages.to_string(index=False, float_format=lambda x: f"{x:.3f}"))



def cmd_register(args) -> None:
    """Spec §9: every signal on snapshot(now), split by measured lead class."""
    from datetime import datetime, timezone
    import pandas as pd
    from adapters.k8s.config import CONFIG
    from backtest.register import build_register, format_register
    from core.replay import snapshot
    from core.store import Store
    from signals import SIGNALS
    from signals.base import Context, DEFAULT_PARAMS, targets_at
    metrics_path = OUT / "k8s" / ("signals.csv" if args.cut == "evidenced" else "signals_full.csv")
    if not metrics_path.exists():
        raise SystemExit(f"no backtest for this corpus: {metrics_path} is missing. Run `backtest` first.")
    s = Store(CACHE / "store.sqlite")
    ms, orgs, evs = s.load_milestones("k8s"), s.load_org_units("k8s"), s.load_events("k8s")
    by_id = {m.id: m for m in ms}
    m = by_id.get(args.milestone)
    if m is None:
        raise SystemExit(f"unknown milestone {args.milestone!r}")
    now = datetime.now(timezone.utc)
    states = snapshot(evs, now)
    # Same calendar-visibility filter as the backtest: a live signal must not read a
    # later milestone's dates either.
    visible = {mid: x for mid, x in by_id.items() if x.ordinal <= m.ordinal}
    ctx = Context(now, m, visible, orgs, CONFIG, dict(DEFAULT_PARAMS),
                  [e for e in evs if e.kind == "outcome" and e.ts <= now])
    firing: dict[tuple[str, str], list[str]] = {}
    for iid, st in states.items():
        for stage in targets_at(st, m.id):
            firing[(iid, stage)] = []
    for name, fn in SIGNALS.items():
        for key in fn(states, ctx):
            if key in firing:
                firing[key].append(name)
    print(format_register(build_register(firing, pd.read_csv(metrics_path), m, cut=args.cut), m, cut=args.cut))


def cmd_sensitivity(args) -> None:
    """Spec §8's grid: vary each a priori parameter, report, do not tune on it."""
    from adapters.k8s.config import CONFIG
    from backtest.run import run_backtest
    from backtest.sensitivity import DEFAULT_GRID, sweep
    from core.store import Store
    from signals import SIGNALS
    from signals.base import DEFAULT_PARAMS
    s = Store(CACHE / "store.sqlite")
    ms, orgs, evs = s.load_milestones("k8s"), s.load_org_units("k8s"), s.load_events("k8s")
    if args.min_minor:
        ms = [m for m in ms if m.ordinal >= args.min_minor or not m.is_scheduled]
    by_id = {m.id: m for m in ms}
    runner = lambda params: run_backtest(evs, ms, orgs, CONFIG, SIGNALS, params)
    out = OUT / "k8s"; out.mkdir(parents=True, exist_ok=True)
    frames = []
    for cut in ("evidenced", "full"):
        df = sweep(runner, by_id, dict(DEFAULT_PARAMS), DEFAULT_GRID, cut=cut)
        frames.append(df)
        print(f"\n--- {cut} cut ---")
        print(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    import pandas as pd
    pd.concat(frames).to_csv(out / "sensitivity.csv", index=False)
    print(f"\nwrote {out / 'sensitivity.csv'}")


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

    # Completeness guard. GitHub paginates at 100; a timeline of exactly the page size
    # is the signature of an unfollowed `Link: rel="next"`. That defect shipped once --
    # 475 of 644 timelines truncated at 100, hiding a median 64% of each issue's life --
    # and it was invisible because every downstream check compared the corpus to itself.
    suspicious = [n for n, r in recs.items() if len(r.get("timeline") or []) % 100 == 0
                  and r.get("timeline")]
    if suspicious:
        print(f"  WARNING: {len(suspicious)} timeline(s) are an exact multiple of the page "
              f"size: {sorted(suspicious)[:10]}{' ...' if len(suspicious) > 10 else ''}")
        print(f"  That can be coincidence, but it is also what an unfollowed next-link "
              f"looks like. Verify before trusting evidence coverage.")
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
    rp = sub.add_parser("register")
    rp.add_argument("--milestone", required=True, help="milestone id, e.g. k8s:v1.34")
    rp.add_argument("--cut", default="evidenced", choices=("evidenced", "full"))
    rp.set_defaults(fn=cmd_register)
    sp = sub.add_parser("sensitivity")
    sp.add_argument("--min-minor", type=int, default=0)
    sp.set_defaults(fn=cmd_sensitivity)
    bp = sub.add_parser("backtest")
    bp.add_argument("--censor-days", type=int, default=180,
                    help="exclude milestones released fewer than this many days ago from the "
                         "uncensored tables (default 180, ~1.5 release cycles)")
    # Default 0 = every scheduled milestone (v1.19-v1.37), which is what the committed
    # out/k8s/*.csv were produced from -- a bare `cli.py backtest` must reproduce them.
    # `--min-minor N` is the opt-in "recent cycles only" cut (see docs/sprint-1-notes.md).
    bp.add_argument("--min-minor", type=int, default=0)
    bp.set_defaults(fn=cmd_backtest)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
