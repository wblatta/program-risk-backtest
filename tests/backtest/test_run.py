from datetime import date, datetime, timezone
from backtest.run import run_backtest, Row
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone

UTC = timezone.utc
def T(m, d): return datetime(2024, m, d, tzinfo=UTC)
M31 = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13),
                {"start": date(2024, 5, 13), "enhancements_freeze": date(2024, 6, 7), "code_freeze": date(2024, 7, 10), "release": date(2024, 8, 13)})
CFG = AdapterConfig("x", ())

def ev(ts, kind, payload, item="x:i1"): return Event(ts, item, kind, payload, "t")

def always(states, ctx): return set(states)
def never(states, ctx): return set()
def after_june(states, ctx): return set(states) if ctx.as_of >= T(6, 1) else set()

def base_events():
    return [ev(T(5, 1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "x:v31"}),
            ev(T(5, 1), K.OWNER_CHANGED, {"subject_id": "x:org-a", "role": "owning", "op": "add"}),
            ev(T(8, 13), K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"})]

def test_rows_and_outcomes_join():
    rows = run_backtest(base_events(), [M31], [], CFG, {"always": always, "never": never}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert len(rows) == 1
    r = rows[0]
    assert (r.item_id, r.stage, r.milestone_id, r.org_id, r.outcome) == ("x:i1", "alpha", "x:v31", "x:org-a", "slipped")
    assert r.first_fired["never"] is None
    assert r.first_fired["always"] is not None and r.first_fired["always"].date() <= date(2024, 5, 20)

def test_first_fired_is_earliest_weekly_snapshot():
    rows = run_backtest(base_events(), [M31], [], CFG, {"aj": after_june}, {"N": 8, "M": 4, "K": 3, "L": 4})
    ff = rows[0].first_fired["aj"]
    assert ff is not None and T(6, 1) <= ff < T(6, 8)

def test_outcome_before_as_of_is_not_leaked():
    evs = base_events()
    def sees_outcome(states, ctx):
        return {i for i, s in states.items() if hasattr(s, "outcome")}
    rows = run_backtest(evs, [M31], [], CFG, {"leak": sees_outcome}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert rows[0].first_fired["leak"] is None

def test_unscheduled_milestones_ignored():
    m = Milestone("x:v32", 32, None, None, {})
    assert run_backtest(base_events(), [M31, m], [], CFG, {}, {"N": 8, "M": 4, "K": 3, "L": 4})[0].milestone_id == "x:v31"
