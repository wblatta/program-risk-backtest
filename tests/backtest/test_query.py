from datetime import date, datetime, timezone
import pytest
from backtest.query import CorpusQuery
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone, OrgUnit, WorkItem

UTC = timezone.utc
def T(m, d=1): return datetime(2024, m, d, tzinfo=UTC)

M31 = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13),
                {"enhancements_freeze": date(2024, 6, 7), "start": date(2024, 5, 1)})
EVENTS = [
    Event(T(5), "x:i1", K.TARGET_SET, {"stage": "alpha", "milestone_id": "x:v31"}, "t"),
    Event(T(5), "x:i1", K.OWNER_CHANGED, {"subject_id": "x:@alice", "role": "author", "op": "add"}, "t"),
    Event(T(5, 20), "x:i1", K.ACTIVITY, {"actor_id": "x:@alice", "kind": "commented"}, "t"),
    Event(T(8, 13), "x:i1", K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"}, "t"),
]


@pytest.fixture
def q():
    return CorpusQuery("x", EVENTS, [M31], [OrgUnit("x:o", "O")], [WorkItem("x:i1", "One", "u")],
                       AdapterConfig("x", ()))


def test_snapshot_reports_state_as_of_a_date(q):
    s = q.snapshot_at("2024-05-25")
    assert s["x:i1"]["targets"] == {"alpha": "x:v31"}
    assert s["x:i1"]["owners"]["author"] == ["x:@alice"]

def test_snapshot_never_returns_outcomes(q):
    """The leakage boundary is the property this whole project rests on. A query surface
    that could hand an outcome to a caller asking about a past date would undo it."""
    assert all("outcome" not in v for v in q.snapshot_at("2024-12-31").values())

def test_snapshot_excludes_later_events(q):
    assert q.snapshot_at("2024-05-10")["x:i1"]["last_activity"] == {}

def test_item_history_is_chronological_and_includes_outcomes(q):
    """History is a deliberate exception: it is an audit view of a *past* item, not a
    point-in-time view, and it says so."""
    hist = q.item_history("x:i1")
    assert [e["ts"] for e in hist] == sorted(e["ts"] for e in hist)   # chronological
    assert "outcome" in [e["kind"] for e in hist]                     # audit view, on purpose
    assert {e["kind"] for e in hist} == {"target_set", "owner_changed", "activity", "outcome"}

def test_item_history_rejects_an_unknown_item(q):
    with pytest.raises(KeyError):
        q.item_history("x:nope")

def test_signals_firing_names_rows_and_signals(q):
    out = q.signals_firing("x:v31", "2024-06-07")
    assert out and all({"item_id", "stage", "signals"} <= set(r) for r in out)

def test_signals_firing_rejects_an_unknown_milestone(q):
    with pytest.raises(KeyError):
        q.signals_firing("x:v99", "2024-06-07")

def test_signals_firing_refuses_a_date_after_the_freeze(q):
    """Asking what signals said *after* the commitment locked is a different question and
    a trap: the caller would read it as a prediction. Refuse rather than mislead."""
    with pytest.raises(ValueError):
        q.signals_firing("x:v31", "2024-08-01")

def test_milestones_lists_the_calendar(q):
    ms = q.milestones()
    assert ms[0]["id"] == "x:v31" and ms[0]["freeze"] == "2024-07-10"
