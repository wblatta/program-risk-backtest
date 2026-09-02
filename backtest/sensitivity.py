"""Sensitivity of each signal to the a priori parameter it depends on (spec §8).

*"A small grid over N, M, K; reported, not tuned on."* The distinction is the whole
point. `params = {N: 8, M: 4, K: 3, L: 4}` were fixed before the first backtest and never
moved, which is the honest position — but a number chosen a priori and never varied leaves
a fair question open: **would a different choice have told a different story?** This module
answers it in public.

One factor at a time. Each parameter is swept across a range with the others held at their
a priori values, and only the signals that actually read that parameter are reported. A
full cross-product would multiply runs without adding information: no signal reads more
than one of these, so the interactions it would explore do not exist.

**This is a report, not a search.** The a priori cell is marked in every table. Reading
the grid and then publishing its best cell would be tuning on the test set, which is the
practice this module exists to make visible rather than to enable.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from backtest.metrics import signal_metrics
from core.model import Milestone

# Which signals each a priori parameter reaches. Sweeping N and reporting `late_target`
# would be noise: it does not read N, so its row would be identical in every cell and
# invite a reader to see stability where nothing varied.
PARAM_SIGNALS: dict[str, tuple[str, ...]] = {
    "N": ("hollow_owner", "item_silent"),
    "M": ("gate_unassigned",),
    "K": ("late_target",),
}

# Ranges bracket each a priori value on both sides. Deliberately coarse: the question is
# whether the conclusion survives a different reasonable choice, not where the optimum is.
DEFAULT_GRID: dict[str, list[int]] = {
    "N": [4, 6, 8, 10, 12],
    "M": [2, 3, 4, 6, 8],
    "K": [1, 2, 3, 4, 6],
}


def sweep(runner: Callable[[dict], list], milestones_by_id: dict[str, Milestone], base_params: dict,
          grid: dict[str, list[int]], cut: str = "evidenced", n_boot: int = 200, seed: int = 0) -> pd.DataFrame:
    """Re-run the backtest once per grid cell and tabulate the signals that cell moves.

    Args:
        runner: called with a full params dict, returns backtest rows. Injected so this
            module is testable without a corpus.
        base_params: the a priori values; every parameter not being swept holds here.
        grid: parameter -> values to try.
    """
    out = []
    for param, values in grid.items():
        names = PARAM_SIGNALS.get(param, ())
        for value in values:
            params = dict(base_params, **{param: value})
            table = signal_metrics(runner(params), milestones_by_id, L=params["L"],
                                   n_boot=n_boot, seed=seed, cut=cut)
            for _, r in table[table["signal"].isin(names)].iterrows():
                out.append({"cut": cut, "param": param, "value": value,
                            "a_priori": value == base_params[param], "signal": r["signal"],
                            "fired": int(r["fired"]), "precision": r["precision"], "lift": r["lift"],
                            "lift_ci_lo": r.get("lift_ci_lo"), "lift_ci_hi": r.get("lift_ci_hi"),
                            "median_lead_weeks": r["median_lead_weeks"], "lead_class": r["lead_class"]})
    return pd.DataFrame(out, columns=["cut", "param", "value", "a_priori", "signal", "fired", "precision",
                                      "lift", "lift_ci_lo", "lift_ci_hi", "median_lead_weeks", "lead_class"])
