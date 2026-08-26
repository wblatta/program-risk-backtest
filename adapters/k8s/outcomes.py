"""Labeling rule v1. See LABELING.md — the doc is normative, this is its implementation."""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from core.model import Event, EventKind as K, Milestone
from core.replay import snapshot
from adapters.k8s.exceptions import ExceptionRequest

# "removed" is deliberately NOT in this set -- see LABELING.md ("dropped" section) for why:
# on the real corpus it marks a KEP whose already-shipped feature was later removed from
# Kubernetes, not a KEP that was abandoned before shipping.
DROP_STATUSES = {"withdrawn", "rejected", "deferred", "replaced", "superseded"}
SRC = "derived"


def _dt(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def _kep_number(item_id: str) -> int | None:
    try:
        return int(item_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


def outcome_events(events: list[Event], milestones: list[Milestone], exceptions: dict[str, list[ExceptionRequest]], today: date) -> list[Event]:
    by_id = {m.id: m for m in milestones}
    out: list[Event] = []
    events = sorted(events, key=Event.sort_key)
    # Bucket by item once. Scanning all events per (milestone, item, stage) is quadratic:
    # ~800 KEPs x ~40 milestones x tens of thousands of events stalls the real build, while
    # the unit tests below stay fast enough to hide it.
    by_item: dict[str, list[Event]] = {}
    for e in events:
        by_item.setdefault(e.item_id, []).append(e)
    for m in sorted(milestones, key=lambda x: x.ordinal):
        ef = m.dates.get("enhancements_freeze")
        if not m.is_scheduled or ef is None or m.release > today:
            continue
        ef_dt = _dt(ef)
        nxt = next((x for x in milestones if x.ordinal > m.ordinal and x.dates.get("enhancements_freeze")), None)
        window_end = _dt(nxt.dates["enhancements_freeze"]) if nxt else _dt(today)
        exc_by_issue = {e.issue: e for e in exceptions.get(m.id, [])}
        for item_id, state in snapshot(events, ef_dt, presorted=True).items():
            if m.id not in state.targets.values():
                continue
            later = [e for e in by_item.get(item_id, ()) if e.ts > ef_dt]
            for stage, target in state.targets.items():
                if target != m.id:
                    continue

                # Rule 1: slipped. Only a genuine retarget (op != "clear") to a
                # higher-ordinal milestone counts -- a clear's milestone_id names the
                # milestone being retracted, not a destination, and must not be read as
                # a move by a naive ordinal comparison.
                retargeted = any(
                    e.kind == K.TARGET_SET
                    and e.payload.get("op") != "clear"
                    and (e.payload.get("stage") or "") == stage
                    and by_id.get(e.payload["milestone_id"], m).ordinal > m.ordinal
                    for e in later
                )
                if retargeted:
                    result = "slipped"
                else:
                    # Rule 2: dropped. Either a status change into DROP_STATUSES, or a
                    # TARGET_SET clear for this same (stage, milestone) -- both within the
                    # window from this milestone's enhancements freeze to the next
                    # milestone's enhancements freeze (or today, if there is no next one).
                    dropped_by_status = any(
                        e.kind == K.STATUS_CHANGED and e.payload["status"] in DROP_STATUSES and e.ts <= window_end
                        for e in later
                    )
                    dropped_by_clear = any(
                        e.kind == K.TARGET_SET
                        and e.payload.get("op") == "clear"
                        and (e.payload.get("stage") or "") == stage
                        and e.payload.get("milestone_id") == m.id
                        and e.ts <= window_end
                        for e in later
                    )
                    if dropped_by_status or dropped_by_clear:
                        result = "dropped"
                    else:
                        exc = exc_by_issue.get(_kep_number(item_id))
                        if exc and exc.status != "approved":
                            result = "exception_denied"
                        elif exc:
                            result = "exception_granted"
                        else:
                            result = "shipped"
                out.append(Event(_dt(m.release), item_id, K.OUTCOME, {"milestone_id": m.id, "stage": stage, "result": result}, SRC))
    return out
