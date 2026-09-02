from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.dep_ordering_conflict import dep_ordering_conflict
from signals.dep_inactive import dep_inactive

UTC = timezone.utc
M1 = Milestone("x:v1", 1, date(2024, 3, 10), date(2024, 4, 13), {})
M2 = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {})
M3 = Milestone("x:v3", 3, date(2024, 11, 10), date(2024, 12, 13), {})
NOW = datetime(2024, 6, 1, tzinfo=UTC)
PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}
MS = {M1.id: M1, M2.id: M2, M3.id: M3}


def ctx(as_of=NOW, m=M2):
    return Context(as_of, m, MS, [], AdapterConfig("x", ()), dict(PARAMS))


_DEFAULT_TARGETS = {"alpha": "x:v2"}


def item(iid, targets=None, deps=(), owners=(("author", "x:@a"),), activity=None):
    s = ItemState(iid, datetime(2024, 1, 1, tzinfo=UTC))
    # `targets={}` means "targets nothing" and must not fall through to the default --
    # an untargeted dependency is a case both signals are specified to stay quiet on.
    for stage, ms in (_DEFAULT_TARGETS if targets is None else targets).items():
        s.targets[stage] = ms
    s.deps |= set(deps)
    for role, who in owners:
        s.owners.setdefault(role, set()).add(who)
    for who, ts in (activity or {}).items():
        s.last_activity[who] = ts
    return s


# --- S4a dep_ordering_conflict ------------------------------------------------

def test_fires_when_a_dependency_lands_no_earlier_than_this_item():
    """The core ordering defect: this item is due in v2 and what it depends on is not
    due until v3, so the plan cannot hold as written."""
    states = {"x:i": item("x:i", deps=["x:d"]), "x:d": item("x:d", targets={"alpha": "x:v3"})}
    assert dep_ordering_conflict(states, ctx()) == {("x:i", "alpha")}

def test_fires_when_the_dependency_targets_the_same_milestone():
    """Same-milestone is a conflict too: nothing sequences them, so a slip in one is a
    slip in both."""
    states = {"x:i": item("x:i", deps=["x:d"]), "x:d": item("x:d", targets={"alpha": "x:v2"})}
    assert dep_ordering_conflict(states, ctx()) == {("x:i", "alpha")}

def test_quiet_when_the_dependency_lands_earlier():
    states = {"x:i": item("x:i", deps=["x:d"]), "x:d": item("x:d", targets={"alpha": "x:v1"})}
    assert dep_ordering_conflict(states, ctx()) == set()

def test_quiet_when_the_dependency_has_no_target():
    """An untargeted dependency may be finished, abandoned, or out of scope. Without a
    target there is no ordering claim to make, and inventing one would fire on every
    reference to a completed enhancement."""
    states = {"x:i": item("x:i", deps=["x:d"]), "x:d": item("x:d", targets={})}
    assert dep_ordering_conflict(states, ctx()) == set()

def test_quiet_when_the_dependency_is_not_in_the_snapshot():
    assert dep_ordering_conflict({"x:i": item("x:i", deps=["x:gone"])}, ctx()) == set()

def test_ignores_milestones_not_yet_visible():
    """`Context.milestones_by_id` is filtered to ordinal <= this milestone. A dependency
    targeting a later, invisible milestone must not be resolved by reaching around it."""
    c = Context(NOW, M2, {M1.id: M1, M2.id: M2}, [], AdapterConfig("x", ()), dict(PARAMS))
    states = {"x:i": item("x:i", deps=["x:d"]), "x:d": item("x:d", targets={"alpha": "x:v3"})}
    assert dep_ordering_conflict(states, c) == set()


# --- S4b dep_inactive ---------------------------------------------------------

STALE = {"x:@a": datetime(2024, 2, 1, tzinfo=UTC)}
FRESH = {"x:@a": datetime(2024, 5, 25, tzinfo=UTC)}


def test_fires_when_a_dependency_is_itself_hollow():
    states = {"x:i": item("x:i", deps=["x:d"], activity=FRESH),
              "x:d": item("x:d", targets={"alpha": "x:v3"}, activity=STALE)}
    assert dep_inactive(states, ctx()) == {("x:i", "alpha")}

def test_quiet_when_the_dependency_is_active():
    states = {"x:i": item("x:i", deps=["x:d"], activity=FRESH),
              "x:d": item("x:d", targets={"alpha": "x:v3"}, activity=FRESH)}
    assert dep_inactive(states, ctx()) == set()

def test_fires_regardless_of_whether_this_item_is_itself_active():
    """S4b is a claim about the neighbour, not about the item. An item working hard on a
    dead dependency is exactly the case H2 predicts."""
    states = {"x:i": item("x:i", deps=["x:d"], activity=FRESH),
              "x:d": item("x:d", targets={"alpha": "x:v3"}, activity=None)}
    assert dep_inactive(states, ctx()) == {("x:i", "alpha")}

def test_quiet_without_dependencies():
    assert dep_inactive({"x:i": item("x:i", activity=FRESH)}, ctx()) == set()

def test_fires_for_every_targeted_stage():
    states = {"x:i": item("x:i", targets={"alpha": "x:v2", "beta": "x:v2"}, deps=["x:d"], activity=FRESH),
              "x:d": item("x:d", targets={"alpha": "x:v3"}, activity=STALE)}
    assert dep_inactive(states, ctx()) == {("x:i", "alpha"), ("x:i", "beta")}
