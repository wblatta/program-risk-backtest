# tests/helpers.py
from __future__ import annotations
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess

# Force C-locale, English git output for hermetic, byte-identical fixtures
# regardless of the machine's ambient locale.
_BASE_ENV = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}


def _git(repo: Path, *args, env=None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True, encoding="utf-8", env=env if env is not None else _BASE_ENV,
    ).stdout


def _utc_stamp(ts: datetime) -> str:
    """Render ts as a git date string in +0000. Requires a timezone-aware
    datetime, converted to UTC first, so a caller passing e.g. a naive
    local-time or a non-UTC-aware datetime cannot silently get the wrong
    commit date by having its wall-clock fields stapled to '+0000'.
    """
    if ts.tzinfo is None:
        raise ValueError(f"make_git_repo requires timezone-aware timestamps, got naive {ts!r}")
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


def make_git_repo(root: Path, commits: list[tuple[datetime, dict[str, str | None]]]) -> Path:
    """Build a repo where each commit lands at the given UTC timestamp. Returns repo path.

    Each commit is (committer_ts, {rel_path: content}); content of None
    deletes rel_path (it must already exist in the working tree -- deleting
    a path that was never created raises FileNotFoundError, since that is a
    bug in the fixture's commit list, not a supported no-op).
    """
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    for i, (ts, files) in enumerate(commits):
        for rel, content in files.items():
            p = root / rel
            if content is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
        _git(root, "add", "-A")
        stamp = _utc_stamp(ts)
        env = {**_BASE_ENV, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        _git(root, "commit", "-q", "--allow-empty", "-m", f"c{i}", env=env)
    return root
