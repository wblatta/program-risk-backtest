from datetime import date, datetime, timezone
from adapters.k8s.exceptions import ExceptionRequest
from adapters.k8s.outcomes import outcome_events, DROP_STATUSES
from core.model import Event, EventKind as K, Milestone

UTC = timezone.utc
def T(y, m, d): return datetime(y, m, d, tzinfo=UTC)
M31 = Milestone("k8s:v1.31", 31, date(2024, 7, 10), date(2024, 8, 13),
                {"start": date(2024, 5, 13), "enhancements_freeze": date(2024, 6, 7), "code_freeze": date(2024, 7, 10), "release": date(2024, 8, 13)})
M32 = Milestone("k8s:v1.32", 32, date(2024, 11, 8), date(2024, 12, 11),
                {"start": date(2024, 9, 9), "enhancements_freeze": date(2024, 10, 4), "code_freeze": date(2024, 11, 8), "release": date(2024, 12, 11)})
M33 = Milestone("k8s:v1.33", 33, None, None, {})
MS = [M31, M32, M33]
TODAY = date(2025, 1, 1)

def tgt(ts, stage, ms, item="k8s:kep-1"): return Event(ts, item, K.TARGET_SET, {"stage": stage, "milestone_id": ms}, "git-history")
def clr(ts, stage, ms, item="k8s:kep-1"): return Event(ts, item, K.TARGET_SET, {"stage": stage, "milestone_id": ms, "op": "clear"}, "git-history")
def st(ts, s, item="k8s:kep-1"): return Event(ts, item, K.STATUS_CHANGED, {"status": s}, "git-history")
def results(evs): return {(e.item_id, e.payload["stage"], e.payload["milestone_id"]): e.payload["result"] for e in evs}


# --- brief's baseline cases ---

def test_slipped_when_retargeted_later():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 7, 20), "alpha", "k8s:v1.32")]
    out = outcome_events(evs, MS, {}, TODAY)
    assert results(out)[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"
    assert all(e.ts.date() == date(2024, 8, 13) and e.source == "derived" for e in out if e.payload["milestone_id"] == "k8s:v1.31")

def test_shipped_when_nothing_changes():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"

def test_dropped_on_withdrawal():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "withdrawn")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"

def test_exception_granted_and_denied():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 5, 1), "beta", "k8s:v1.31", item="k8s:kep-2")]
    exc = {"k8s:v1.31": [ExceptionRequest(1, "code_freeze", "approved", None), ExceptionRequest(2, "code_freeze", "denied", None)]}
    r = results(outcome_events(evs, MS, exc, TODAY))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "exception_granted"
    assert r[("k8s:kep-2", "beta", "k8s:v1.31")] == "exception_denied"

def test_target_added_after_enhancements_freeze_is_not_a_row():
    evs = [tgt(T(2024, 6, 20), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY)) == {}

def test_unreleased_and_unscheduled_milestones_skipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.33"), tgt(T(2024, 5, 1), "beta", "k8s:v1.32")]
    assert results(outcome_events(evs, MS, {}, date(2024, 11, 1))) == {}


# --- Ruling 1: DROP_STATUSES gains "superseded", must NOT gain "removed" ---

def test_drop_statuses_vocabulary():
    assert DROP_STATUSES == {"withdrawn", "rejected", "deferred", "replaced", "superseded"}
    assert "removed" not in DROP_STATUSES

def test_dropped_on_superseded():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "superseded")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"

def test_removed_status_does_not_drop():
    # "removed" records that the shipped feature was later removed from Kubernetes,
    # not that the KEP was abandoned -- it must not relabel a real success as dropped.
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "removed")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


# --- Ruling 2: a TARGET_SET clear for the same stage/milestone is evidence of dropped ---

def test_dropped_on_target_cleared():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), clr(T(2024, 6, 20), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"

def test_clear_for_different_stage_does_not_drop_this_row():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), clr(T(2024, 6, 20), "beta", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"

def test_clear_outside_window_does_not_drop():
    # The clear lands after the *next* milestone's enhancements freeze -- outside the window.
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), clr(T(2024, 12, 1), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"

def test_clear_then_later_retarget_is_slipped_not_dropped():
    # A KEP that clears a stage and re-adds it at a later milestone: rule 1 (slipped)
    # must win over the clear-based dropped evidence.
    evs = [
        tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"),
        clr(T(2024, 6, 20), "alpha", "k8s:v1.31"),
        tgt(T(2024, 7, 20), "alpha", "k8s:v1.32"),
    ]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"

def test_clear_is_not_misread_as_a_retarget_via_its_milestone_id():
    # A clear event carries a milestone_id (the milestone being cleared), which can point at
    # a *higher*-ordinal milestone than the row under evaluation. A retarget check that
    # compares ordinals without also checking "op" would misread this clear as a move to
    # v1.32 and wrongly report "slipped". It must instead fall through (no dropped match
    # either, since the clear's milestone_id != this row's milestone) to "shipped".
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), clr(T(2024, 6, 20), "alpha", "k8s:v1.32")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"
