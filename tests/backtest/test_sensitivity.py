from datetime import date, datetime, timezone
import pandas as pd
from backtest.run import Row
from backtest.sensitivity import PARAM_SIGNALS, sweep
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
MS = {M.id: M}


def fake_runner(params):
    """Stands in for run_backtest. `hollow_owner` gets better as N grows, so the sweep
    has something with a real gradient to report."""
    n = params["N"]
    fires = {4: [True, True, False, False], 8: [True, False, False, False]}.get(n, [False] * 4)
    outs = ["slipped", "shipped", "slipped", "shipped"]
    return [Row(f"x:i{i}", "alpha", M.id, "x:o", outs[i],
                {"hollow_owner": datetime(2024, 6, 1, tzinfo=UTC) if f else None})
            for i, f in enumerate(fires)]


def test_sweep_varies_one_param_and_holds_the_rest():
    df = sweep(fake_runner, MS, {"N": 8, "M": 4, "K": 3, "L": 4}, {"N": [4, 8]}, n_boot=0)
    assert set(df["param"]) == {"N"}
    assert sorted(df["value"].unique()) == [4, 8]
    assert set(df["signal"]) == {"hollow_owner"}   # only the signal this param reaches

def test_sweep_reports_the_gradient():
    df = sweep(fake_runner, MS, {"N": 8, "M": 4, "K": 3, "L": 4}, {"N": [4, 8]}, n_boot=0).set_index("value")
    assert df.loc[4, "fired"] == 2 and df.loc[4, "precision"] == 0.5
    assert df.loc[8, "fired"] == 1 and df.loc[8, "precision"] == 1.0

def test_sweep_marks_the_a_priori_value():
    """The published result is one cell of this table. It has to be identifiable, or the
    grid reads as a menu of results to choose from."""
    df = sweep(fake_runner, MS, {"N": 8, "M": 4, "K": 3, "L": 4}, {"N": [4, 8]}, n_boot=0)
    assert df.set_index("value")["a_priori"].to_dict() == {4: False, 8: True}

def test_sweep_labels_its_cut():
    df = sweep(fake_runner, MS, {"N": 8, "M": 4, "K": 3, "L": 4}, {"N": [4]}, cut="full", n_boot=0)
    assert df["cut"].unique().tolist() == ["full"]

def test_param_signals_covers_every_a_priori_param_that_reaches_a_signal():
    """If a new signal starts reading a param, the grid must learn about it here rather
    than silently omitting that signal from its own sensitivity report."""
    from signals import SIGNALS
    for param, names in PARAM_SIGNALS.items():
        assert set(names) <= set(SIGNALS), f"{param} names a signal that is not registered"
