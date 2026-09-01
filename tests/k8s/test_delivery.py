"""Delivery evidence: did the code actually land? Reads cached GitHub JSON only."""
import json
from datetime import date, datetime, timezone
import pytest
from adapters.k8s.delivery import DeliveryEvidence, load_delivery_evidence, has_evidence

UTC = timezone.utc
START, RELEASE = date(2024, 5, 13), date(2024, 8, 13)


def _write(tmp_path, n, issue, timeline):
    (tmp_path / "issues").mkdir(parents=True, exist_ok=True)
    (tmp_path / "timeline").mkdir(parents=True, exist_ok=True)
    (tmp_path / "issues" / f"{n}.json").write_text(json.dumps(issue))
    (tmp_path / "timeline" / f"{n}.json").write_text(json.dumps(timeline))


def xref(repo, merged_at, number=1):
    return {"event": "cross-referenced", "created_at": "2024-06-01T00:00:00Z",
            "source": {"issue": {"number": number, "repository": {"full_name": repo},
                                 "pull_request": {"merged_at": merged_at}}}}


def test_loads_closure_and_merge_timestamps(tmp_path):
    _write(tmp_path, 7, {"number": 7, "closed_at": "2024-09-01T00:00:00Z"},
           [xref("kubernetes/kubernetes", "2024-06-15T00:00:00Z")])
    got = load_delivery_evidence(tmp_path)
    assert got[7] == DeliveryEvidence(closed_at=datetime(2024, 9, 1, tzinfo=UTC),
                                      merges=(datetime(2024, 6, 15, tzinfo=UTC),))


def test_ignores_prs_from_other_repositories(tmp_path):
    """Only kubernetes/kubernetes merges count as implementation evidence."""
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/website", "2024-06-15T00:00:00Z"),
            xref("kubernetes/enhancements", "2024-06-16T00:00:00Z")])
    assert load_delivery_evidence(tmp_path)[7].merges == ()


def test_ignores_unmerged_pull_requests(tmp_path):
    """A closed-but-unmerged PR is not evidence anything landed."""
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/kubernetes", None)])
    assert load_delivery_evidence(tmp_path)[7].merges == ()


def test_merges_are_sorted_for_determinism(tmp_path):
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/kubernetes", "2024-07-01T00:00:00Z", 2),
            xref("kubernetes/kubernetes", "2024-06-01T00:00:00Z", 1)])
    m = load_delivery_evidence(tmp_path)[7].merges
    assert m == tuple(sorted(m))


def test_has_evidence_reports_closure_within_the_window():
    ev = DeliveryEvidence(closed_at=datetime(2024, 10, 1, tzinfo=UTC), merges=())
    assert has_evidence(ev, START, RELEASE) == "closure"


def test_has_evidence_rejects_closure_beyond_the_window():
    """Closure 200 days after release says nothing about this milestone."""
    ev = DeliveryEvidence(closed_at=datetime(2025, 3, 1, tzinfo=UTC), merges=())
    assert has_evidence(ev, START, RELEASE) is None


def test_has_evidence_reports_a_merge_inside_the_cycle():
    ev = DeliveryEvidence(closed_at=None, merges=(datetime(2024, 6, 15, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) == "merge"


def test_has_evidence_rejects_a_merge_before_the_cycle_opened():
    """A merge predating the cycle belongs to earlier work, not this commitment."""
    ev = DeliveryEvidence(closed_at=None, merges=(datetime(2024, 1, 1, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) is None


def test_closure_takes_precedence_over_merge_when_both_hold():
    ev = DeliveryEvidence(closed_at=datetime(2024, 9, 1, tzinfo=UTC),
                          merges=(datetime(2024, 6, 15, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) == "closure"


def test_missing_evidence_record_is_not_an_error():
    assert has_evidence(None, START, RELEASE) is None


def test_has_evidence_rejects_closure_before_the_cycle_opened():
    """An issue closed long before this cycle opened cannot be evidence for it."""
    ev = DeliveryEvidence(closed_at=datetime(2024, 1, 1, tzinfo=UTC), merges=())
    assert has_evidence(ev, START, RELEASE) is None
