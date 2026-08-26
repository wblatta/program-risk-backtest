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


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spike").set_defaults(fn=cmd_spike)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
