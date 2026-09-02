from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.hollow_owner import hollow_owner

UTC = timezone.utc
M = Milestone("x:v1", 1, date(2024, 7, 10), date(2024, 8, 13), {})
NOW = datetime(2024, 6, 1, tzinfo=UTC)
def ctx(as_of=NOW): return Context(as_of, M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})


def item(activity=None, owners=(("author", "x:@alice"),), target=True):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    if target:
        s.targets["alpha"] = "x:v1"
    for role, who in owners:
        s.owners.setdefault(role, set()).add(who)
    for who, ts in (activity or {}).items():
        s.last_activity[who] = ts
    return s


def test_fires_when_the_owner_has_been_quiet_for_N_weeks():
    assert hollow_owner({"x:i": item({"x:@alice": datetime(2024, 3, 1, tzinfo=UTC)})}, ctx()) == {("x:i", "alpha")}

def test_quiet_when_the_owner_is_recently_active():
    assert hollow_owner({"x:i": item({"x:@alice": datetime(2024, 5, 20, tzinfo=UTC)})}, ctx()) == set()

def test_activity_from_a_non_owner_does_not_count():
    """The distinction that separates this signal from `item_silent`, and the whole of
    H1: a busy passer-by must not make an abandoned item read as owned."""
    assert hollow_owner({"x:i": item({"x:@stranger": datetime(2024, 5, 20, tzinfo=UTC)})}, ctx()) == {("x:i", "alpha")}

def test_approvers_and_owning_orgs_count_as_owners():
    for role, who in (("approver", "x:@bob"), ("owning", "x:sig-node")):
        s = item({who: datetime(2024, 5, 20, tzinfo=UTC)}, owners=((role, who),))
        assert hollow_owner({"x:i": s}, ctx()) == set(), role

def test_participating_orgs_are_not_owners():
    """A stakeholder is not accountable. Counting participating SIGs is how a hollow
    item looks staffed."""
    s = item({"x:sig-storage": datetime(2024, 5, 20, tzinfo=UTC)},
             owners=(("author", "x:@alice"), ("participating", "x:sig-storage")))
    assert hollow_owner({"x:i": s}, ctx()) == {("x:i", "alpha")}

def test_any_one_active_owner_silences_the_signal():
    s = item({"x:@bob": datetime(2024, 5, 20, tzinfo=UTC)},
             owners=(("author", "x:@alice"), ("author", "x:@bob")))
    assert hollow_owner({"x:i": s}, ctx()) == set()

def test_fires_when_never_active():
    assert hollow_owner({"x:i": item()}, ctx()) == {("x:i", "alpha")}

def test_fires_when_there_are_no_owners_at_all():
    """Committed work with nobody accountable is the condition at its most acute, not a
    data gap to skip past."""
    assert hollow_owner({"x:i": item(owners=())}, ctx()) == {("x:i", "alpha")}

def test_ignores_items_not_targeting_milestone():
    assert hollow_owner({"x:i": item(target=False)}, ctx()) == set()

def test_fires_for_every_targeted_stage():
    s = item()
    s.targets["beta"] = "x:v1"
    assert hollow_owner({"x:i": s}, ctx()) == {("x:i", "alpha"), ("x:i", "beta")}
