"""Parse a kep.yaml file into a normalized KepMeta. Pure; no I/O."""
from __future__ import annotations
from dataclasses import dataclass
import re
import yaml

_PLACEHOLDERS = {"", "tbd", "nnnn", "n/a", "none", "null"}
_MILESTONE_RE = re.compile(r"^v?\d+\.\d+$")


class KepParseError(Exception):
    pass


@dataclass(frozen=True)
class KepMeta:
    number: int | None
    title: str
    owning_sig: str
    participating_sigs: tuple[str, ...]
    status: str
    stage: str | None
    latest_milestone: str | None
    milestones: dict[str, str]
    authors: tuple[str, ...]
    reviewers: tuple[str, ...]
    approvers: tuple[str, ...]


def _handles(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = []
    for v in value:
        if not isinstance(v, str):
            continue
        s = v.strip().lower()
        if s in _PLACEHOLDERS:
            continue
        if not s.startswith("@"):
            s = "@" + s
        out.append(s)
    return tuple(out)


def _strs(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value if isinstance(v, str) and str(v).strip().lower() not in _PLACEHOLDERS)


def _milestone(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().strip('"')
    if s.lower() in _PLACEHOLDERS or not _MILESTONE_RE.match(s):
        return None
    return s if s.startswith("v") else "v" + s


def _number(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_kep_yaml(text: str) -> KepMeta:
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, ValueError) as e:
        # ValueError: PyYAML's implicit timestamp resolver raises a bare
        # ValueError (not yaml.YAMLError) for a syntactically-plausible but
        # calendrically-invalid date, e.g. "creation-date: 2023-14-05".
        # Observed in real kep.yaml files during the ingestion spike.
        raise KepParseError(str(e)) from e
    if not isinstance(data, dict):
        raise KepParseError("kep.yaml is not a mapping")
    raw_ms = data.get("milestone") or {}
    milestones = {}
    if isinstance(raw_ms, dict):
        for stage, v in raw_ms.items():
            m = _milestone(v)
            if m:
                milestones[str(stage).strip().lower()] = m
    stage = data.get("stage")
    return KepMeta(
        number=_number(data.get("kep-number")),
        title=str(data.get("title") or "").strip(),
        owning_sig=str(data.get("owning-sig") or "").strip().lower(),
        participating_sigs=tuple(s.lower() for s in _strs(data.get("participating-sigs"))),
        status=str(data.get("status") or "").strip().lower(),
        stage=str(stage).strip().lower() if isinstance(stage, str) and stage.strip() else None,
        latest_milestone=_milestone(data.get("latest-milestone")),
        milestones=milestones,
        authors=_handles(data.get("authors")),
        reviewers=_handles(data.get("reviewers")),
        approvers=_handles(data.get("approvers")),
    )
