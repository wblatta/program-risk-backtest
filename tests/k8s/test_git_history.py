import os
import subprocess
import pytest
from datetime import datetime, timezone
from adapters.k8s.git_history import (
    list_kep_dirs, file_versions, dir_activity, GitError, _show_or_none,
)
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(d): return datetime(2024, 1, d, 12, 0, tzinfo=UTC)

def _env_at(ts):
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {
        **os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com",
    }

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

def test_first_parent_skips_side_branch_state_uses_merge_committer_time(tmp_path):
    # A --no-ff merge must not surface the side branch's own commit as a
    # separate mainline version, and the state it brings in must be timed
    # at the merge commit's committer time, not the side commit's.
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    f = repo / "keps/sig-a/100-x/kep.yaml"
    f.parent.mkdir(parents=True)

    f.write_text("mainline\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c0"],
                    env=_env_at(T(1)), check=True)

    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "side"], check=True)
    f.write_text("side-only\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "side1"],
                    env=_env_at(T(2)), check=True)

    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "merge", "-q", "--no-ff", "side", "-m", "merge"],
                    env=_env_at(T(5)), check=True)

    vs = file_versions(repo, "keps/sig-a/100-x/kep.yaml")
    assert [v.ts for v in vs] == [T(1), T(5)]
    assert [v.text for v in vs] == ["mainline\n", "side-only\n"]

def test_file_versions_follows_renames(tmp_path):
    # A KEP directory rename (slug change or SIG move) must not truncate
    # the file's history: content from before the rename must still surface,
    # timed at the commit that carried it, under the pre-rename sha.
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-old-name/kep.yaml": "v1\n"}),
        (T(2), {"keps/sig-a/100-old-name/kep.yaml": None,
                 "keps/sig-a/100-new-name/kep.yaml": "v1\n"}),
        (T(3), {"keps/sig-a/100-new-name/kep.yaml": "v2\n"}),
    ])
    vs = file_versions(repo, "keps/sig-a/100-new-name/kep.yaml")
    assert [v.ts for v in vs] == [T(1), T(2), T(3)]
    assert [v.text for v in vs] == ["v1\n", "v1\n", "v2\n"]

def test_file_versions_does_not_graft_unrelated_boilerplate_similar_file(tmp_path):
    # KEPs share a large YAML boilerplate template. Two distinct, unrelated
    # KEPs whose bodies happen to be short enough that the shared boilerplate
    # crosses git's default rename/copy similarity threshold must not be
    # spliced into one file's history by --follow.
    boiler = (
        "title: KEP\nkep-number: NUM\nauthors:\n  - \"@someone\"\nowning-sig: sig-x\n"
        "status: provisional\ncreation-date: 2020-01-01\nreviewers:\n  - TBD\n"
        "approvers:\n  - TBD\n##### WARNING !!! ######\n# prr-approvers has been moved\n"
        "# create your own copy\n#prr-approvers:\n  - TBD\nsee-also: []\nreplaces: []\n"
        "superseded-by: []\n"
    )
    alpha = boiler + "".join(f"alpha unique body line {i} about widgets\n" for i in range(1, 7))
    omega = boiler + "".join(f"omega unique body line {i} about rockets\n" for i in range(1, 7))
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-alpha/kep.yaml": alpha}),
        (T(2), {"keps/sig-b/900-omega/kep.yaml": omega}),
    ])
    vs = file_versions(repo, "keps/sig-b/900-omega/kep.yaml")
    assert [v.ts for v in vs] == [T(2)]
    assert "alpha" not in vs[0].text

def test_real_git_failure_raises_instead_of_looking_empty(tmp_path):
    # A directory that is not a git repo at all must raise, not be silently
    # reported as "nothing here" the way a genuinely absent path is.
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(GitError):
        list_kep_dirs(not_a_repo)
    with pytest.raises(GitError):
        dir_activity(not_a_repo, "keps/sig-a/100-x")

def test_show_or_none_distinguishes_missing_path_from_real_failure(tmp_path):
    repo = make_git_repo(tmp_path / "r", [(T(1), {"a": "x\n"})])
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert _show_or_none(repo, head, "nope") is None
    with pytest.raises(GitError):
        _show_or_none(repo, "not-a-real-sha", "a")

def test_make_git_repo_deletes_existing_path(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "v1\n"}),
        (T(2), {"keps/sig-a/100-x/kep.yaml": None}),
    ])
    vs = file_versions(repo, "keps/sig-a/100-x/kep.yaml")
    assert [v.text for v in vs] == ["v1\n"]  # deletion commit yields no version, not a crash

def test_make_git_repo_deleting_never_tracked_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_git_repo(tmp_path / "r", [(T(1), {"never/created": None})])

def test_make_git_repo_converts_non_utc_timestamp_to_utc(tmp_path):
    from datetime import timedelta
    est = timezone(timedelta(hours=-5))
    local_ts = datetime(2024, 1, 1, 7, 0, tzinfo=est)  # 07:00 EST == 12:00 UTC
    repo = make_git_repo(tmp_path / "r", [(local_ts, {"a": "x\n"})])
    vs = file_versions(repo, "a")
    assert vs[0].ts == T(1)

def test_make_git_repo_rejects_naive_datetime(tmp_path):
    with pytest.raises(ValueError):
        make_git_repo(tmp_path / "r", [(datetime(2024, 1, 1, 12, 0), {"a": "x\n"})])
