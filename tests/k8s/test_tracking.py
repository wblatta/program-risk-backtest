"""Tracking-issue parsing. Pure functions over API payloads; no network."""
from datetime import datetime, timezone
from adapters.k8s.tracking import parse_issue, parse_timeline, labels_at, IssueMeta, LabelEvent

UTC = timezone.utc
def T(m, d): return datetime(2024, m, d, 12, 0, tzinfo=UTC)

ISSUE = {"number": 3257, "state": "open", "closed_at": None,
         "milestone": {"title": "v1.37"},
         "labels": [{"name": "sig/auth"}, {"name": "stage/stable"}]}

TIMELINE = [
    {"event": "labeled",   "created_at": "2024-03-01T12:00:00Z", "label": {"name": "tracked/yes"}},
    {"event": "commented", "created_at": "2024-03-05T12:00:00Z"},
    {"event": "unlabeled", "created_at": "2024-04-01T12:00:00Z", "label": {"name": "tracked/yes"}},
    {"event": "labeled",   "created_at": "2024-05-01T12:00:00Z", "label": {"name": "stage/beta"}},
]


def test_parse_issue_extracts_state_milestone_and_labels():
    m = parse_issue(ISSUE)
    assert m == IssueMeta(number=3257, state="open", closed_at=None,
                          milestone="v1.37", labels=("sig/auth", "stage/stable"))


def test_parse_issue_reads_closed_at_as_utc_aware():
    m = parse_issue({**ISSUE, "state": "closed", "closed_at": "2024-08-13T09:30:00Z"})
    assert m.closed_at == datetime(2024, 8, 13, 9, 30, tzinfo=UTC)
    assert m.closed_at.tzinfo is not None


def test_parse_timeline_keeps_only_label_events_in_order():
    evs = parse_timeline(TIMELINE)
    assert evs == [LabelEvent(T(3, 1), "tracked/yes", "add"),
                   LabelEvent(T(4, 1), "tracked/yes", "remove"),
                   LabelEvent(T(5, 1), "stage/beta", "add")]


def test_labels_at_is_a_point_in_time_replay():
    evs = parse_timeline(TIMELINE)
    assert labels_at(evs, T(2, 1)) == set()
    assert labels_at(evs, T(3, 15)) == {"tracked/yes"}
    assert labels_at(evs, T(4, 15)) == set()
    assert labels_at(evs, T(6, 1)) == {"stage/beta"}


def test_labels_at_boundary_is_inclusive():
    """Matches snapshot()'s as_of convention: a label added exactly at ts is present."""
    evs = parse_timeline(TIMELINE)
    assert labels_at(evs, T(3, 1)) == {"tracked/yes"}


def test_malformed_timeline_entries_are_skipped_not_fatal():
    evs = parse_timeline([{"event": "labeled", "created_at": "2024-03-01T12:00:00Z"},
                          {"event": "labeled", "label": {"name": "x"}},
                          {"event": "labeled", "created_at": "nonsense", "label": {"name": "y"}},
                          {"event": "labeled", "created_at": "2024-03-02T12:00:00Z", "label": {"name": "ok"}}])
    assert evs == [LabelEvent(datetime(2024, 3, 2, 12, 0, tzinfo=UTC), "ok", "add")]


def test_fetch_skips_issues_already_on_disk(tmp_path):
    """A cached issue costs no request; that is what makes a re-run affordable."""
    from adapters.k8s.tracking import fetch_tracking
    calls = []

    class C:
        remaining = 5000
        def get_json(self, url):
            calls.append(url)
            return {"number": 7, "state": "open", "labels": []} if "timeline" not in url else []

    fetch_tracking(tmp_path, [7], C())
    assert len(calls) == 2, "first pass fetches issue + timeline"
    fetch_tracking(tmp_path, [7], C())
    assert len(calls) == 2, "second pass must read from disk, not the API"


