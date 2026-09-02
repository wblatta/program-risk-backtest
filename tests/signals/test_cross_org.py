from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.cross_org import cross_org

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)})
CTX = Context(datetime(2024, 6, 20, tzinfo=UTC), M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})


def _item(owning=("x:sig-a",), participating=(), stages=("alpha",)):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    for st in stages:
        s.targets[st] = "x:v2"
    if owning:
        s.owners["owning"] = set(owning)
    if participating:
        s.owners["participating"] = set(participating)
    return s


def test_quiet_for_a_single_org():
    assert cross_org({"x:i": _item()}, CTX) == set()

def test_fires_when_a_second_org_participates():
    assert cross_org({"x:i": _item(participating=("x:sig-b",))}, CTX) == {("x:i", "alpha")}

def test_participating_org_identical_to_owner_is_not_a_second_org():
    """K8s KEPs routinely list the owning SIG among participating-sigs. Counting the
    set union rather than the list length keeps that from reading as coordination."""
    assert cross_org({"x:i": _item(participating=("x:sig-a",))}, CTX) == set()

def test_fires_for_every_targeted_stage():
    """Org composition is item-wide, so a firing names every row it covers."""
    s = _item(participating=("x:sig-b",), stages=("alpha", "beta"))
    assert cross_org({"x:i": s}, CTX) == {("x:i", "alpha"), ("x:i", "beta")}

def test_quiet_for_items_not_targeting_this_milestone():
    s = _item(participating=("x:sig-b",))
    s.targets["alpha"] = "x:v3"
    assert cross_org({"x:i": s}, CTX) == set()

def test_participating_without_a_recorded_owner_still_counts_orgs():
    assert cross_org({"x:i": _item(owning=(), participating=("x:sig-b", "x:sig-c"))}, CTX) == {("x:i", "alpha")}
