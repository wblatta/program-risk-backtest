from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.late_target import late_target

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)})
CTX = Context(datetime(2024, 6, 8, tzinfo=UTC), M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})

def _item(set_at):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_set_at["alpha"] = set_at
    return s

def test_fires_when_target_set_within_K_weeks_of_commitment():
    assert late_target({"x:i": _item(datetime(2024, 5, 25, tzinfo=UTC))}, CTX) == {"x:i"}

def test_quiet_when_set_early():
    assert late_target({"x:i": _item(datetime(2024, 4, 1, tzinfo=UTC))}, CTX) == set()

def test_falls_back_to_freeze_without_enhancements_freeze():
    m = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {})
    c = Context(datetime(2024, 7, 1, tzinfo=UTC), m, {m.id: m}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})
    assert late_target({"x:i": _item(datetime(2024, 6, 25, tzinfo=UTC))}, c) == {"x:i"}
