# tests/helpers.py
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path
import subprocess


def _git(repo: Path, *args, env=None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def make_git_repo(root: Path, commits: list[tuple[datetime, dict[str, str | None]]]) -> Path:
    """Build a repo where each commit lands at the given UTC timestamp. Returns repo path."""
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
        stamp = ts.strftime("%Y-%m-%dT%H:%M:%S+0000")
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        _git(root, "commit", "-q", "--allow-empty", "-m", f"c{i}", env=env)
    return root
