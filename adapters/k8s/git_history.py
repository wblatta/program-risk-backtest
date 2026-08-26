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

# Similarity threshold used with --follow when walking a single file's
# history across renames. KEP files share a large boilerplate YAML template
# (title/kep-number/authors/status header, PRR-approvers warning block,
# etc.), so git's default ~50% similarity threshold for rename/copy
# detection false-positives: it splices together the history of two
# completely unrelated KEPs whenever their bodies happen to be short enough
# that the shared boilerplate crosses 50% similarity. Genuine KEP renames
# (a slug change or a SIG move, both preserving the KEP number) measured on
# the real kubernetes/enhancements corpus score 90-100% similar; spurious
# boilerplate-only matches to unrelated KEPs score below that. 90% is high
# enough to keep the false positives out while still following real renames.
_FOLLOW_SIMILARITY = "-M90%"


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
    out = _git(repo, "ls-files", "keps/*/*/kep.yaml")
    dirs = {line.rsplit("/", 1)[0] for line in out.splitlines() if line.startswith("keps/sig-")}
    return sorted(dirs)


def _iter_path_at_commit(repo: Path, rel_path: str):
    """Yield (sha, epoch_str, path_in_that_commit) newest-first along
    first-parent history, following renames per _FOLLOW_SIMILARITY. The
    path can differ from rel_path for commits before a rename; that is the
    path git show needs to retrieve the content that existed then.
    """
    out = _git(
        repo, "log", "--first-parent", "--follow", _FOLLOW_SIMILARITY,
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
            # which path held the content here, so skip rather than guess.
            continue
        fields = line.split("\t")
        path = fields[-1]  # for M/A: the only path; for R###/C###: the new path
        yield sha, epoch, path


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
