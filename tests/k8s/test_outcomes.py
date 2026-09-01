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


# --- Precedence pins (structurally safe via if/elif today; pin against a future
# control-flow refactor flattening the branches) ---

def test_slipped_wins_over_status_based_dropped():
    evs = [
        tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"),
        st(T(2024, 6, 20), "withdrawn"),
        tgt(T(2024, 7, 20), "alpha", "k8s:v1.32"),
    ]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"

def test_dropped_wins_over_exception():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "withdrawn")]
    exc = {"k8s:v1.31": [ExceptionRequest(1, "code_freeze", "approved", None)]}
    assert results(outcome_events(evs, MS, exc, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"


# --- Regression: window_end must use ordinal order, not caller iteration order ---

def test_dropped_window_uses_ordinal_order_not_caller_order():
    # `nxt` must find the milestone with the smallest ordinal above M -- not just the
    # first later-ordinal milestone in whatever order the caller passed `milestones`
    # in. Deliberately shuffled here: if the lookup ever regresses to scanning the
    # caller's raw list order again, this test starts a later milestone's
    # enhancements freeze as window_end, silently widening the dropped window.
    m33 = Milestone("k8s:v1.33", 33, date(2025, 3, 1), date(2025, 4, 1),
                     {"enhancements_freeze": date(2025, 1, 10), "code_freeze": date(2025, 3, 1), "release": date(2025, 4, 1)})
    shuffled = [m33, M31, M32]
    evs = [
        tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"),
        # After M32's enhancements freeze (2024-10-04) but well before m33's
        # (2025-01-10). The correct window_end is M32's freeze, so this status
        # change is outside the window and must NOT drop the row.
        st(T(2024, 11, 1), "withdrawn"),
    ]
    assert results(outcome_events(evs, shuffled, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


# --- Evidenced outcomes: shipped requires evidence; unresolved is new ---

from adapters.k8s.delivery import DeliveryEvidence


def test_shipped_requires_delivery_evidence():
    """The v1 fallthrough is gone: no evidence means unresolved, not shipped."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    r = results(outcome_events(evs, MS, {}, TODAY, delivery={}))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "unresolved"


def test_closure_evidence_yields_shipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


def test_merge_evidence_yields_shipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=None, merges=(T(2024, 6, 15),))}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


def test_evidence_kind_is_recorded_on_the_event():
    """Every shipped row must be able to name why it was called shipped."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    out = [e for e in outcome_events(evs, MS, {}, TODAY, delivery=d)
           if e.payload["milestone_id"] == "k8s:v1.31"]
    assert out[0].payload["evidence"] == "closure"


def test_unresolved_rows_carry_no_evidence_key_value():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    out = [e for e in outcome_events(evs, MS, {}, TODAY, delivery={})
           if e.payload["milestone_id"] == "k8s:v1.31"]
    assert out[0].payload["evidence"] is None


def test_evidence_does_not_override_slipped():
    """Precedence is unchanged: a retarget outranks any delivery evidence."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 7, 20), "alpha", "k8s:v1.32")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"


def test_evidence_does_not_override_dropped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "withdrawn")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"


def test_omitting_delivery_keeps_the_v1_behaviour():
    """delivery=None is the pre-existing contract: shipped remains the fallthrough."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    r = results(outcome_events(evs, MS, {}, TODAY))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


def test_missing_cycle_start_yields_no_evidence_not_a_narrowed_window():
    """A milestone missing `start` must not fall back to `m.freeze` (code freeze, near
    the END of the cycle) as the evidence window's lower bound -- that would shrink the
    window rather than skip evidence. Evidence that would match if `freeze` were
    wrongly substituted must NOT be picked up: the row is unresolved instead."""
    m_no_start = Milestone("k8s:v1.31n", 31, date(2024, 7, 10), date(2024, 8, 13),
                            {"enhancements_freeze": date(2024, 6, 7),
                             "code_freeze": date(2024, 7, 10), "release": date(2024, 8, 13)})
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31n")]
    # Between code_freeze and release+90d -- would match under the old `or m.freeze`
    # fallback, but is before the milestone's real (unavailable) cycle start.
    d = {1: DeliveryEvidence(closed_at=T(2024, 7, 20), merges=())}
    r = results(outcome_events(evs, [m_no_start], {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31n")] == "unresolved"


def test_evidence_does_not_leak_across_stages_of_the_same_item():
    """One item, two stages at the same milestone: alpha ships with evidence, beta is
    retargeted (slipped). The slipped row's `evidence` must be None, not alpha's
    leftover evidence value -- pins the payload-site ternary against a future refactor
    that might drop it."""
    evs = [
        tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"),
        tgt(T(2024, 5, 1), "beta", "k8s:v1.31"),
        tgt(T(2024, 7, 20), "beta", "k8s:v1.32"),
    ]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    out = [e for e in outcome_events(evs, MS, {}, TODAY, delivery=d)
           if e.payload["milestone_id"] == "k8s:v1.31"]
    alpha_row = next(e for e in out if e.payload["stage"] == "alpha")
    beta_row = next(e for e in out if e.payload["stage"] == "beta")
    assert alpha_row.payload["result"] == "shipped" and alpha_row.payload["evidence"] == "closure"
    assert beta_row.payload["result"] == "slipped" and beta_row.payload["evidence"] is None
