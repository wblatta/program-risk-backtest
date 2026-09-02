"""Tracking-issue payloads -> typed records and timestamped label history.

Every KEP has a tracking issue in kubernetes/enhancements whose **issue number is the
KEP number** (spec §5 amendment 2), carrying the release team's `tracked/yes|no|
out-of-tree`, `stage/*`, `lead-opted-in` and `sig/*` labels.

An issue's *current* labels are a snapshot of today, which is the wrong shape for a
backtest: they say what is true now, not what was knowable at a past date. The timeline
endpoint gives `labeled`/`unlabeled` events with `created_at`, so label history can be
replayed to any point in time the same way `core.replay.snapshot()` replays the event
stream. `labels_at()` uses the same inclusive `as_of` convention.

Parsing only -- no network, no I/O. `adapters.k8s.github` fetches; this interprets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IssueMeta:
    number: int
    state: str
    closed_at: datetime | None
    milestone: str | None
    labels: tuple[str, ...]


@dataclass(frozen=True)
class LabelEvent:
    ts: datetime
    label: str
    op: str  # "add" | "remove"


def _ts(value) -> datetime | None:
    """GitHub timestamps are RFC3339 with a literal Z, which fromisoformat rejects
    before 3.11; normalise rather than depending on the interpreter version."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_issue(d: dict) -> IssueMeta:
    milestone = (d.get("milestone") or {}).get("title")
    labels = tuple(sorted(
        str(l.get("name")) for l in (d.get("labels") or []) if isinstance(l, dict) and l.get("name")))
    return IssueMeta(number=int(d["number"]), state=str(d.get("state") or ""),
                     closed_at=_ts(d.get("closed_at")), milestone=milestone, labels=labels)


_OPS = {"labeled": "add", "unlabeled": "remove"}


def parse_timeline(events) -> list[LabelEvent]:
    """Label add/remove events, oldest first. Entries missing a usable timestamp or
    label name are skipped: the timeline carries two dozen event types and the shape
    varies by age, so a malformed entry must not cost the whole issue's history."""
    out = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        op = _OPS.get(e.get("event"))
        if op is None:
            continue
        ts = _ts(e.get("created_at"))
        name = (e.get("label") or {}).get("name") if isinstance(e.get("label"), dict) else None
        if ts is None or not name:
            continue
        out.append(LabelEvent(ts, str(name), op))
    return sorted(out, key=lambda e: (e.ts, e.label, e.op))


def labels_at(events: list[LabelEvent], as_of: datetime) -> set[str]:
    """Labels in force at `as_of`. Inclusive of events exactly at `as_of`, matching
    `core.replay.snapshot()`."""
    live: set[str] = set()
    for e in events:
        if e.ts > as_of:
            break
        if e.op == "add":
            live.add(e.label)
        else:
            live.discard(e.label)
    return live


# --- fetching -------------------------------------------------------------------
# Cached under cache/k8s/github/, which is gitignored. Caching is not an optimisation
# here: a full pass is ~1,300 requests against a 5,000/hour budget, so an uncached
# re-run would burn a quarter of the hour's allowance to learn nothing new.

import json as _json
from pathlib import Path

REPO = "kubernetes/enhancements"


def _cached(path: Path):
    try:
        return _json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def fetch_tracking(cache_dir, numbers, client, repo: str = REPO):
    """Fetch issue + timeline for each number, writing each to disk as it arrives.

    Returns `(records, stopped_early)`. Stops at the first `RateLimitError` rather than
    raising, because everything already written stays valid: the next run resumes from
    disk instead of starting over. Both files are written only once both have been
    fetched, so a partial issue is never mistaken for a complete one.
    """
    from adapters.k8s.github import RateLimitError

    cache_dir = Path(cache_dir)
    idir, tdir = cache_dir / "issues", cache_dir / "timeline"
    idir.mkdir(parents=True, exist_ok=True)
    tdir.mkdir(parents=True, exist_ok=True)

    records: dict[int, dict] = {}
    for n in numbers:
        ip, tp = idir / f"{n}.json", tdir / f"{n}.json"
        issue, timeline = _cached(ip), _cached(tp)
        if issue is not None and timeline is not None:
            records[n] = {"issue": issue, "timeline": timeline}
            continue
        try:
            if issue is None:
                issue = client.get_json(f"https://api.github.com/repos/{repo}/issues/{n}")
            if timeline is None:
                timeline = client.get_json(
                    f"https://api.github.com/repos/{repo}/issues/{n}/timeline?per_page=100")
        except RateLimitError:
            return records, True
        ip.write_text(_json.dumps(issue))
        tp.write_text(_json.dumps(timeline))
        records[n] = {"issue": issue, "timeline": timeline}
    return records, False


def label_events(item_id: str, timeline) -> list["Event"]:
    """Timestamped tracking-label changes as core events, so `snapshot()` can replay them.

    Only `tracked/*` and `stage/*` are emitted. The rest of the vocabulary
    (`lifecycle/*`, `sig/*`, `kind/*`) is either noise for this purpose or already
    carried by other events, and every extra label multiplies the event stream without
    adding signal.
    """
    from core.model import Event, EventKind as K
    out = []
    for e in parse_timeline(timeline):
        if not (e.label.startswith("tracked/") or e.label.startswith("stage/")):
            continue
        out.append(Event(e.ts, item_id, K.LABEL_CHANGED,
                         {"label": e.label, "op": e.op}, "tracking-issue"))
    return out
