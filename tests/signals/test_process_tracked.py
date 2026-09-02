"""S0 `process_tracked` -- the control.

The sprint-1 notes set the bar: "a signal that cannot beat the project's own status
field is not worth reporting." S0 IS the project's own status field, read at snapshot
time, so every other signal is measured against it.
"""
from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.process_tracked import process_tracked

UTC = timezone.utc
M = Milestone("x:v1", 1, date(2024, 7, 10), date(2024, 8, 13),
              {"enhancements_freeze": date(2024, 6, 7)})
def ctx(): return Context(datetime(2024, 6, 1, tzinfo=UTC), M, {M.id: M}, [],
                          AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})

def item(labels, stage="alpha", milestone="x:v1"):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets[stage] = milestone
    s.labels.update(labels)
    return s


def test_fires_when_the_release_team_is_not_tracking_it():
    assert process_tracked({"x:i": item({"tracked/no"})}, ctx()) == {("x:i", "alpha")}


def test_fires_when_no_tracking_decision_has_been_recorded():
    """Absence of tracked/yes is the weaker, less tautological form of the control."""
    assert process_tracked({"x:i": item({"sig/node"})}, ctx()) == {("x:i", "alpha")}


def test_silent_when_the_release_team_is_tracking_it():
    assert process_tracked({"x:i": item({"tracked/yes", "sig/node"})}, ctx()) == set()


def test_ignores_items_not_targeting_this_milestone():
    assert process_tracked({"x:i": item({"tracked/no"}, milestone="x:v9")}, ctx()) == set()


def test_emits_one_pair_per_targeting_stage():
    s = item({"tracked/no"})
    s.targets["beta"] = "x:v1"
    assert process_tracked({"x:i": s}, ctx()) == {("x:i", "alpha"), ("x:i", "beta")}
