"""Read-only query surface over a corpus, shared by the CLI and the MCP wrapper.

Spec §2 priority 3 pairs the live view with *"an MCP wrapper over the store"*. This module
is the part worth testing: plain functions over loaded events, with no transport. The MCP
server (`mcp_server.py`) binds these and adds nothing.

**Every method here honours the leakage boundary**, because a query surface is exactly
where it would be lost. `snapshot_at` cannot return an outcome, and `signals_firing`
refuses a date after the milestone's freeze — a caller asking "what were the signals saying
in September about a June commitment" would read the answer as a prediction, and it would
not be one. `item_history` is the deliberate exception: it is an audit view of a past item,
returns outcomes on purpose, and is named so that is obvious.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone

from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone, OrgUnit, WorkItem
from core.replay import snapshot
from signals import SIGNALS
from signals.base import Context, DEFAULT_PARAMS, targets_at


def _as_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.combine(date.fromisoformat(str(value)), time(23, 59, 59), tzinfo=timezone.utc)


class CorpusQuery:
    """One corpus, loaded once. Cheap to construct from a `Store`."""

    def __init__(self, corpus: str, events: list[Event], milestones: list[Milestone],
                 org_units: list[OrgUnit], items: list[WorkItem], config: AdapterConfig,
                 params: dict | None = None):
        self.corpus = corpus
        self.events = sorted(events, key=Event.sort_key)
        self._milestones = {m.id: m for m in milestones}
        self.org_units = org_units
        self.items = {i.id: i for i in items}
        self.config = config
        self.params = dict(params or DEFAULT_PARAMS)

    # --- reference data ---

    def milestones(self) -> list[dict]:
        """The calendar. Named as a method, not an attribute, so it cannot be confused
        with the internal id->Milestone map."""
        return [{"id": m.id, "ordinal": m.ordinal,
                 "freeze": m.freeze.isoformat() if m.freeze else None,
                 "release": m.release.isoformat() if m.release else None,
                 "dates": {k: v.isoformat() for k, v in m.dates.items()}}
                for m in sorted(self._milestones.values(), key=lambda x: x.ordinal)]

    # --- point-in-time ---

    def snapshot_at(self, as_of: str) -> dict[str, dict]:
        """The roadmap as it stood on `as_of`. Contains no outcome, ever."""
        states = snapshot(self.events, _as_dt(as_of), presorted=True)
        return {iid: {"targets": dict(s.targets),
                      "status": s.status,
                      "owners": {r: sorted(v) for r, v in s.owners.items() if v},
                      "labels": sorted(s.labels),
                      "deps": sorted(s.deps),
                      "last_activity": {a: t.isoformat() for a, t in s.last_activity.items()},
                      "title": self.items[iid].title if iid in self.items else None}
                for iid, s in states.items()}

    def signals_firing(self, milestone_id: str, as_of: str) -> list[dict]:
        """Which signals fire, for each row committed to `milestone_id`, as of `as_of`."""
        m = self._milestones.get(milestone_id)
        if m is None:
            raise KeyError(f"unknown milestone {milestone_id!r}")
        when = _as_dt(as_of)
        if m.freeze is not None and when.date() > m.freeze:
            raise ValueError(
                f"{as_of} is after {milestone_id}'s freeze ({m.freeze.isoformat()}). "
                "Signals evaluated after the commitment locks are not predictions; "
                "read the backtest for what they achieved.")
        states = snapshot(self.events, when, presorted=True)
        visible = {mid: x for mid, x in self._milestones.items() if x.ordinal <= m.ordinal}
        prior = [e for e in self.events if e.kind == K.OUTCOME and e.ts <= when]
        ctx = Context(when, m, visible, self.org_units, self.config, dict(self.params), prior)
        rows: dict[tuple[str, str], list[str]] = {}
        for iid, s in states.items():
            for stage in targets_at(s, milestone_id):
                rows[(iid, stage)] = []
        for name, fn in SIGNALS.items():
            for key in fn(states, ctx):
                if key in rows:
                    rows[key].append(name)
        return [{"item_id": i, "stage": st, "signals": sorted(names),
                 "title": self.items[i].title if i in self.items else None}
                for (i, st), names in sorted(rows.items())]

    # --- audit ---

    def item_history(self, item_id: str) -> list[dict]:
        """Every event for one item, oldest first, **including outcomes**.

        An audit view of the past, not a point-in-time view. Use `snapshot_at` for
        anything that feeds a prediction.
        """
        evs = [e for e in self.events if e.item_id == item_id]
        if not evs:
            raise KeyError(f"unknown item {item_id!r}")
        return [{"ts": e.ts.isoformat(), "kind": e.kind, "payload": e.payload, "source": e.source}
                for e in evs]
