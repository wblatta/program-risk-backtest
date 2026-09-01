from datetime import date, datetime, timedelta, timezone
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

def test_outcome_at_freeze_boundary_excluded_after_included():
    # Pins the strict `>` in the outcome join: an outcome exactly at freeze_dt must NOT
    # be joined (it's within the window the signal was allowed to speak in); an outcome
    # one second later must be. A regression to `>=` would pass every other test.
    evs_base = [ev(T(5, 1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "x:v31"})]
    FREEZE_DT = datetime(2024, 7, 10, 23, 59, 59, tzinfo=UTC)

    at_boundary = evs_base + [ev(FREEZE_DT, K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"})]
    rows = run_backtest(at_boundary, [M31], [], CFG, {}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert rows[0].outcome is None

    just_after = evs_base + [ev(FREEZE_DT + timedelta(seconds=1), K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"})]
    rows2 = run_backtest(just_after, [M31], [], CFG, {}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert rows2[0].outcome == "slipped"

def test_prior_outcomes_includes_exact_as_of_boundary():
    # Pins the `bisect_right` slice feeding Context.prior_outcomes: an outcome timestamped
    # exactly at a weekly as_of must be visible that same week (ts <= as_of), never a week
    # before, and must never leak an outcome with ts > as_of. A regression to `bisect_left`
    # would delay visibility by one week without breaking any other test.
    EXACT = datetime(2024, 6, 3, 23, 59, 59, tzinfo=UTC)   # falls exactly on the weekly grid from start=5/13
    BEFORE = datetime(2024, 5, 27, 23, 59, 59, tzinfo=UTC)
    AFTER = datetime(2024, 6, 10, 23, 59, 59, tzinfo=UTC)
    evs = [ev(T(5, 1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "x:v31"}),
           ev(EXACT, K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"})]
    seen: dict = {}
    def collect(states, ctx):
        seen[ctx.as_of] = [e.ts for e in ctx.prior_outcomes]
        return set()
    run_backtest(evs, [M31], [], CFG, {"collect": collect}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert seen[BEFORE] == []
    assert seen[EXACT] == [EXACT]
    assert seen[AFTER] == [EXACT]
    assert all(ts <= as_of for as_of, tss in seen.items() for ts in tss)

def test_context_calendar_excludes_future_milestones():
    # Pins the leakage boundary on Context.milestones_by_id (see signals/base.py). The
    # calendar handed to a signal must contain the milestone being scored and every
    # earlier one, and must NOT contain a higher-ordinal milestone -- whose stored
    # freeze/release dates are post-hoc actuals, not the schedule as published at the
    # time. Without the filter in run_backtest every milestone is visible at every
    # as_of and no other test in this file notices.
    past = Milestone("x:v30", 30, date(2024, 3, 10), date(2024, 4, 13),
                     {"enhancements_freeze": date(2024, 2, 7)})
    future = Milestone("x:v32", 32, date(2024, 11, 10), date(2024, 12, 13),
                       {"enhancements_freeze": date(2024, 10, 7)})
    # keyed by the milestone being scored: v30 and v32 are themselves scheduled cycles,
    # so each legitimately sees itself -- only the cross-cycle visibility is the leak.
    seen: dict[str, set[str]] = {}

    def collect(states, ctx):
        seen.setdefault(ctx.milestone.id, set()).update(ctx.milestones_by_id)
        # the ordinal invariant itself, asserted at every weekly snapshot
        assert all(m.ordinal <= ctx.milestone.ordinal for m in ctx.milestones_by_id.values())
        return set()

    run_backtest(base_events(), [past, M31, future], [], CFG, {"collect": collect},
                 {"N": 8, "M": 4, "K": 3, "L": 4})
    # scoring v31: v30 (earlier) and v31 (itself) visible, v32 (later) not
    assert seen["x:v31"] == {"x:v30", "x:v31"}
    # and the earliest cycle cannot see either of its successors
    assert seen["x:v30"] == {"x:v30"}
