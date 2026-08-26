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
