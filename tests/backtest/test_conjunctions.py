from datetime import date, datetime, timezone
import pytest
from backtest.conjunctions import conjunction_metrics
from backtest.run import Row
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
MS = {M.id: M}
T = datetime(2024, 6, 1, tzinfo=UTC)


def row(i, outcome, a, b):
    """`a` and `b` are whether signals A and B fired."""
    return Row(f"x:i{i}", "alpha", M.id, None, outcome,
               {"a": T if a else None, "b": T if b else None},
               {"a": a, "b": b})


def rows():
    # A fires on 4 (3 slips), B fires on 4 (3 slips), both on 3 (all slips).
    return [row(0, "slipped", True, True), row(1, "slipped", True, True),
            row(2, "slipped", True, True), row(3, "shipped", True, False),
            row(4, "slipped", False, True), row(5, "shipped", False, False),
            row(6, "shipped", False, False), row(7, "shipped", False, False),
            # A slip that A catches and B does not -- without it the conjunction loses no
            # positive and the recall trade this file exists to show is invisible.
            row(8, "slipped", True, False)]


def by_name(df):
    return {r["signals"]: r for _, r in df.iterrows()}


def test_reports_each_signal_alone_and_the_pair():
    d = by_name(conjunction_metrics(rows(), ["a", "b"], MS, n_boot=0, min_fired=1))
    assert set(d) == {"a", "b", "a AND b"}

def test_conjunction_precision_beats_either_alone():
    d = by_name(conjunction_metrics(rows(), ["a", "b"], MS, n_boot=0, min_fired=1))
    assert d["a"]["precision"] == 0.8 and d["b"]["precision"] == 1.0
    assert d["a AND b"]["fired"] == 3 and d["a AND b"]["precision"] == 1.0

def test_recall_falls_when_precision_rises():
    """The trade the conjunction makes, and the reason it must be reported beside
    precision rather than instead of it."""
    d = by_name(conjunction_metrics(rows(), ["a", "b"], MS, n_boot=0, min_fired=1))
    assert d["a AND b"]["recall"] < d["a"]["recall"]

def test_reports_overlap_so_redundancy_is_visible():
    """Two signals that fire on the same rows cannot be combined into anything new.
    Jaccard says whether the pair is worth reporting at all."""
    d = by_name(conjunction_metrics(rows(), ["a", "b"], MS, n_boot=0, min_fired=1))
    assert d["a AND b"]["jaccard"] == pytest.approx(3 / 6)

def test_flags_a_subset_relationship():
    """If one signal's firings are wholly contained in another's, the 'conjunction' is
    just the smaller signal wearing a different name -- an implementation fact, not a
    finding, and it must not be published as one."""
    rs = [row(0, "slipped", True, True), row(1, "shipped", False, True),
          row(2, "shipped", False, False)]
    d = by_name(conjunction_metrics(rs, ["a", "b"], MS, n_boot=0, min_fired=1))
    assert d["a AND b"]["subset"] == "a ⊆ b"

def test_no_subset_flag_when_neither_contains_the_other():
    assert by_name(conjunction_metrics(rows(), ["a", "b"], MS, n_boot=0, min_fired=1))["a AND b"]["subset"] is None

def test_triples_when_asked():
    rs = [row(0, "slipped", True, True), row(1, "shipped", True, False)]
    for r in rs:
        r.first_fired["c"] = T
        r.fired_at_freeze["c"] = True
    d = by_name(conjunction_metrics(rs, ["a", "b", "c"], MS, max_size=3, n_boot=0, min_fired=1))
    assert "a AND b AND c" in d

def test_pairs_below_the_firing_floor_are_dropped():
    """A conjunction firing on three rows has a precision but not a finding."""
    d = by_name(conjunction_metrics(rows(), ["a", "b"], MS, min_fired=4, n_boot=0))
    assert "a AND b" not in d

def test_honours_cut_and_evaluation():
    d = conjunction_metrics(rows(), ["a", "b"], MS, cut="full", evaluation="at_freeze", n_boot=0)
    assert set(d["cut"]) == {"full"} and set(d["eval"]) == {"at_freeze"}
