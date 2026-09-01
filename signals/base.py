"""Signal interface. A signal is a pure function over a snapshot."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from core.config import AdapterConfig
from core.model import Event, Milestone, OrgUnit
from core.replay import ItemState

DEFAULT_PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}


@dataclass
class Context:
    """Everything a signal may read besides the snapshot itself.

    Leakage boundary. Two of these fields are point-in-time and are filtered by
    `run_backtest` before the Context is built; a signal must not reach around either.

    `prior_outcomes` holds only outcome events with `ts <= as_of`. The outcome of the row
    being scored is by construction not in it.

    `milestones_by_id` holds only milestones with `ordinal <= milestone.ordinal`.
    **Reading a higher-ordinal milestone's dates is a leak.** The distinction is subtle
    enough to spell out, because it is not the calendar's *existence* that leaks. A
    release calendar is legitimately known in advance -- corpora of this kind publish a
    cycle's schedule at cycle start -- so knowing that a later milestone exists, and
    roughly when it is meant to land, is not hindsight. But what `Milestone.dates` stores
    is not that published plan: it is where each freeze and release **ended up**, after
    any slips to the release schedule itself. A signal evaluated during one cycle that
    reads a later milestone's stored freeze date is reading a fact that did not exist yet.

    Filtering here makes that structural rather than a rule each new signal author has to
    remember. It was introduced as an experiment and kept: with the filter applied, every
    committed backtest output is byte-identical to the run without it, so no current
    signal depended on the unfiltered calendar. Had anything moved, the filter would have
    been reverted and the change investigated rather than absorbed.
    """
    as_of: datetime
    milestone: Milestone
    milestones_by_id: dict[str, Milestone]
    org_units: list[OrgUnit]
    config: AdapterConfig
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    prior_outcomes: list[Event] = field(default_factory=list)

    def weeks(self, key: str) -> timedelta:
        return timedelta(weeks=self.params[key])


# GRANULARITY CONTRACT -- read before writing a new signal.
#
# A signal returns a set of *item ids*. The unit of analysis, though, is the
# `(item, stage, milestone)` triple of `backtest.run.Row`, so `run_backtest` takes each
# item id a signal returns and **broadcasts it across every stage that item targets at
# that milestone**. Signals are therefore item-scoped; they cannot say "fires for beta but
# not for stable".
#
# Blast radius, measured on the first backtest: 7 `(item, milestone)` pairs carry more
# than one stage, covering 18 of 1,255 rows (1.4%). All three sprint-1 signals agree
# across stages by construction -- `hollow_owner` reads item-wide activity, `prior_slip`
# and `late_target` are `any(...)` over the item's stages at this milestone -- so **no row
# is wrong today**. This is a latent constraint, not a live bug, and it is kept for
# sprint 1 deliberately rather than by oversight.
#
# **A stage-scoped signal cannot be written correctly against this contract.** The
# concrete case is spec §7's S2 `gate_unassigned` -- a required approval role (see
# `AdapterConfig`'s corpus-declared required roles) still unfilled M weeks out. Those
# roles are granted *per stage*, so an S2 that correctly fires for one stage would be
# silently broadcast onto that item's other stages at the same milestone and score them
# as flagged when they were not: a wrong answer that looks like a normal one, with no
# failure to notice. S3 `cross_org` and S6 `org_overcommitted` are genuinely item-scoped
# and are unaffected.
#
# Sprint 2 P0 (see docs/sprint-1-notes.md, "What sprint 2 must do"): widen this to
# `set[tuple[str, str]]` -- `(item_id, stage)` -- *before* landing S2. Do not implement S2
# against the current type.
Signal = Callable[[dict[str, ItemState], Context], set[str]]


def targets_at(state: ItemState, milestone_id: str) -> list[str]:
    return [stage for stage, m in state.targets.items() if m == milestone_id]
