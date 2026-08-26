"""signals/ must not know any corpus. This is the portability guarantee."""
from pathlib import Path
import re


def test_signals_import_no_adapters():
    root = Path(__file__).resolve().parents[2] / "signals"
    for p in root.glob("*.py"):
        src = p.read_text()
        assert not re.search(r"^\s*(from|import)\s+adapters", src, re.M), f"{p.name} imports adapters"
        assert "k8s" not in src.lower(), f"{p.name} mentions k8s"
