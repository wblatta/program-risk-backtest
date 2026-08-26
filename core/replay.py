"""Replay non-outcome events up to as_of into per-item state. The leakage guard lives here."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable
from core.model import Event, EventKind as K


@dataclass
class ItemState:
    item_id: str
    created_at: datetime
    targets: dict[str, str] = field(default_factory=dict)
    target_set_at: dict[str, datetime] = field(default_factory=dict)
    target_history: dict[str, list[str]] = field(default_factory=dict)
    status: str | None = None
    owners: dict[str, set[str]] = field(default_factory=dict)
    deps: set[str] = field(default_factory=set)
    last_activity: dict[str, datetime] = field(default_factory=dict)

    @property
    def last_activity_any(self) -> datetime | None:
        return max(self.last_activity.values()) if self.last_activity else None


def snapshot(events: Iterable[Event], as_of: datetime, *, presorted: bool = False) -> dict[str, ItemState]:
    # Sorting is O(n log n) and the hot callers snapshot the same list hundreds of times.
    # They sort once and pass presorted=True; ad-hoc callers get the safe default.
    states: dict[str, ItemState] = {}
    for e in (events if presorted else sorted(events, key=Event.sort_key)):
        if e.kind == K.OUTCOME or e.ts > as_of:
            continue
        s = states.get(e.item_id)
        if s is None:
            s = states[e.item_id] = ItemState(e.item_id, e.ts)
        p = e.payload
        if e.kind == K.TARGET_SET:
            stage = p.get("stage") or ""
            s.targets[stage] = p["milestone_id"]
            s.target_set_at[stage] = e.ts
            hist = s.target_history.setdefault(stage, [])
            if not hist or hist[-1] != p["milestone_id"]:
                hist.append(p["milestone_id"])
        elif e.kind == K.STATUS_CHANGED:
            s.status = p["status"]
        elif e.kind == K.OWNER_CHANGED:
            bucket = s.owners.setdefault(p["role"], set())
            (bucket.add if p["op"] == "add" else bucket.discard)(p["subject_id"])
        elif e.kind == K.DEPENDENCY_CHANGED:
            (s.deps.add if p["op"] == "add" else s.deps.discard)(p["depends_on_id"])
        elif e.kind == K.ACTIVITY:
            actor = p["actor_id"]
            if actor not in s.last_activity or s.last_activity[actor] < e.ts:
                s.last_activity[actor] = e.ts
    return states
