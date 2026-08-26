from datetime import datetime, timezone, date
import json
import pytest
from core.model import Event, EventKind, Milestone, corpus_of

UTC = timezone.utc

def test_corpus_of():
    assert corpus_of("k8s:kep-2400") == "k8s"
    assert corpus_of("gitlab:issue-1") == "gitlab"

def test_event_requires_utc_and_source():
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1), "k8s:kep-1", EventKind.ACTIVITY, {}, "git-history")
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {}, "")
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", "bogus", {}, "x")

def test_event_round_trips_through_row():
    e = Event(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC), "k8s:kep-1", EventKind.TARGET_SET,
              {"stage": "alpha", "milestone_id": "k8s:v1.30"}, "git-history")
    row = e.to_row()
    assert row["corpus"] == "k8s"
    assert json.loads(row["payload"]) == e.payload
    assert Event.from_row(row) == e

def test_sort_key_is_deterministic():
    a = Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {"b": 1, "a": 2}, "s")
    b = Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {"a": 2, "b": 1}, "s")
    assert a.sort_key() == b.sort_key()

def test_milestone_dates_optional():
    m = Milestone("k8s:v1.99", 99, None, None, {})
    assert m.freeze is None and m.is_scheduled is False
    m2 = Milestone("k8s:v1.34", 34, date(2025, 7, 25), date(2025, 8, 27), {"enhancements_freeze": date(2025, 6, 20)})
    assert m2.is_scheduled is True
