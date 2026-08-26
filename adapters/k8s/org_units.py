"""kubernetes/community sigs.yaml → OrgUnit list."""
from __future__ import annotations
import yaml
from core.model import OrgUnit

PREFIX = "k8s:"


def parse_sigs_yaml(text: str) -> list[OrgUnit]:
    data = yaml.safe_load(text) or {}
    out = []
    for s in data.get("sigs") or []:
        d = str(s.get("dir") or "").strip().lower()
        if d:
            out.append(OrgUnit(PREFIX + d, str(s.get("name") or d)))
    return sorted(out, key=lambda o: o.id)
