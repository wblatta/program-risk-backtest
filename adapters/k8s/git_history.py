# adapters/k8s/git_history.py
"""Read-only access to a local clone's history. First-parent commit time = when it became true on main."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess

# Force English, C-locale git output regardless of the caller's ambient
# locale/terminal settings. Required for byte-identical output across
# machines, and because _show_or_none below matches on the (English) text
# of git's "fatal:" messages to tell a real failure from "path absent here".
_GIT_ENV = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}


@dataclass(frozen=True)
class FileVersion:
    sha: str
    ts: datetime
    text: str


class GitError(RuntimeError):
    """A git invocation failed for a reason other than "path absent here"."""


def _run(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", env=_GIT_ENV,
    )


def _git(repo: Path, *args) -> str:
    r = _run(repo, *args)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


# git's (English, per _GIT_ENV above) wording for "this path is not present
# in this particular tree" -- as opposed to a bad object, a bad repo, or any
# other real failure, all of which must raise rather than look like a quiet
# deletion.
_MISSING_PATH_MARKERS = ("does not exist in", "exists on disk, but not in")


def _show_or_none(repo: Path, sha: str, rel_path: str) -> str | None:
    """Content of rel_path at sha, or None if that path is absent from that
    commit's tree (i.e. deleted there). Raises GitError for any other
    failure (bad sha, corrupt repo, git invocation problem, ...) instead of
    silently treating it as a deletion.
    """
    r = _run(repo, "show", f"{sha}:{rel_path}")
    if r.returncode == 0:
        return r.stdout
    stderr = r.stderr.strip()
    if any(marker in stderr for marker in _MISSING_PATH_MARKERS):
        return None
    raise GitError(f"git show {sha}:{rel_path} failed: {stderr}")


def _ts(epoch: str) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc)


def list_kep_dirs(repo: Path) -> list[str]:
    # git pathspec "*" crosses "/", unlike a Python glob: this deliberately
    # matches keps/sig-x/N-slug/kep.yaml (the common case) *and*
    # keps/sig-x/group/N-slug/kep.yaml (KEPs nested under a provider/group
    # subdirectory, e.g. keps/sig-cloud-provider/azure/2328-.../kep.yaml).
    # The spec for this function is "contains a kep.yaml", not a fixed
    # depth, so both must be included -- do not narrow this to a
    # fixed-depth match (e.g. by switching to a Python glob) without
    # checking test_list_kep_dirs_includes_nested_group_dirs below.
    out = _git(repo, "ls-files", "keps/*/kep.yaml")
    dirs = {line.rsplit("/", 1)[0] for line in out.splitlines() if line.startswith("keps/sig-")}
    return sorted(dirs)


def _iter_path_at_commit(repo: Path, rel_path: str):
    """Yield (sha, epoch_str, path_in_that_commit) newest-first along
    first-parent history, following renames with git's default rename/copy
    detection (no similarity threshold override). The path can differ from
    rel_path for commits before a rename; that is the path git show needs
    to retrieve the content that existed then.

    A rename ("R###" status) means the old path was deleted in this very
    commit: the same file's identity genuinely continues further back
    under the old name, so the walk keeps following it. A plain "M" (same
    path, modified) or "D" (deleted, handled by file_versions below) does
    not end the identity either -- it says nothing about where the file
    came from. Any other status ends the identity walk after including
    this commit's own (correct) content: "A" (added) is a real genesis --
    git's own log has nothing earlier for that path anyway. "C###" (copy)
    means the apparent "source" file was *not* deleted -- it is a
    different, still-living file whose content this commit happened to
    reuse (KEP authors routinely start a new KEP by copying a similar
    sibling's file, and KEP files also share enough boilerplate template
    text that unrelated KEPs can look superficially similar to git's copy
    heuristic), not a past identity of rel_path. Walking into that copy
    source's own further history would silently graft an unrelated file's
    history onto this one -- confirmed on the real kubernetes/enhancements
    clone, where unbounded --follow does exactly this (see task-5-report.md).
    """
    out = _git(
        repo, "log", "--first-parent", "--follow",
        "--name-status", "--format=%x00%H%x09%ct", "--", rel_path,
    )
    for chunk in out.split("\x00"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, rest = chunk.partition("\n\n")
        sha, epoch = header.split("\t")
        line = next((l for l in rest.splitlines() if l.strip()), "")
        if not line:
            # No diff recorded against the pathspec for this commit (seen
            # only in unusual merge shapes). We cannot say with confidence
            # which path held the content here, so stop rather than guess.
            break
        fields = line.split("\t")
        status, path = fields[0], fields[-1]  # for M/A/D: the only path; for R###/C###: the new path
        yield sha, epoch, path
        if not (status.startswith(("M", "R", "D"))):
            break


def file_versions(repo: Path, rel_path: str) -> list[FileVersion]:
    entries = list(_iter_path_at_commit(repo, rel_path))
    versions = []
    for sha, epoch, path in reversed(entries):
        text = _show_or_none(repo, sha, path)
        if text is None:
            continue  # deleted in this commit
        versions.append(FileVersion(sha, _ts(epoch), text))
    return versions


def dir_activity(repo: Path, rel_dir: str) -> list[tuple[datetime, str, str]]:
    log = _git(repo, "log", "--no-merges", "--format=%H %ct %ae", "--", rel_dir)
    out = []
    for line in reversed(log.splitlines()):
        sha, epoch, email = line.split(" ", 2)
        out.append((_ts(epoch), sha, email))
    return out
