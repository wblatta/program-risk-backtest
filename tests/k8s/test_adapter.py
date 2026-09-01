"""K8sAdapter assembly: kep-number-derived item ids, collision handling, caching.
See Ruling 2 (task-10 brief overrides) for the id-derivation and collision policy."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import pytest
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(d, h=12): return datetime(2024, 1, d, h, tzinfo=UTC)

SIGS = "sigs:\n  - dir: sig-a\n    name: A\n  - dir: sig-b\n    name: B\n"


def _kep(number, status="implementable", extra=""):
    return (f'title: T{number}\nkep-number: {number}\nowning-sig: sig-a\n'
            f'status: {status}\nauthors: ["@ann"]\n{extra}')


def _adapter(tmp_path, enh_commits, sig_release_commits=None):
    from adapters.k8s.adapter import K8sAdapter
    cache = tmp_path / "cache"
    make_git_repo(cache / "k8s" / "enhancements", enh_commits)
    make_git_repo(cache / "k8s" / "community", [(T(1), {"sigs.yaml": SIGS})])
    make_git_repo(cache / "k8s" / "sig_release", sig_release_commits or [(T(1), {"releases/release-1.31/README.md": "\n"})])
    return K8sAdapter(cache, today=datetime(2025, 1, 1).date(), calendar_path=None)


def test_zero_kep_number_dirs_are_excluded_and_counted(tmp_path):
    a = _adapter(tmp_path, [
        (T(1), {
            "keps/sig-a/0000-process/kep.yaml": _kep(0),
            "keps/sig-a/100-real/kep.yaml": _kep(100),
        }),
    ])
    ids = {i.id for i in a.work_items()}
    assert ids == {"k8s:kep-100"}
    assert a.excluded_zero_dirs == ["keps/sig-a/0000-process"]


def test_collision_prefers_non_replaced_status(tmp_path):
    a = _adapter(tmp_path, [
        (T(1), {
            "keps/sig-a/200-old/kep.yaml": _kep(200, status="replaced"),
            "keps/sig-b/200-new/kep.yaml": _kep(200, status="implemented"),
        }),
    ])
    dirs = dict(a._kep_dirs())
    assert dirs == {"keps/sig-b/200-new": "k8s:kep-200"}
    assert a.dropped_collision_dirs == [("keps/sig-a/200-old", "keps/sig-b/200-new")]


def test_collision_tie_break_by_most_recent_commit(tmp_path):
    a = _adapter(tmp_path, [
        (T(1), {"keps/sig-a/300-early/kep.yaml": _kep(300, status="implementable")}),
        (T(2), {"keps/sig-b/300-later/kep.yaml": _kep(300, status="implementable")}),
        (T(3), {"keps/sig-b/300-later/README.md": "touch\n"}),  # sig-b dir gets the later commit
    ])
    dirs = dict(a._kep_dirs())
    assert dirs == {"keps/sig-b/300-later": "k8s:kep-300"}
    assert a.dropped_collision_dirs == [("keps/sig-a/300-early", "keps/sig-b/300-later")]


def test_collision_all_losers_falls_back_to_recency_among_all(tmp_path):
    # Every directory in the group is replaced/superseded: _pick_survivor's
    # `candidates = [...] or dirs` fallback must still pick deterministically
    # (by recency among the full group), not raise on an empty candidate list.
    a = _adapter(tmp_path, [
        (T(1), {"keps/sig-a/700-first/kep.yaml": _kep(700, status="replaced")}),
        (T(2), {"keps/sig-b/700-second/kep.yaml": _kep(700, status="superseded")}),
    ])
    dirs = dict(a._kep_dirs())
    assert dirs == {"keps/sig-b/700-second": "k8s:kep-700"}
    assert a.dropped_collision_dirs == [("keps/sig-a/700-first", "keps/sig-b/700-second")]


def test_item_id_uses_kep_number_not_directory_prefix(tmp_path):
    # sig-node/2043-... declares kep-number 1884 in the real corpus; item_id must
    # follow kep-number, but the PRR path is keyed to the *directory's* number
    # (prod-readiness files are named after the directory, not kep.yaml's
    # self-declared kep-number -- confirmed against the real corpus).
    a = _adapter(tmp_path, [
        (T(1), {
            "keps/sig-a/2043-mismatch/kep.yaml": _kep(1884),
            "keps/prod-readiness/sig-a/2043.yaml": 'alpha:\n  approver: "@prr"\n',
        }),
    ])
    ids = {i.id for i in a.work_items()}
    assert ids == {"k8s:kep-1884"}
    prr = [e for e in a.events() if e.kind == "owner_changed" and e.payload.get("role") == "prr_approver"]
    assert prr and prr[0].item_id == "k8s:kep-1884"


def test_fallback_to_directory_prefix_when_kep_yaml_unparseable(tmp_path):
    a = _adapter(tmp_path, [
        (T(1), {"keps/sig-a/400-broken/kep.yaml": "title: [unterminated\n"}),
    ])
    ids = {i.id for i in a.work_items()}
    assert ids == {"k8s:kep-400"}


def test_leading_zero_directory_prefix_matches_int(tmp_path):
    a = _adapter(tmp_path, [
        (T(1), {"keps/sig-a/0752-endpointslices/kep.yaml": _kep(752)}),
    ])
    ids = {i.id for i in a.work_items()}
    assert ids == {"k8s:kep-752"}


def test_kep_dirs_is_cached(tmp_path):
    a = _adapter(tmp_path, [(T(1), {"keps/sig-a/100-x/kep.yaml": _kep(100)})])
    first = a._kep_dirs()
    assert a._kep_dirs() is first


# --- Ruling 5: the clear-event contract ---

README_131 = ("| Start of Release Cycle | Lead | Monday 13th May 2024 | week 1 |\n"
              "| **Begin [Enhancements Freeze]** | Enhancements Lead | Friday 7th June 2024 | week 4 |\n"
              "| **Begin [Code Freeze]** | Branch Manager | Wednesday 10th July 2024 | week 9 |\n"
              "| **v1.31.0 released** | Branch Manager | Tuesday 13th August 2024 | week 14 |\n")


def test_clear_event_keeps_a_known_milestone_id(tmp_path):
    v1 = _kep(500, extra='milestone:\n  alpha: "v1.31"\n')
    v2 = _kep(500, extra="")  # alpha retracted
    a = _adapter(
        tmp_path,
        [
            (T(1), {"keps/sig-a/500-x/kep.yaml": v1}),
            (T(2), {"keps/sig-a/500-x/kep.yaml": v2}),
        ],
        sig_release_commits=[(T(1), {"releases/release-1.31/README.md": README_131})],
    )
    ms = {m.id for m in a.milestones()}
    assert "k8s:v1.31" in ms
    clears = [e for e in a.events() if e.kind == "target_set" and e.payload.get("op") == "clear"]
    assert clears, "expected a clear event"
    assert clears[0].payload["milestone_id"] == "k8s:v1.31"
    assert clears[0].payload["milestone_id"] in ms


# --- Task 3: evidence wiring ---

def test_adapter_labels_unresolved_without_delivery_evidence(tmp_path):
    """With a github cache present but empty, a committed target with no evidence
    must come back `unresolved` rather than `shipped`."""
    from adapters.k8s.adapter import K8sAdapter
    from core.model import EventKind as K
    a = _adapter(
        tmp_path,
        [(T(1), {"keps/sig-a/500-x/kep.yaml": _kep(500, extra='milestone:\n  alpha: "v1.31"\n')})],
        sig_release_commits=[(T(1), {"releases/release-1.31/README.md": README_131})],
    )
    (tmp_path / "cache" / "k8s" / "github" / "issues").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache" / "k8s" / "github" / "timeline").mkdir(parents=True, exist_ok=True)
    results = {e.payload["result"] for e in a.events() if e.kind == K.OUTCOME}
    assert "shipped" not in results
    assert "unresolved" in results
