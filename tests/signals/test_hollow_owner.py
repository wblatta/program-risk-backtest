from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.hollow_owner import hollow_owner

UTC = timezone.utc
M = Milestone("x:v1", 1, date(2024, 7, 10), date(2024, 8, 13), {})
def ctx(as_of): return Context(as_of, M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})

def item(last_activity=None, target=True):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    if target:
        s.targets["alpha"] = "x:v1"
    if last_activity:
        s.last_activity["x:unknown"] = last_activity
    return s

def test_fires_when_no_activity_in_N_weeks():
    s = item(last_activity=datetime(2024, 3, 1, tzinfo=UTC))
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == {"x:i"}

def test_quiet_when_recent_activity():
    s = item(last_activity=datetime(2024, 5, 20, tzinfo=UTC))
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == set()

def test_fires_when_never_active():
    assert hollow_owner({"x:i": item()}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == {"x:i"}

def test_ignores_items_not_targeting_milestone():
    s = item(target=False)
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == set()
