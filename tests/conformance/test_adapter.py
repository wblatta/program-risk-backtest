"""Corpus-agnostic adapter contract. Every adapter must pass every check."""
from __future__ import annotations
from datetime import datetime, time, timezone
from pathlib import Path
import pytest
from core.model import EventKind as K, SOURCES
from core.replay import snapshot
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(m, d): return datetime(2024, m, d, 12, tzinfo=UTC)

KEP = 'title: Fixture\nkep-number: 100\nowning-sig: sig-a\nstatus: implementable\nauthors: ["@ann"]\nmilestone:\n  alpha: "v1.31"\n'
README_131 = ("| Start of Release Cycle | Lead | Monday 13th May 2024 | week 1 |\n"
              "| **Begin [Enhancements Freeze]** | Enhancements Lead | Friday 7th June 2024 | week 4 |\n"
              "| **Begin [Code Freeze]** | Branch Manager | Wednesday 10th July 2024 | week 9 |\n"
              "| **v1.31.0 released** | Branch Manager | Tuesday 13th August 2024 | week 14 |\n")
SIGS = "sigs:\n  - dir: sig-a\n    name: A\n"


@pytest.fixture
def fixture_adapter(tmp_path):
    from adapters.k8s.adapter import K8sAdapter
    cache = tmp_path / "cache"
    make_git_repo(cache / "k8s" / "enhancements", [
        (T(3, 1), {"keps/sig-a/100-fixture/kep.yaml": KEP, "keps/sig-a/100-fixture/README.md": "Depends on nothing.\n"}),
        (T(4, 1), {"keps/prod-readiness/sig-a/100.yaml": 'alpha:\n  approver: "@prr"\n'}),
    ])
    make_git_repo(cache / "k8s" / "community", [(T(1, 1), {"sigs.yaml": SIGS})])
    make_git_repo(cache / "k8s" / "sig_release", [(T(1, 1), {"releases/release-1.31/README.md": README_131,
                                                               "releases/release-1.31/exceptions.yaml": "enhancementFreeze:\ncodeFreeze:\n"})])
    return K8sAdapter(cache, today=datetime(2025, 1, 1).date(), calendar_path=None)


def _real_adapter():
    from adapters.k8s.adapter import K8sAdapter
    return K8sAdapter(Path("cache"))


def conformance(adapter):
    items = {i.id for i in adapter.work_items()}
    ms = {m.id: m for m in adapter.milestones()}
    ev = adapter.events()
    assert ev == sorted(ev, key=lambda e: e.sort_key())
    assert all(e.source in SOURCES for e in ev)
    assert all(e.item_id in items for e in ev), "event references unknown item"
    assert all(e.payload["milestone_id"] in ms for e in ev if e.kind == K.TARGET_SET), "target_set references unknown milestone"
    first_ts = {}
    for e in ev:
        first_ts.setdefault(e.item_id, e.ts)
    for e in ev:
        if e.kind == K.OUTCOME:
            m = ms[e.payload["milestone_id"]]
            assert m.is_scheduled
            assert e.ts >= first_ts[e.item_id]
            assert e.ts.date() > m.freeze
    for m in ms.values():
        if not m.is_scheduled or not m.dates.get("enhancements_freeze"):
            continue
        as_of = datetime.combine(m.dates["enhancements_freeze"], time(23, 59, 59), tzinfo=UTC)
        targeted = [s for s in snapshot(ev, as_of).values() if m.id in s.targets.values()]
        if any(e.kind == K.OUTCOME and e.payload["milestone_id"] == m.id for e in ev):
            assert targeted, f"{m.id} has outcomes but nothing targeted at enhancements freeze"
    assert ev == adapter.events(), "events() is not deterministic"
    labeling = Path(__file__).resolve().parents[2] / "adapters" / adapter.config.name / "LABELING.md"
    assert labeling.exists() and labeling.read_text().strip()


def test_fixture_adapter_conforms(fixture_adapter):
    conformance(fixture_adapter)
    ev = fixture_adapter.events()
    kinds = {e.kind for e in ev}
    assert {K.TARGET_SET, K.STATUS_CHANGED, K.OWNER_CHANGED, K.ACTIVITY, K.OUTCOME} <= kinds
    prr = [e for e in ev if e.kind == K.OWNER_CHANGED and e.payload["role"] == "prr_approver"]
    assert prr and prr[0].ts == T(4, 1)
    outcome = [e for e in ev if e.kind == K.OUTCOME][0]
    assert outcome.payload == {"milestone_id": "k8s:v1.31", "stage": "alpha", "result": "shipped", "evidence": None}


@pytest.mark.integration
@pytest.mark.skipif(not Path("cache/k8s/enhancements/.git").exists(), reason="no cache")
def test_real_k8s_adapter_conforms():
    conformance(_real_adapter())
