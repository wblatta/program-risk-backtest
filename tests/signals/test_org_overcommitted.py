from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone
from core.replay import ItemState
from signals.base import Context
from signals.org_overcommitted import org_overcommitted

UTC = timezone.utc
M2 = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)})
M1 = Milestone("x:v1", 1, date(2024, 2, 10), date(2024, 3, 13), {})
PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}


def outcome(item, milestone, result, ts=datetime(2024, 3, 13, tzinfo=UTC), stage="alpha"):
    return Event(ts, item, K.OUTCOME, {"milestone_id": milestone, "stage": stage, "result": result}, "derived")


def ctx(prior):
    return Context(datetime(2024, 6, 20, tzinfo=UTC), M2, {M1.id: M1, M2.id: M2}, [],
                   AdapterConfig("x", ()), dict(PARAMS), prior)


def _item(iid, org="x:sig-a", stages=("alpha",), milestone="x:v2"):
    s = ItemState(iid, datetime(2024, 1, 1, tzinfo=UTC))
    for st in stages:
        s.targets[st] = milestone
    s.owners["owning"] = {org}
    return s


def test_fires_when_targeted_count_exceeds_historical_best():
    """sig-a shipped 1 in v1 and has now committed 2. The claim is about throughput:
    an org that has never delivered this much has committed to more than it has shown."""
    states = {"x:i1": _item("x:i1"), "x:i2": _item("x:i2")}
    prior = [outcome("x:old1", "x:v1", "shipped"), outcome("x:old2", "x:v1", "slipped")]
    states["x:old1"] = _item("x:old1", milestone="x:v1")
    states["x:old2"] = _item("x:old2", milestone="x:v1")
    assert org_overcommitted(states, ctx(prior)) == {("x:i1", "alpha"), ("x:i2", "alpha")}

def test_quiet_when_within_historical_best():
    states = {"x:i1": _item("x:i1"), "x:old1": _item("x:old1", milestone="x:v1"),
              "x:old2": _item("x:old2", milestone="x:v1")}
    prior = [outcome("x:old1", "x:v1", "shipped"), outcome("x:old2", "x:v1", "shipped")]
    assert org_overcommitted(states, ctx(prior)) == set()

def test_exception_granted_counts_as_delivered():
    """Spec §8: exception_granted is a near-miss, not a miss. Excluding it would
    understate an org's demonstrated throughput and over-fire this signal."""
    states = {"x:i1": _item("x:i1"), "x:old1": _item("x:old1", milestone="x:v1"),
              "x:old2": _item("x:old2", milestone="x:v1")}
    prior = [outcome("x:old1", "x:v1", "shipped"), outcome("x:old2", "x:v1", "exception_granted")]
    assert org_overcommitted(states, ctx(prior)) == set()

def test_unresolved_does_not_count_as_delivered():
    """`unresolved` means the outcome is unknown to the instrument, not that it shipped."""
    states = {"x:i1": _item("x:i1"), "x:i2": _item("x:i2"),
              "x:old1": _item("x:old1", milestone="x:v1"),
              "x:old2": _item("x:old2", milestone="x:v1")}
    prior = [outcome("x:old1", "x:v1", "shipped"), outcome("x:old2", "x:v1", "unresolved")]
    # best is 1, not 2: committing 2 fires. Had `unresolved` counted, best would be 2
    # and this would be silent.
    assert org_overcommitted(states, ctx(prior)) == {("x:i1", "alpha"), ("x:i2", "alpha")}

def test_no_history_means_no_firing():
    """With no prior record there is no throughput claim to make. Firing on every org
    in the first cycle would be an artifact of the corpus start, not a finding."""
    assert org_overcommitted({"x:i1": _item("x:i1")}, ctx([])) == set()

def test_items_without_an_owning_org_are_skipped():
    s = _item("x:i1"); s.owners.pop("owning")
    assert org_overcommitted({"x:i1": s}, ctx([outcome("x:old1", "x:v1", "shipped")])) == set()

def test_max_is_taken_across_milestones_not_summed():
    """Historical *max per milestone*, per spec §7 -- not the lifetime total, which would
    grow forever and silence the signal."""
    states = {"x:i1": _item("x:i1"), "x:i2": _item("x:i2")}
    for n, ms in (("x:a", "x:v1"), ("x:b", "x:v1"), ("x:c", "x:v0")):
        states[n] = _item(n, milestone=ms)
    prior = [outcome("x:a", "x:v1", "shipped"), outcome("x:b", "x:v1", "shipped"),
             outcome("x:c", "x:v0", "shipped")]
    assert org_overcommitted(states, ctx(prior)) == set()   # max is 2, committed 2
