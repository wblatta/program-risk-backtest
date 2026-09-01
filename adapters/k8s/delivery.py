"""Did the code actually land? Evidence from cached tracking issues and PR cross-refs.

Two independent sources, measured complementary rather than redundant (intersection
2.2%, inverse stage profiles):

  closure  the KEP's tracking issue closed between cycle start and `closure_days`
           after the release. Present on 21.6% of shipped rows and 0.8% of slipped
           ones. A tracking issue spans a KEP's whole lifecycle, so this is evidence
           about the FINAL stage -- 53.9% of `stable` rows, under 5% of alpha and beta.
  merge    a kubernetes/kubernetes PR cross-referenced from the tracking issue
           merged between cycle start and release. 24.0% vs 6.5%. Implementation
           PRs cluster at first delivery, so this is evidence about the FIRST
           stage -- 45.5% of `alpha`, 10.2% of `stable`.

Deliberately NOT used: the release team's `tracked/yes` label. It appears on 51.8%
of shipped rows and 40.0% of slipped ones -- it records that the team was tracking
the work and is not removed when the work fails.

Reads only from `cache/k8s/github/`, populated by `cli.py fetch-issues`. No network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

IMPL_REPO = "kubernetes/kubernetes"


@dataclass(frozen=True)
class DeliveryEvidence:
    closed_at: datetime | None
    merges: tuple[datetime, ...]


def _ts(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _merges(timeline) -> tuple[datetime, ...]:
    out = []
    for e in timeline or []:
        if not isinstance(e, dict) or e.get("event") != "cross-referenced":
            continue
        src = (e.get("source") or {}).get("issue") or {}
        if (src.get("repository") or {}).get("full_name") != IMPL_REPO:
            continue
        merged = _ts((src.get("pull_request") or {}).get("merged_at"))
        if merged:
            out.append(merged)
    return tuple(sorted(out))


def load_delivery_evidence(github_cache: Path) -> dict[int, DeliveryEvidence]:
    """Read every cached issue + timeline into evidence records keyed by KEP number."""
    github_cache = Path(github_cache)
    out: dict[int, DeliveryEvidence] = {}
    for p in sorted((github_cache / "issues").glob("*.json")):
        try:
            n = int(p.stem)
            issue = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        tp = github_cache / "timeline" / f"{n}.json"
        try:
            timeline = json.loads(tp.read_text()) if tp.exists() else []
        except (ValueError, OSError):
            timeline = []
        out[n] = DeliveryEvidence(closed_at=_ts(issue.get("closed_at")),
                                  merges=_merges(timeline))
    return out


def _eod(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def has_evidence(ev: DeliveryEvidence | None, cycle_start: date, release: date,
                 closure_days: int = 90) -> str | None:
    """Which evidence supports delivery at this milestone, if any.

    Returns "closure", "merge", or None. Closure is checked first because it has the
    lower false-positive rate (0.8% vs 6.5%), so when both hold the stronger source
    is the one recorded.
    """
    if ev is None:
        return None
    lo, hi = _eod(cycle_start), _eod(release)
    if ev.closed_at is not None and lo <= ev.closed_at <= hi + timedelta(days=closure_days):
        return "closure"
    if any(lo <= m <= hi for m in ev.merges):
        return "merge"
    return None
