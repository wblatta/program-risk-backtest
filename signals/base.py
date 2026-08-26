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
    as_of: datetime
    milestone: Milestone
    milestones_by_id: dict[str, Milestone]
    org_units: list[OrgUnit]
    config: AdapterConfig
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    prior_outcomes: list[Event] = field(default_factory=list)

    def weeks(self, key: str) -> timedelta:
        return timedelta(weeks=self.params[key])


Signal = Callable[[dict[str, ItemState], Context], set[str]]


def targets_at(state: ItemState, milestone_id: str) -> list[str]:
    return [stage for stage, m in state.targets.items() if m == milestone_id]
