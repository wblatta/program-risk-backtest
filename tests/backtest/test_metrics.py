from datetime import date, datetime, timezone
from backtest.run import Row
from backtest.metrics import signal_metrics, by_org, by_stage, rows_frame
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
M31 = M  # alias: the brief's test code names this M31
MS = {M.id: M}
def T(m, d): return datetime(2024, m, d, tzinfo=UTC)

def rows():
    # 4 rows: 2 slipped, 2 shipped. sig "good" fires on both slips 6 weeks early; "bad" fires on one shipped 1 week early.
    return [Row("x:a", "alpha", M.id, "x:o1", "slipped", {"good": T(5, 29), "bad": None}),
            Row("x:b", "alpha", M.id, "x:o1", "slipped", {"good": T(5, 29), "bad": None}),
            Row("x:c", "alpha", M.id, "x:o2", "shipped", {"good": None, "bad": T(7, 3)}),
            Row("x:d", "beta", M.id, "x:o2", "shipped", {"good": None, "bad": None})]

def test_metrics_table():
    df = signal_metrics(rows(), MS, L=4, n_boot=200).set_index("signal")
    g = df.loc["good"]
    assert g["fired"] == 2 and g["precision"] == 1.0 and g["recall"] == 1.0 and g["lift"] == 2.0
    assert g["median_lead_weeks"] == 6.0 and g["lead_class"] == "risk"
    b = df.loc["bad"]
    assert b["fired"] == 1 and b["precision"] == 0.0 and b["lead_class"] == "status"
    assert "precision_ci_lo" in df.columns and 0 <= g["precision_ci_lo"] <= g["precision_ci_hi"] <= 1

def test_by_org_counts():
    df = by_org(rows()).set_index("org_id")
    assert df.loc["x:o1", "rows"] == 2 and df.loc["x:o1", "slip_rate"] == 1.0
    assert df.loc["x:o2", "slip_rate"] == 0.0

def test_rows_frame_has_one_col_per_signal():
    df = rows_frame(rows())
    assert set(df.columns) >= {"item_id", "stage", "milestone_id", "org_id", "outcome", "first_fired.good", "first_fired.bad"}


from backtest.run import Row, UNRESOLVED


def _rows():
    """Two rows a signal fired on: one a real positive, one unresolved."""
    return [Row("i1", "alpha", "x:v31", None, "slipped", {"s": T(5, 20)}),
            Row("i2", "alpha", "x:v31", None, "unresolved", {"s": T(5, 20)}),
            Row("i3", "alpha", "x:v31", None, "shipped", {"s": None})]


def test_evidenced_cut_excludes_unresolved_rows():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="evidenced")
    assert int(df["rows"].iloc[0]) == 2, "unresolved row must be dropped"
    assert df["cut"].iloc[0] == "evidenced"


def test_full_cut_counts_unresolved_as_negative():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="full")
    assert int(df["rows"].iloc[0]) == 3, "all rows retained"
    assert df["cut"].iloc[0] == "full"
    # base rate is 1 positive of 3 rows -- unresolved counted as not-positive
    assert abs(float(df["base_rate"].iloc[0]) - 1 / 3) < 1e-9


def test_cut_column_is_first_so_a_csv_always_says_which_it_is():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="evidenced")
    assert list(df.columns)[0] == "cut"


def test_unknown_cut_is_rejected_rather_than_silently_defaulting():
    import pytest
    with pytest.raises(ValueError):
        signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="whatever")


def test_by_org_respects_cut():
    """One org, two rows: a real slip and an unresolved one. Pins that by_org applies the
    cut the same way signal_metrics does -- if the two ever drift, this fails."""
    rows = [Row("i1", "alpha", "x:v31", "x:o1", "slipped", {}),
            Row("i2", "alpha", "x:v31", "x:o1", "unresolved", {})]
    ev = by_org(rows, cut="evidenced").set_index("org_id")
    assert ev.loc["x:o1", "rows"] == 1 and ev.loc["x:o1", "slips"] == 1 and ev.loc["x:o1", "slip_rate"] == 1.0
    assert ev["cut"].iloc[0] == "evidenced"
    full = by_org(rows, cut="full").set_index("org_id")
    assert full.loc["x:o1", "rows"] == 2 and full.loc["x:o1", "slips"] == 1 and full.loc["x:o1", "slip_rate"] == 0.5
    assert full["cut"].iloc[0] == "full"


# --- by_stage (spec §8: "Cuts: by org unit, by stage, S0 vs each signal") ---

def test_by_stage_counts():
    """Stage is the axis spec §8 names alongside org, and the one the labeling design
    predicted would differ (closure evidence is weighted toward a KEP's final stage)."""
    df = by_stage(rows()).set_index("stage")
    assert df.loc["alpha", "rows"] == 3 and df.loc["alpha", "slips"] == 2
    assert df.loc["alpha", "slip_rate"] == 2 / 3
    assert df.loc["beta", "rows"] == 1 and df.loc["beta", "slip_rate"] == 0.0

def test_by_stage_labels_its_cut():
    """Every table states its cut. A number that does not say which cut it is, is a defect."""
    assert by_stage(rows(), cut="full")["cut"].unique().tolist() == ["full"]

def test_by_stage_excludes_unlabeled_rows():
    """A row with outcome None is held-out, not a negative -- it must not dilute the rate."""
    rs = rows() + [Row("x:e", "alpha", M.id, "x:o1", None, {"good": None, "bad": None})]
    assert by_stage(rs).set_index("stage").loc["alpha", "rows"] == 3

def test_by_stage_empty_input_keeps_schema():
    df = by_stage([])
    assert list(df.columns) == ["cut", "stage", "rows", "slips", "slip_rate"]
