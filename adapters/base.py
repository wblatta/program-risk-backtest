"""What every corpus adapter must provide. See spec §4."""
from __future__ import annotations
from typing import Protocol
from core.config import AdapterConfig
from core.model import Event, Milestone, OrgUnit, WorkItem

__all__ = ["AdapterConfig", "Adapter"]


class Adapter(Protocol):
    config: AdapterConfig

    def fetch(self) -> None: ...
    def work_items(self) -> list[WorkItem]: ...
    def org_units(self) -> list[OrgUnit]: ...
    def milestones(self) -> list[Milestone]: ...
    def events(self) -> list[Event]: ...
