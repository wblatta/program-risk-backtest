from datetime import datetime, timezone, date
import sqlite3
import pytest
from core.model import Event, EventKind, Milestone, OrgUnit, WorkItem
from core.store import Store

UTC = timezone.utc

def _sample():
    items = [WorkItem("k8s:kep-1", "One", "https://x/1")]
    orgs = [OrgUnit("k8s:sig-node", "Node")]
    ms = [Milestone("k8s:v1.31", 31, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)}),
          Milestone("k8s:v1.30", 30, None, None, {})]
    ev = [Event(datetime(2024, 2, 1, tzinfo=UTC), "k8s:kep-1", EventKind.STATUS_CHANGED, {"status": "implementable"}, "git-history"),
          Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"}, "git-history")]
    return items, orgs, ms, ev

def test_round_trip(tmp_path):
    s = Store(tmp_path / "s.sqlite"); s.init_schema()
    items, orgs, ms, ev = _sample()
    s.replace_corpus("k8s", items, orgs, ms, ev)
    assert s.load_items("k8s") == items
    assert s.load_org_units("k8s") == orgs
    loaded_ms = s.load_milestones("k8s")
    assert [m.id for m in loaded_ms] == ["k8s:v1.30", "k8s:v1.31"]
    assert loaded_ms[1].dates == {"enhancements_freeze": date(2024, 6, 7)}
    # Verify placeholder milestone (index 0) field-level assertions
    assert loaded_ms[0].freeze is None
    assert loaded_ms[0].release is None
    assert loaded_ms[0].dates == {}
    assert s.load_events("k8s") == sorted(ev, key=Event.sort_key)

def test_replace_is_idempotent_and_scoped(tmp_path):
    s = Store(tmp_path / "s.sqlite"); s.init_schema()
    items, orgs, ms, ev = _sample()
    s.replace_corpus("k8s", items, orgs, ms, ev)
    s.replace_corpus("k8s", items, orgs, ms, ev)
    assert len(s.load_events("k8s")) == 2
    other = [Event(datetime(2024, 1, 1, tzinfo=UTC), "gitlab:issue-9", EventKind.ACTIVITY, {}, "api")]
    s.replace_corpus("gitlab", [WorkItem("gitlab:issue-9", "x", "u")], [], [], other)
    assert len(s.load_events("k8s")) == 2
    assert len(s.load_events("gitlab")) == 1

def test_atomicity_rollback_on_duplicate_ids(tmp_path):
    """Verify atomicity: mid-batch failure rolls back without corrupting prior content."""
    s = Store(tmp_path / "s.sqlite"); s.init_schema()
    items, orgs, ms, ev = _sample()
    s.replace_corpus("k8s", items, orgs, ms, ev)
    prior_item_count = len(s.load_items("k8s"))
    prior_events = s.load_events("k8s")

    # Attempt to insert two items with duplicate id; should raise IntegrityError
    dup_items = [
        WorkItem("k8s:kep-1", "First", "https://x/1"),
        WorkItem("k8s:kep-1", "Duplicate", "https://x/1-dup")
    ]
    with pytest.raises(sqlite3.IntegrityError):
        s.replace_corpus("k8s", dup_items, [], [], [])

    # Verify prior content is fully intact (no half-deletion)
    assert len(s.load_items("k8s")) == prior_item_count
    assert s.load_events("k8s") == prior_events
