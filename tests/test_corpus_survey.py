import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.corpus_survey import label_families, survey_repo, verdict


_MISSING = object()


class FakeClient:
    """Stands in for the GitHub API so the survey's logic is testable offline.

    `repo=None` means the fetch failed (what the real client returns on a 404); an empty
    dict means a valid response that happens to be sparse. The survey must tell them apart.
    """
    def __init__(self, repo=_MISSING, milestones=None, issues=None, timelines=None):
        repo = {} if repo is _MISSING else repo
        self.repo, self.milestones = repo, milestones or []
        self.issues, self.timelines = issues or [], timelines or {}
        self.calls = 0

    def get(self, url):
        self.calls += 1
        if "/timeline" in url:
            n = int(url.split("/issues/")[1].split("/")[0])
            return self.timelines.get(n, []), {}
        if "/milestones" in url:
            return self.milestones, {}
        if "/issues?" in url:
            return self.issues, {}
        return self.repo, {}


def issue(n, milestone=None, labels=()):
    return {"number": n, "milestone": {"title": milestone} if milestone else None,
            "labels": [{"name": l} for l in labels]}


def moved(n):    return [{"event": "milestoned"}, {"event": "demilestoned"}, {"event": "milestoned"}]
def stayed(n):   return [{"event": "milestoned"}]


def test_detects_retargeting():
    c = FakeClient({"stargazers_count": 1}, [{"due_on": "2024-01-01"}],
                   [issue(1, "v1"), issue(2, "v1")], {1: moved(1), 2: stayed(2)})
    row = survey_repo(c, "o/r")
    assert row["retarget_rate"] == 0.5 and row["timelines_checked"] == 2

def test_rejects_a_repo_with_no_retargeting():
    """The disqualifying case: work is milestoned once and never moved, so there is no
    slip to predict and an adapter would produce a backtest with no positive class."""
    c = FakeClient(milestones=[{"due_on": "x"}], issues=[issue(1, "v1")], timelines={1: stayed(1)})
    assert survey_repo(c, "o/r")["verdict"].startswith("REJECT")

def test_flags_a_thin_milestoned_population():
    """A retarget rate computed on a handful of issues is not evidence of a positive class."""
    c = FakeClient(milestones=[{"due_on": "x"}], issues=[issue(1, "v1")], timelines={1: moved(1)})
    assert "thin milestoned population" in survey_repo(c, "o/r")["verdict"]

def test_notes_a_missing_release_calendar_without_rejecting():
    c = FakeClient(milestones=[{"due_on": None}], issues=[issue(1, "v1")], timelines={1: moved(1)})
    v = survey_repo(c, "o/r")["verdict"]
    assert "calendar needed" in v and not v.startswith("REJECT")

def test_flags_missing_org_units():
    """Without team/area labels, cross_org and org_overcommitted have nothing to group by."""
    issues = [issue(i, "v1", ["kind/bug"]) for i in range(1, 25)]
    c = FakeClient(milestones=[{"due_on": "x"}], issues=issues,
                   timelines={i: moved(i) for i in range(1, 25)})
    assert "no org units" in survey_repo(c, "o/r")["verdict"]


def test_flags_a_missing_scope_label():
    """Without a scope-label analogue the new corpus cannot reproduce S0 -- the control
    this project measures every signal against."""
    issues = [issue(i, "v1", ["area/core"]) for i in range(1, 25)]
    c = FakeClient(milestones=[{"due_on": "x"}], issues=issues,
                   timelines={i: moved(i) for i in range(1, 25)})
    assert "no S0 control" in survey_repo(c, "o/r")["verdict"]

def test_strong_verdict_needs_all_four():
    issues = [issue(i, "v1", ["sig/node", "tracked/yes"]) for i in range(1, 25)]
    c = FakeClient(milestones=[{"due_on": "x"}], issues=issues,
                   timelines={i: moved(i) for i in range(1, 25)})
    row = survey_repo(c, "o/r")
    assert row["verdict"].startswith("STRONG")
    assert "sig" in row["org_families"] and "tracked" in row["scope_labels"]

def test_unreadable_repo_does_not_abort_the_survey():
    c = FakeClient(repo=None)
    row = survey_repo(c, "o/gone")
    assert row["error"] and row["verdict"] == "unreadable"

def test_label_families_groups_by_prefix():
    fams = label_families([issue(1, labels=["sig/node", "sig/api", "kind/bug"])])
    assert fams["sig"] == 2 and fams["kind"] == 1


def test_retarget_sample_comes_from_milestoned_issues_not_recent_ones():
    """Sampling `sort=updated` skews to new, untriaged issues, so a project that
    milestones its planned work heavily can still show zero milestoned issues in a recent
    page. The retarget measure must query issues that HAVE a milestone (`milestone=*`),
    or it under-reports exactly the corpora worth finding."""
    seen = []

    class Recording(FakeClient):
        def get(self, url):
            seen.append(url)
            if "milestone=%2A" in url or "milestone=*" in url:
                return [issue(1, "v1")], {}
            return super().get(url)

    c = Recording(milestones=[{"due_on": "x"}], issues=[issue(9)], timelines={1: moved(1)})
    survey_repo(c, "o/r")
    assert any("milestone=*" in u or "milestone=%2A" in u for u in seen), seen
    
def test_pull_requests_do_not_count_toward_coverage():
    """A busy repo's recent page is mostly PRs; counting them collapses coverage."""
    issues = [issue(1, "v1"), {**issue(2), "pull_request": {"url": "x"}}]
    c = FakeClient(milestones=[{"due_on": "x"}], issues=issues, timelines={1: moved(1)})
    assert survey_repo(c, "o/r")["issues_sampled"] == 1


def test_missing_due_dates_is_a_note_not_a_downgrade():
    """Kubernetes' own release calendar does not come from GitHub milestones -- it is
    built from the sig-release repo into `adapters/k8s/calendar.yaml`. A candidate whose
    milestones lack `due_on` can supply a calendar the same way, so this must not be
    scored as disqualifying."""
    issues = [issue(i, "v1", ["area/core"]) for i in range(1, 5)]
    c = FakeClient(milestones=[{"due_on": None}], issues=issues,
                   timelines={i: moved(i) for i in range(1, 5)})
    v = survey_repo(c, "o/r")["verdict"]
    assert not v.startswith("REJECT") and "calendar needed" in v
