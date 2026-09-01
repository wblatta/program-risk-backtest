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
# A signal returns a set of `(item_id, stage)` pairs, matching the
# `(item, stage, milestone)` unit of analysis in `backtest.run.Row`. A firing names
# exactly the rows it applies to; `run_backtest` matches those pairs against the
# committed set and nothing is broadcast. A signal may therefore fire for `beta` and
# not for `stable` on the same item at the same milestone.
#
# Emit one pair per stage the firing genuinely covers:
#   - An item-scoped condition (`hollow_owner` reads item-wide activity) still emits a
#     pair for *every* stage that item targets at this milestone -- the condition is
#     item-wide, but the firing names rows.
#   - A stage-scoped condition (`prior_slip`, `late_target`) emits only the qualifying
#     stages. Do not reintroduce an `any(...)` over stages: that was the item-scoped
#     shape, and it silently flagged stages that did not qualify.
#
# Use `targets_at(state, milestone_id)` to get the stages an item targets here. A signal
# that returns bare item ids will match nothing and fire on no row -- there is no
# fallback, deliberately, so the mistake fails visibly rather than scoring wrong rows.
#
# This replaced an item-scoped `set[str]` contract in sprint 2. Widening it changed no
# result: on the corpus at the time, all 7 multi-stage `(item, milestone)` pairs -- 18 of
# 1,255 rows -- had identical per-stage qualification for both stage-scoped signals, so
# the outputs were byte-identical before and after. The change was made to unblock
# spec §7's S2 `gate_unassigned`, whose required-approval roles are granted per stage and
# which could not be expressed against the old contract.

Signal = Callable[[dict[str, ItemState], Context], set[tuple[str, str]]]


def targets_at(state: ItemState, milestone_id: str) -> list[str]:
    return [stage for stage, m in state.targets.items() if m == milestone_id]
