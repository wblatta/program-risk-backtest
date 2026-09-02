from datetime import datetime, timezone
from core.model import Event, EventKind as K
from core.replay import snapshot

UTC = timezone.utc
def T(m, d=1): return datetime(2024, m, d, tzinfo=UTC)
def ev(ts, kind, payload, item="k8s:kep-1"): return Event(ts, item, kind, payload, "test")

def test_targets_history_and_timestamps():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(3), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"}),
           ev(T(3, 2), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.32"})]
    s = snapshot(evs, T(4))["k8s:kep-1"]
    assert s.targets == {"alpha": "k8s:v1.31", "beta": "k8s:v1.32"}
    assert s.target_history["alpha"] == ["k8s:v1.30", "k8s:v1.31"]
    assert s.target_set_at["alpha"] == T(3)
    assert s.created_at == T(1)

def test_as_of_excludes_future_events():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(3), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.targets == {"alpha": "k8s:v1.30"}
    assert snapshot(evs, T(1, 1))["k8s:kep-1"].targets == {"alpha": "k8s:v1.30"}  # inclusive

def test_outcomes_never_enter_snapshot():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(2), K.OUTCOME, {"milestone_id": "k8s:v1.30", "stage": "alpha", "result": "slipped"})]
    s = snapshot(evs, T(5))["k8s:kep-1"]
    assert not hasattr(s, "outcome")
    assert s.targets == {"alpha": "k8s:v1.30"}

def test_owners_add_remove_and_status():
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "add"}),
           ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:sig-node", "role": "owning", "op": "add"}),
           ev(T(2), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "remove"}),
           ev(T(2), K.STATUS_CHANGED, {"status": "implementable"})]
    s = snapshot(evs, T(3))["k8s:kep-1"]
    assert s.owners == {"author": set(), "owning": {"k8s:sig-node"}}
    assert s.status == "implementable"

def test_deps_and_activity():
    evs = [ev(T(1), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "add"}),
           ev(T(2), K.ACTIVITY, {"actor_id": "k8s:@a", "kind": "commit", "ref": "abc"}),
           ev(T(3), K.ACTIVITY, {"actor_id": "k8s:@b", "kind": "comment", "ref": "1"}),
           ev(T(4), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "remove"})]
    s = snapshot(evs, T(3, 15))["k8s:kep-1"]
    assert s.deps == {"k8s:kep-2"}
    assert s.last_activity == {"k8s:@a": T(2), "k8s:@b": T(3)}
    assert s.last_activity_any == T(3)
    assert snapshot(evs, T(5))["k8s:kep-1"].deps == set()

def test_stageless_target_uses_empty_key():
    evs = [ev(T(1), K.TARGET_SET, {"milestone_id": "gitlab:17.3"}, item="gitlab:issue-1")]
    assert snapshot(evs, T(2))["gitlab:issue-1"].targets == {"": "gitlab:17.3"}

def test_presorted_matches_unsorted_path():
    evs = [ev(T(3), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"}),
           ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"})]
    ordered = sorted(evs, key=Event.sort_key)
    assert snapshot(ordered, T(4), presorted=True) == snapshot(evs, T(4))

def test_same_timestamp_owner_add_remove_remove_wins():
    # Event.sort_key() breaks ties on json-serialized payload.
    # For OWNER_CHANGED, "add" < "remove" lexicographically,
    # so add sorts first and remove applies last — removing the owner.
    # This tie-break is conservative: ownership reads as absent, so risk signals fire.
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "add"}),
           ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "remove"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.owners == {"author": set()}

