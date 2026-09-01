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
