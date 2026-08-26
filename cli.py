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


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spike").set_defaults(fn=cmd_spike)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