def test_same_timestamp_dep_add_remove_remove_wins():
    # Same tie-break rule for DEPENDENCY_CHANGED: remove applies last.
    evs = [ev(T(1), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "add"}),
           ev(T(1), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "remove"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.deps == set()

def test_last_activity_any_is_none_when_empty():
    # ItemState.last_activity_any returns None when no activity has been recorded.
    evs = [ev(T(1), K.TARGET_SET, {"milestone_id": "k8s:v1.30"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.last_activity == {}
    assert s.last_activity_any is None

def test_target_clear_removes_target_but_keeps_history():
    # A TARGET_SET event with op="clear" retracts a previously-set stage:
    # the stage must disappear from targets/target_set_at, but the milestone
    # it was once targeted at stays in target_history (history of what was
    # targeted is not rewritten by a later retraction).
    evs = [ev(T(1), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.31"}),
           ev(T(2), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.31", "op": "clear"})]
    s = snapshot(evs, T(3))["k8s:kep-1"]
    assert "beta" not in s.targets
    assert "beta" not in s.target_set_at
    assert s.target_history["beta"] == ["k8s:v1.31"]

def test_target_clear_then_re_add():
    # A stage cleared and later re-targeted at a new milestone comes back:
    # snapshot after the re-add reports the new milestone as the current
    # target, and target_history accumulates both the retracted and the
    # new milestone in order.
    evs = [ev(T(1), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.31"}),
           ev(T(2), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.31", "op": "clear"}),
           ev(T(3), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.32"})]
    s = snapshot(evs, T(4))["k8s:kep-1"]
    assert s.targets["beta"] == "k8s:v1.32"
    assert s.target_set_at["beta"] == T(3)
    assert s.target_history["beta"] == ["k8s:v1.31", "k8s:v1.32"]


# --- per-stage role holders (unblocks S2 gate_unassigned) ---

def test_stage_scoped_owner_events_are_recorded_per_stage():
    """PRR approval is granted per stage, so an approver on `alpha` says nothing about
    `beta`. `owners` unions them item-wide; `stage_owners` keeps them apart."""
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:p-a", "role": "prr_approver", "op": "add", "stage": "alpha"}),
           ev(T(2), K.OWNER_CHANGED, {"subject_id": "k8s:p-b", "role": "prr_approver", "op": "add", "stage": "beta"})]
    s = snapshot(evs, T(3))["k8s:kep-1"]
    assert s.stage_owners["prr_approver"]["alpha"] == {"k8s:p-a"}
    assert s.stage_owners["prr_approver"]["beta"] == {"k8s:p-b"}
    assert s.owners["prr_approver"] == {"k8s:p-a", "k8s:p-b"}   # item-wide view unchanged

def test_stage_scoped_owner_removal_clears_only_that_stage():
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:p-a", "role": "prr_approver", "op": "add", "stage": "alpha"}),
           ev(T(2), K.OWNER_CHANGED, {"subject_id": "k8s:p-b", "role": "prr_approver", "op": "add", "stage": "beta"}),
           ev(T(3), K.OWNER_CHANGED, {"subject_id": "k8s:p-a", "role": "prr_approver", "op": "remove", "stage": "alpha"})]
    s = snapshot(evs, T(4))["k8s:kep-1"]
    assert s.stage_owners["prr_approver"]["alpha"] == set()
    assert s.stage_owners["prr_approver"]["beta"] == {"k8s:p-b"}

def test_owner_events_without_a_stage_do_not_enter_stage_owners():
    """`owning`/`author` are item-wide roles and carry no stage. Inventing one would
    make a stage look covered because some other stage was."""
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:sig-node", "role": "owning", "op": "add"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.owners["owning"] == {"k8s:sig-node"}
    assert "owning" not in s.stage_owners


# --- bot activity is kept, but kept apart ---

def test_bot_activity_does_not_count_as_human_activity():
    """A staleness bot commenting on a dead item is not work on it. Counting it would
    make abandoned enhancements read as alive -- the exact failure the silence signals
    exist to catch."""
    evs = [ev(T(5), K.ACTIVITY, {"actor_id": "k8s:@stale-bot", "kind": "commented", "bot": True})]
    s = snapshot(evs, T(6))["k8s:kep-1"]
    assert s.last_activity == {}
    assert s.last_activity_any is None
    assert s.last_activity_bot == {"k8s:@stale-bot": T(5)}

def test_unflagged_activity_is_treated_as_human():
    """Git-derived activity carries no `bot` key; it is a real commit and must count."""
    evs = [ev(T(5), K.ACTIVITY, {"actor_id": "k8s:unknown", "kind": "commit"})]
    assert snapshot(evs, T(6))["k8s:kep-1"].last_activity_any == T(5)
