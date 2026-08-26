"""Parse keps/prod-readiness/<sig>/<num>.yaml → {stage: approver handle}."""
from __future__ import annotations
import yaml

_PLACEHOLDERS = {"", "tbd", "none", "null", "n/a"}


def parse_prr_yaml(text: str) -> dict[str, str]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for stage in ("alpha", "beta", "stable"):
        block = data.get(stage)
        if not isinstance(block, dict):
            continue
        h = str(block.get("approver") or "").strip().lower()
        if h in _PLACEHOLDERS:
            continue
        out[stage] = h if h.startswith("@") else "@" + h
    return out
