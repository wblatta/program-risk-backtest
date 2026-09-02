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
    c = FakeClient({}, [{"due_on": "x"}], [issue(1, "v1")], {1: stayed(1)})
    assert survey_repo(c, "o/r")["verdict"].startswith("REJECT")

def test_flags_low_milestone_coverage():
    issues = [issue(1, "v1")] + [issue(i) for i in range(2, 12)]
    c = FakeClient({}, [{"due_on": "x"}], issues, {1: moved(1)})
    assert "rarely applied" in survey_repo(c, "o/r")["verdict"]

def test_flags_a_missing_release_calendar():
    c = FakeClient({}, [{"due_on": None}], [issue(1, "v1")], {1: moved(1)})
    assert "no release calendar" in survey_repo(c, "o/r")["verdict"]

def test_flags_a_missing_scope_label():
    """Without a scope-label analogue the new corpus cannot reproduce S0 -- the control
    this project measures every signal against."""
    c = FakeClient({}, [{"due_on": "x"}], [issue(1, "v1", ["kind/bug"])], {1: moved(1)})
    assert "no S0 control" in survey_repo(c, "o/r")["verdict"]

def test_strong_verdict_needs_all_four():
    issues = [issue(i, "v1", ["sig/node", "tracked/yes"]) for i in range(1, 5)]
    c = FakeClient({}, [{"due_on": "x"}], issues, {i: moved(i) for i in range(1, 5)})
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
