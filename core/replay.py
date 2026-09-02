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
    labels: set[str] = field(default_factory=set)   # tracking-issue labels in force at as_of
    # role -> stage -> subjects, for roles granted per stage rather than per item.
    # `owners` keeps the item-wide union; this keeps the stages apart. K8s grants PRR
    # approval per stage, so an approver on `alpha` is no evidence about `beta` -- and
    # the union cannot tell you which stage is actually covered.
    stage_owners: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    # Bot activity, kept out of `last_activity` rather than discarded. A staleness bot
    # commenting on a dead enhancement is not work on it, and counting it would make
    # abandoned items read as alive -- the exact failure the silence signals exist to
    # catch. Kept rather than dropped so a signal that wants it can still ask.
    last_activity_bot: dict[str, datetime] = field(default_factory=dict)

    @property
    def last_activity_any(self) -> datetime | None:
        return max(self.last_activity.values()) if self.last_activity else None


def snapshot(events: Iterable[Event], as_of: datetime, *, presorted: bool = False) -> dict[str, ItemState]:
    """Replay non-outcome events up to as_of into per-item state, keyed by item_id.

    Args:
        events: Event stream to replay.
        as_of: Cutoff timestamp (inclusive). Events where ts > as_of are excluded.
        presorted: If True, caller guarantees events are sorted by Event.sort_key().
                   If False (default), events are sorted internally. When presorted=True with
                   genuinely unsorted input, results are silently undefined — all last-write-wins
                   fields (targets, status, owners, deps) will be corrupted.
    """
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
            if p.get("op") == "clear":
                s.targets.pop(stage, None)
                s.target_set_at.pop(stage, None)
            else:
                s.targets[stage] = p["milestone_id"]
                s.target_set_at[stage] = e.ts
            hist = s.target_history.setdefault(stage, [])
            if not hist or hist[-1] != p["milestone_id"]:
                hist.append(p["milestone_id"])
        elif e.kind == K.STATUS_CHANGED:
            s.status = p["status"]
        elif e.kind == K.OWNER_CHANGED:
            # Event.sort_key() breaks ties on json-serialized payload. For OWNER_CHANGED,
            # "add" < "remove" lexicographically, so when add and remove occur at the same
            # timestamp for the same subject+role, remove applies last. This is conservative
            # (ownership reads as absent, so risk signals fire) and is pinned by the test suite.
            bucket = s.owners.setdefault(p["role"], set())
            (bucket.add if p["op"] == "add" else bucket.discard)(p["subject_id"])
            # Only stage-scoped grants enter stage_owners. An item-wide role (`owning`,
            # `author`) carries no stage, and inventing one would make every stage look
            # covered because the item was.
            stage = p.get("stage")
            if stage:
                sb = s.stage_owners.setdefault(p["role"], {}).setdefault(stage, set())
                (sb.add if p["op"] == "add" else sb.discard)(p["subject_id"])
        elif e.kind == K.DEPENDENCY_CHANGED:
            (s.deps.add if p["op"] == "add" else s.deps.discard)(p["depends_on_id"])
        elif e.kind == K.LABEL_CHANGED:
            # Tracking-issue labels, replayed like everything else so a signal reading
            # them sees only what was applied by as_of. Reading today's labels instead
            # would leak the future: they are the release team's final word, not their
            # view during the cycle.
            (s.labels.add if p["op"] == "add" else s.labels.discard)(p["label"])
        elif e.kind == K.ACTIVITY:
            # Events with no `bot` key are human by default: git-derived activity predates
            # the flag and is a real commit either way.
            actor, into = p["actor_id"], (s.last_activity_bot if p.get("bot") else s.last_activity)
            if actor not in into or into[actor] < e.ts:
                into[actor] = e.ts
    return states
