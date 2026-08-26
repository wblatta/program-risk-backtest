import os
import subprocess
from datetime import datetime, timezone
from adapters.k8s.git_history import list_kep_dirs, file_versions, dir_activity
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(d): return datetime(2024, 1, d, 12, 0, tzinfo=UTC)

def test_file_versions_oldest_first_with_commit_times(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "status: provisional\n"}),
        (T(2), {"README.md": "unrelated\n"}),
        (T(3), {"keps/sig-a/100-x/kep.yaml": "status: implementable\n"}),
    ])
    vs = file_versions(repo, "keps/sig-a/100-x/kep.yaml")
    assert [v.ts for v in vs] == [T(1), T(3)]
    assert [v.text for v in vs] == ["status: provisional\n", "status: implementable\n"]
    assert all(len(v.sha) == 40 for v in vs)

def test_list_kep_dirs_only_those_with_kep_yaml(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "a", "keps/sig-b/200-y/kep.yaml": "b",
                "keps/sig-b/README.md": "no", "keps/prod-readiness/sig-a/100.yaml": "prr"}),
    ])
    assert list_kep_dirs(repo) == ["keps/sig-a/100-x", "keps/sig-b/200-y"]

def test_dir_activity_lists_every_commit_touching_dir(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "a"}),
        (T(2), {"keps/sig-a/100-x/README.md": "design"}),
        (T(3), {"keps/sig-b/200-y/kep.yaml": "b"}),
    ])
    acts = dir_activity(repo, "keps/sig-a/100-x")
    assert [a[0] for a in acts] == [T(1), T(2)]
    assert all(a[2] == "t@example.com" for a in acts)

def test_missing_path_gives_empty(tmp_path):
    repo = make_git_repo(tmp_path / "r", [(T(1), {"x": "y"})])
    assert file_versions(repo, "nope/kep.yaml") == []

def test_uses_committer_time_not_author_time(tmp_path):
    # Simulates a rebase/squash: authored in January, but only became true on
    # main when committed (merged) in June. file_versions must report June.
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "status: provisional\n"}),
    ])
    committer_ts = datetime(2024, 6, 15, 9, 0, tzinfo=UTC)
    stamp_author = "2024-01-05T09:00:00+0000"
    stamp_committer = committer_ts.strftime("%Y-%m-%dT%H:%M:%S+0000")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": stamp_author,
        "GIT_COMMITTER_DATE": stamp_committer,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty",
                     "--amend", "-m", "c0"], check=True, env=env)
    vs = file_versions(repo, "keps/sig-a/100-x/kep.yaml")
    assert [v.ts for v in vs] == [committer_ts]
