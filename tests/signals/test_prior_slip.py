from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.prior_slip import prior_slip

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {})
CTX = Context(datetime(2024, 6, 1, tzinfo=UTC), M, {M.id: M}, [], AdapterConfig("x", ()))

def test_fires_when_stage_was_retargeted_before():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_history["alpha"] = ["x:v1", "x:v2"]
    assert prior_slip({"x:i": s}, CTX) == {("x:i", "alpha")}

def test_quiet_on_first_target():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_history["alpha"] = ["x:v2"]
    assert prior_slip({"x:i": s}, CTX) == set()

def test_other_stage_history_does_not_count():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["beta"] = "x:v2"; s.target_history["beta"] = ["x:v2"]; s.target_history["alpha"] = ["x:v0", "x:v1"]
    assert prior_slip({"x:i": s}, CTX) == set()
