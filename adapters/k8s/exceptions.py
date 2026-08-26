"""sig-release releases/release-1.N/exceptions.yaml → ExceptionRequest list."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import yaml

_PHASES = {"enhancementFreeze": "enhancements_freeze", "codeFreeze": "code_freeze"}

# Legacy pre-v1.24 exceptions.yaml files (real examples: release-1.10, -1.11, -1.16,
# -1.17, -1.21, -1.22, -1.23) predate the enhancementFreeze/codeFreeze schema above:
# the document is a single flat top-level list, and which freeze phase a request
# belongs to is recorded only in a free-text comment (e.g. "# Enhancements Freeze
# Exceptions requested in 1.21"), never as structured data. outcome_events keys
# exceptions purely by issue number via exc_by_issue and never reads `phase` (see
# outcomes.py), so this value is not load-bearing for any label -- but it must not
# silently *claim* a phase parsed out of a comment as if it were real structured
# data. Every request recovered from a flat-list file gets this explicit, honest
# placeholder instead.
UNSPECIFIED_PHASE = "unspecified"

# Seen in release-1.23's header comments; corrupts an otherwise-valid document.
# Stripping it is a data-cleaning step on a known-dirty source, not a heuristic.
_ZERO_WIDTH_SPACE = "\u200b"


@dataclass(frozen=True)
class ExceptionRequest:
    issue: int
    phase: str
    status: str
    date_requested: date | None


@dataclass(frozen=True)
class SkippedExceptionsFile:
    """One release-1.N/exceptions.yaml that contributed zero requests, and why.

    Populated by load_exceptions when a caller passes a `skipped` list, so a file
    that exists but yields nothing is never silently invisible -- mirrors the
    "count them and print in build" pattern used elsewhere for filtered-out data.
    A genuinely empty document (`data is None`) is not a skip: there is nothing
    wrong with it, it simply has no requests to report.
    """
    milestone_id: str
    path: Path
    reason: str


def _date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def _requests_from_items(items, phase: str) -> list[ExceptionRequest]:
    out = []
    for r in items:
        if not isinstance(r, dict):
            continue
        try:
            issue = int(r.get("issue"))
        except (TypeError, ValueError):
            continue
        out.append(ExceptionRequest(issue, phase, str(r.get("status") or "").strip().lower(), _date(r.get("date_requested"))))
    return out


def _parse(text: str) -> tuple[list[ExceptionRequest], str | None]:
    """Returns (requests, reason). reason is None on a clean parse -- including a
    genuinely empty document -- and a short human-readable explanation otherwise
    (invalid YAML, or a top-level shape that is neither the modern mapping schema
    nor the legacy flat-list schema).
    """
    try:
        data = yaml.safe_load(text.replace(_ZERO_WIDTH_SPACE, ""))
    except yaml.YAMLError as e:
        return [], f"invalid YAML: {str(e).splitlines()[0]}"
    if data is None:
        return [], None
    if isinstance(data, list):
        # Legacy flat-list schema (pre-v1.24): no structured phase separation.
        return _requests_from_items(data, UNSPECIFIED_PHASE), None
    if isinstance(data, dict):
        out = []
        for key, phase in _PHASES.items():
            out.extend(_requests_from_items(data.get(key) or [], phase))
        return out, None
    return [], f"unrecognized top-level YAML type: {type(data).__name__}"


def parse_exceptions_yaml(text: str) -> list[ExceptionRequest]:
    requests, _reason = _parse(text)
    return requests


def load_exceptions(sig_release_repo: Path, skipped: list[SkippedExceptionsFile] | None = None) -> dict[str, list[ExceptionRequest]]:
    """skipped: optional out-list. When given, one SkippedExceptionsFile is appended
    for every release-1.N/exceptions.yaml that contributed zero requests because it
    could not be parsed (invalid YAML or an unrecognized top-level shape) -- as
    opposed to a file that legitimately has no requests. Optional and additive so
    existing callers are unaffected; a later task (build) can pass a list and print
    it so nothing is silently lost.
    """
    out = {}
    for p in sorted((sig_release_repo / "releases").glob("release-1.*/exceptions.yaml")):
        minor = p.parent.name.split(".")[1]
        milestone_id = f"k8s:v1.{minor}"
        requests, reason = _parse(p.read_text())
        if reason is not None and skipped is not None:
            skipped.append(SkippedExceptionsFile(milestone_id, p, reason))
        out[milestone_id] = requests
    return out
