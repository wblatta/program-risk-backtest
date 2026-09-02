"""Tracking labels must be replayable point-in-time, like every other fact.

S0 asks "was the release team tracking this, as of date D". Reading today's labels
would leak the future; the label history has to enter the event stream with the
timestamps the labels were actually applied.
"""
from datetime import datetime, timezone
from core.model import Event, EventKind as K, SOURCES
from core.replay import snapshot

UTC = timezone.utc
def T(m, d=1): return datetime(2024, m, d, tzinfo=UTC)
def lab(ts, label, op, item="k8s:kep-1"):
    return Event(ts, item, K.LABEL_CHANGED, {"label": label, "op": op}, "tracking-issue")


def test_tracking_issue_is_an_accepted_source():
    assert "tracking-issue" in SOURCES


def test_label_changed_is_a_known_event_kind():
    assert K.LABEL_CHANGED in K.ALL


def test_labels_replay_to_a_point_in_time():
    evs = [lab(T(1), "tracked/yes", "add"), lab(T(3), "tracked/yes", "remove"),
           lab(T(3), "tracked/no", "add")]
    assert snapshot(evs, T(2))["k8s:kep-1"].labels == {"tracked/yes"}
    assert snapshot(evs, T(4))["k8s:kep-1"].labels == {"tracked/no"}


def test_labels_are_empty_when_nothing_was_applied():
    evs = [Event(T(1), "k8s:kep-1", K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}, "git-history")]
    assert snapshot(evs, T(2))["k8s:kep-1"].labels == set()


def test_future_label_events_are_excluded_like_every_other_event():
    """The leakage guard applies to labels too -- this is the whole reason they are events."""
    evs = [lab(T(5), "tracked/yes", "add")]
    assert snapshot(evs, T(2)).get("k8s:kep-1") is None
