# adapters/k8s/git_history.py
"""Read-only access to a local clone's history. First-parent commit time = when it became true on main."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class FileVersion:
    sha: str
    ts: datetime
    text: str


def _git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout


def _ts(epoch: str) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc)


def list_kep_dirs(repo: Path) -> list[str]:
    out = _git(repo, "ls-files", "keps/*/*/kep.yaml")
    dirs = {line.rsplit("/", 1)[0] for line in out.splitlines() if line.startswith("keps/sig-")}
    return sorted(dirs)


def file_versions(repo: Path, rel_path: str) -> list[FileVersion]:
    log = _git(repo, "log", "--first-parent", "--format=%H %ct", "--", rel_path)
    versions = []
    for line in reversed(log.splitlines()):
        sha, epoch = line.split()
        text = _git(repo, "show", f"{sha}:{rel_path}")
        if text == "":
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
