"""sig-release releases/release-1.N/exceptions.yaml → ExceptionRequest list."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import yaml

_PHASES = {"enhancementFreeze": "enhancements_freeze", "codeFreeze": "code_freeze"}


@dataclass(frozen=True)
class ExceptionRequest:
    issue: int
    phase: str
    status: str
    date_requested: date | None


def _date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def parse_exceptions_yaml(text: str) -> list[ExceptionRequest]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        # Pre-v1.24 exceptions.yaml files predate this enhancementFreeze/codeFreeze
        # schema and occasionally contain outright invalid YAML (stray trailing
        # commas, stray zero-width characters). Out of schema either way: no rows.
        return []
    if not isinstance(data, dict):
        # Same pre-v1.24 files: a bare top-level list with no phase separation, not
        # this schema's enhancementFreeze/codeFreeze mapping. No rows, not a crash.
        return []
    out = []
    for key, phase in _PHASES.items():
        for r in data.get(key) or []:
            try:
                issue = int(r.get("issue"))
            except (TypeError, ValueError):
                continue
            out.append(ExceptionRequest(issue, phase, str(r.get("status") or "").strip().lower(), _date(r.get("date_requested"))))
    return out


def load_exceptions(sig_release_repo: Path) -> dict[str, list[ExceptionRequest]]:
    out = {}
    for p in sorted((sig_release_repo / "releases").glob("release-1.*/exceptions.yaml")):
        minor = p.parent.name.split(".")[1]
        out[f"k8s:v1.{minor}"] = parse_exceptions_yaml(p.read_text())
    return out
