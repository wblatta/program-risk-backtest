"""Weekly snapshots per cycle → first-fired per signal → join to held-out outcomes."""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone, OrgUnit
from core.replay import snapshot
from signals.base import Context, Signal

# The positive/negative partition of the five outcome labels is defined in
# adapters/k8s/LABELING.md ("Positive class"), which is normative: this set implements
# that table and the two must agree exactly. In particular `exception_granted` is
# deliberately *negative* (a near-miss, not a miss) -- 65 rows of the first backtest, and
# the reason the base rate is 0.302 rather than higher.
#
# `exception_denied` is presently *unreachable*, not merely empty: LABELING.md rule 1
# (slipped) is evaluated before rule 3, and a SIG refused an exception retargets, so every
# such case is labeled `slipped` first. This set therefore behaves as {slipped, dropped}
# today. That is a vocabulary defect, not a measurement one -- no row changes class under
# either precedence. Do not "fix" it by editing this line; see LABELING.md.
POSITIVE = {"slipped", "dropped", "exception_denied"}


@dataclass
class Row:
    item_id: str
    stage: str
    milestone_id: str
    org_id: str | None
    outcome: str | None
    first_fired: dict[str, datetime | None] = field(default_factory=dict)


def _eod(d) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def run_backtest(events: list[Event], milestones: list[Milestone], org_units: list[OrgUnit], config: AdapterConfig,
                 signals: dict[str, Signal], params: dict) -> list[Row]:
    # Sort once. snapshot() below runs ~200+ times (weekly x every milestone); letting it
    # re-sort the full event list on each call dominates the runtime.
    events = sorted(events, key=Event.sort_key)
    by_id = {m.id: m for m in milestones}
    outcome_list = [e for e in events if e.kind == K.OUTCOME]   # already in ts order
    outcome_ts = [e.ts for e in outcome_list]
    outcomes = {(e.item_id, e.payload.get("stage") or "", e.payload["milestone_id"]): e for e in outcome_list}
    rows: list[Row] = []
    for m in sorted(milestones, key=lambda x: x.ordinal):
        ef = m.dates.get("enhancements_freeze")
        if not m.is_scheduled or ef is None:
            continue
        start = m.dates.get("start") or (m.freeze - timedelta(weeks=15))
        commit_dt, freeze_dt = _eod(ef), _eod(m.freeze)
        committed = {(iid, st) for iid, s in snapshot(events, commit_dt, presorted=True).items() for st, tgt in s.targets.items() if tgt == m.id}
        first: dict[tuple[str, str], dict[str, datetime | None]] = {key: {n: None for n in signals} for key in committed}
        # Leakage boundary on the calendar (see signals/base.py, Context.milestones_by_id):
        # a signal evaluated at milestone m must not be able to read a *later* milestone's
        # stored freeze/release dates, which are the post-hoc actuals. Filtering here makes
        # that structural rather than a convention a future signal has to remember.
        visible = {mid: x for mid, x in by_id.items() if x.ordinal <= m.ordinal}
        as_of = _eod(start)
        while as_of <= freeze_dt:
            states = snapshot(events, as_of, presorted=True)
            prior = outcome_list[:bisect_right(outcome_ts, as_of)]   # same reason: no full rescan per week
            ctx = Context(as_of, m, visible, org_units, config, dict(params), prior)
            for name, fn in signals.items():
                fired = fn(states, ctx)
                for (iid, st) in committed:
                    if iid in fired and first[(iid, st)][name] is None:
                        first[(iid, st)][name] = as_of
            as_of += timedelta(weeks=1)
        final = snapshot(events, commit_dt, presorted=True)
        for (iid, st) in sorted(committed):
            owning = sorted(final[iid].owners.get("owning", ()))
            oc = outcomes.get((iid, st, m.id))
            rows.append(Row(iid, st, m.id, owning[0] if owning else None,
                            oc.payload["result"] if oc and oc.ts > freeze_dt else None, first[(iid, st)]))
    return rows
