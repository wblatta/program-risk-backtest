from datetime import date, datetime, timezone
from backtest.run import Row
from backtest.metrics import signal_metrics, by_org, rows_frame
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
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
