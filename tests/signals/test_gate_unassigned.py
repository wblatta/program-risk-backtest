from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.gate_unassigned import gate_unassigned

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)})
CFG = AdapterConfig("x", ("prr_approver",))
PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}


def ctx(as_of, cfg=CFG, m=M):
    return Context(as_of, m, {m.id: m}, [], cfg, dict(PARAMS))


def _item(stages=("alpha",), approved=()):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    for st in stages:
        s.targets[st] = "x:v2"
    for st in approved:
        s.stage_owners.setdefault("prr_approver", {}).setdefault(st, set()).add("x:p-a")
    return s


# freeze is 2024-07-10; M=4 weeks means the window opens 2024-06-12.

def test_fires_inside_the_window_when_the_required_role_is_unheld():
    assert gate_unassigned({"x:i": _item()}, ctx(datetime(2024, 6, 20, tzinfo=UTC))) == {("x:i", "alpha")}

def test_quiet_outside_the_window():
    """Before the window there is still time to assign; an unheld gate is not yet news."""
    assert gate_unassigned({"x:i": _item()}, ctx(datetime(2024, 5, 1, tzinfo=UTC))) == set()

def test_quiet_when_the_role_is_held_for_that_stage():
    assert gate_unassigned({"x:i": _item(approved=("alpha",))}, ctx(datetime(2024, 6, 20, tzinfo=UTC))) == set()

def test_fires_per_stage_not_per_item():
    """The whole reason S2 needed the widened Signal contract: approval is granted per
    stage, so a covered alpha must not silence an uncovered beta."""
    s = _item(stages=("alpha", "beta"), approved=("alpha",))
    assert gate_unassigned({"x:i": s}, ctx(datetime(2024, 6, 20, tzinfo=UTC))) == {("x:i", "beta")}

def test_quiet_for_stages_targeting_another_milestone():
    s = _item(stages=("alpha",))
    s.targets["beta"] = "x:v3"
    assert gate_unassigned({"x:i": s}, ctx(datetime(2024, 6, 20, tzinfo=UTC))) == {("x:i", "alpha")}

def test_no_required_roles_configured_means_no_firings():
    """A corpus without a gate role must not have one invented for it."""
    assert gate_unassigned({"x:i": _item()}, ctx(datetime(2024, 6, 20, tzinfo=UTC), cfg=AdapterConfig("x", ()))) == set()

def test_any_unheld_required_role_fires():
    cfg = AdapterConfig("x", ("prr_approver", "second_gate"))
    s = _item(approved=("alpha",))   # prr_approver held, second_gate not
    assert gate_unassigned({"x:i": s}, ctx(datetime(2024, 6, 20, tzinfo=UTC), cfg=cfg)) == {("x:i", "alpha")}

def test_unscheduled_milestone_is_quiet():
    """Without a freeze date there is no window to be inside of."""
    m = Milestone("x:v2", 2, None, None, {})
    assert gate_unassigned({"x:i": _item()}, ctx(datetime(2024, 6, 20, tzinfo=UTC), m=m)) == set()
