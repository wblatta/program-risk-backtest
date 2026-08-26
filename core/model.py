"""Normalized model. Three reference entities and one event stream."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from typing import Any


class EventKind:
    TARGET_SET = "target_set"
    STATUS_CHANGED = "status_changed"
    OWNER_CHANGED = "owner_changed"
    DEPENDENCY_CHANGED = "dependency_changed"
    ACTIVITY = "activity"
    OUTCOME = "outcome"
    ALL = frozenset({TARGET_SET, STATUS_CHANGED, OWNER_CHANGED, DEPENDENCY_CHANGED, ACTIVITY, OUTCOME})


# Adapter-output vocabulary, enforced by the conformance suite rather than by Event.__post_init__
SOURCES = frozenset({"git-history", "calendar", "exceptions", "derived"})


def corpus_of(id: str) -> str:
    return id.split(":", 1)[0]


@dataclass(frozen=True)
class WorkItem:
    id: str
    title: str
    url: str


@dataclass(frozen=True)
class OrgUnit:
    id: str
    name: str


@dataclass(frozen=True)
class Milestone:
    id: str
    ordinal: int
    freeze: date | None
    release: date | None
    dates: dict[str, date] = field(default_factory=dict)

    @property
    def is_scheduled(self) -> bool:
        return self.freeze is not None and self.release is not None


@dataclass(frozen=True)
class Event:
    ts: datetime
    item_id: str
    kind: str
    payload: dict[str, Any]
    source: str

    def __post_init__(self):
        if self.ts.tzinfo is None or self.ts.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("Event.ts must be timezone-aware UTC")
        if not self.source:
            raise ValueError("Event.source is required")
        if self.kind not in EventKind.ALL:
            raise ValueError(f"unknown event kind {self.kind!r}")

    def sort_key(self) -> tuple:
        return (self.ts, self.item_id, self.kind, json.dumps(self.payload, sort_keys=True, default=str))

    def to_row(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "corpus": corpus_of(self.item_id),
            "item_id": self.item_id,
            "kind": self.kind,
            "payload": json.dumps(self.payload, sort_keys=True, default=str),
            "source": self.source,
        }

    @classmethod
    def from_row(cls, row) -> "Event":
        return cls(datetime.fromisoformat(row["ts"]), row["item_id"], row["kind"], json.loads(row["payload"]), row["source"])