def test_fetch_stops_cleanly_when_the_budget_runs_out(tmp_path):
    """Partial progress is kept on disk so the next run resumes instead of restarting."""
    from adapters.k8s.tracking import fetch_tracking
    from adapters.k8s.github import RateLimitError

    class C:
        remaining = 5000
        def __init__(self): self.n = 0
        def get_json(self, url):
            self.n += 1
            if self.n > 2:
                raise RateLimitError("budget exhausted")
            return {"number": 1, "state": "open", "labels": []} if "timeline" not in url else []

    got, stopped = fetch_tracking(tmp_path, [1, 2, 3], C())
    assert stopped is True, "should report that it stopped early"
    assert set(got) == {1}, "the one complete issue is kept"
    assert (tmp_path / "issues" / "1.json").exists()


# --- real actors for activity (spec S1 needs owner-scoped activity, not anonymous) ---

from adapters.k8s.tracking import ACTIVITY_EVENTS, actor_activity_events, actor_id


def _tl(event, login, when="2024-03-01T00:00:00Z", **extra):
    return {"event": event, "created_at": when, "actor": {"login": login}, **extra}


def test_comments_become_activity_with_a_real_actor():
    evs = actor_activity_events("k8s:kep-1", [_tl("commented", "alice")])
    assert len(evs) == 1
    assert evs[0].kind == "activity" and evs[0].source == "tracking-issue"
    assert evs[0].payload["actor_id"] == "k8s:@alice"
    assert evs[0].payload["kind"] == "commented"

def test_cross_references_count_as_activity():
    """A PR linked to the tracking issue is work on the item, by the person who linked it."""
    assert [e.payload["actor_id"] for e in actor_activity_events("k8s:kep-1", [_tl("cross-referenced", "bob")])] == ["k8s:@bob"]

def test_bookkeeping_events_are_not_activity():
    """`labeled` is the release team's process, not work on the enhancement -- counting
    it would let a bot's housekeeping make an abandoned item look alive."""
    assert actor_activity_events("k8s:kep-1", [_tl("labeled", "k8s-ci-robot", label={"name": "tracked/yes"})]) == []

def test_mentioned_and_subscribed_are_not_activity():
    """`mentioned` records that someone was named by another person; `subscribed` is a
    notification preference. Neither is an action taken on the work."""
    tl = [_tl("mentioned", "carol"), _tl("subscribed", "carol")]
    assert actor_activity_events("k8s:kep-1", tl) == []

def test_entries_without_an_actor_are_skipped():
    assert actor_activity_events("k8s:kep-1", [{"event": "commented", "created_at": "2024-03-01T00:00:00Z"}]) == []

def test_entries_without_a_timestamp_are_skipped():
    assert actor_activity_events("k8s:kep-1", [{"event": "commented", "actor": {"login": "alice"}}]) == []

def test_falls_back_to_user_when_actor_is_absent():
    """Comment entries carry the author under `user`; most other types use `actor`."""
    tl = [{"event": "commented", "created_at": "2024-03-01T00:00:00Z", "user": {"login": "dave"}}]
    assert [e.payload["actor_id"] for e in actor_activity_events("k8s:kep-1", tl)] == ["k8s:@dave"]

def test_output_is_sorted_and_bots_are_kept_but_marked():
    """Bots act on real timestamps and excluding them here would silently change what
    `activity` means. Mark them and let the signal decide."""
    tl = [_tl("commented", "zoe", "2024-05-01T00:00:00Z"), _tl("commented", "k8s-ci-robot", "2024-04-01T00:00:00Z")]
    evs = actor_activity_events("k8s:kep-1", tl)
    assert [e.ts.month for e in evs] == [4, 5]
    assert evs[0].payload["bot"] is True and evs[1].payload["bot"] is False

def test_activity_events_vocabulary_is_explicit():
    assert "commented" in ACTIVITY_EVENTS and "labeled" not in ACTIVITY_EVENTS


def test_actor_id_matches_person_id():
    """The two id-minting paths must agree, or an owner-scoped signal silently matches
    nothing. kep.yaml carries `@alice`; the GitHub API returns `alice`; both must land on
    the same id."""
    from adapters.k8s.events import person_id
    assert actor_id("Alice") == person_id("@Alice") == "k8s:@alice"
    assert actor_id("@Alice") == person_id("@alice")
