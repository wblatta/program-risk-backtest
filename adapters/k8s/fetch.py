"""Clone or fast-forward the three K8s repos into cache_dir. Raw only."""
from __future__ import annotations
from pathlib import Path
import subprocess
from adapters.k8s.config import REPOS


def clone_or_update(url: str, dest: Path) -> None:
    if (dest / ".git").exists():
        subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=True)
        subprocess.run(["git", "-C", str(dest), "reset", "--quiet", "--hard", "origin/HEAD"], check=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", url, str(dest)], check=True)


def fetch_all(cache_dir: Path) -> dict[str, Path]:
    paths = {}
    for name, url in REPOS.items():
        dest = cache_dir / "k8s" / name
        clone_or_update(url, dest)
        paths[name] = dest
    return paths
