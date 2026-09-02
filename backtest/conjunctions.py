"""Signals in combination — spec §8's third cut, "S0 vs each signal", generalised.

Two signals that fire on different rows are worth more together than either apart, and the
backtest's per-signal table cannot show it. This module answers the operational question
directly: **if I act only when two independent checks agree, how often am I right, and how
much do I stop seeing?**

Three things are reported that a precision column alone would hide:

- **Recall**, beside precision. Every conjunction trades one for the other, and a 94%
  precision instrument that fires on 3% of the corpus is usually the wrong tool.
- **Jaccard overlap.** Two signals firing on the same rows cannot combine into anything
  new. Overlap says whether a pair is worth reading before its lift does.
- **Subset relationships.** If one signal's firings are wholly contained in another's, the
  "conjunction" is the smaller signal under a longer name. That is an implementation fact
  — often a correctness check, since `item_silent` is *necessarily* a subset of
  `hollow_owner` — and publishing it as a finding would be a mistake.

Conjunctions are cheap to compute and easy to over-read: with n signals there are n(n−1)/2
pairs, and the best of them will look impressive by selection alone. `min_fired` exists to
keep pairs that fire on a handful of rows out of the table entirely.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from backtest.metrics import EVALUATIONS, _apply_cut
from backtest.run import POSITIVE, Row
from core.model import Milestone


def _mask(rows: list[Row], name: str, at_freeze: bool) -> np.ndarray:
    if at_freeze:
        return np.array([bool(r.fired_at_freeze.get(name)) for r in rows])
    return np.array([r.first_fired.get(name) is not None for r in rows])


def _subset_label(masks: dict[str, np.ndarray], names: tuple[str, ...]) -> str | None:
    """Names a containment relation between exactly two signals, if there is one."""
    if len(names) != 2:
        return None
    a, b = names
    ma, mb = masks[a], masks[b]
    if not ma.any() or not mb.any():
        return None
    if (ma & ~mb).sum() == 0:
        return f"{a} ⊆ {b}"
    if (mb & ~ma).sum() == 0:
        return f"{b} ⊆ {a}"
    return None


def conjunction_metrics(rows: list[Row], names: list[str], milestones_by_id: dict[str, Milestone],
                        cut: str = "evidenced", evaluation: str = "first_fired", max_size: int = 2,
                        min_fired: int = 20, n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Precision, recall, lift and CIs for each signal alone and for each combination.

    Args:
        names: signals to combine. Order does not matter; output is sorted.
        max_size: 2 for pairs (default), 3 to include triples.
        min_fired: drop combinations firing on fewer rows than this. A conjunction on a
            handful of rows has a precision but not a finding.
    """
    if evaluation not in EVALUATIONS:
        raise ValueError(f"unknown evaluation {evaluation!r}; expected one of {EVALUATIONS}")
    labeled = [r for r in _apply_cut(rows, cut) if r.outcome is not None]
    if not labeled:
        return pd.DataFrame(columns=["cut", "eval", "signals", "size", "fired", "fired_pct",
                                     "precision", "recall", "lift", "lift_ci_lo", "lift_ci_hi",
                                     "jaccard", "subset"])
    at_freeze = evaluation == "at_freeze"
    y = np.array([r.outcome in POSITIVE for r in labeled])
    base = y.mean()
    positives = int(y.sum())
    masks = {n: _mask(labeled, n, at_freeze) for n in names}
    rng = np.random.default_rng(seed)

    out = []
    for size in range(1, max_size + 1):
        for combo in combinations(sorted(names), size):
            m = masks[combo[0]].copy()
            for n in combo[1:]:
                m &= masks[n]
            fired = int(m.sum())
            if size > 1 and fired < min_fired:
                continue
            if not fired:
                continue
            prec = (m & y).sum() / fired
            boots = []
            for _ in range(n_boot):
                i = rng.integers(0, len(y), len(y))
                mb, yb = m[i], y[i]
                if mb.sum() and yb.mean():
                    boots.append(((mb & yb).sum() / mb.sum()) / yb.mean())
            lo, hi = ((float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
                      if boots else (float("nan"), float("nan")))
            union = None
            if size == 2:
                a, b = combo
                u = int((masks[a] | masks[b]).sum())
                union = fired / u if u else float("nan")
            out.append({"cut": cut, "eval": evaluation, "signals": " AND ".join(combo), "size": size,
                        "fired": fired, "fired_pct": fired / len(labeled), "precision": prec,
                        "recall": (m & y).sum() / positives if positives else float("nan"),
                        "lift": prec / base if base else float("nan"),
                        "lift_ci_lo": lo, "lift_ci_hi": hi,
                        "jaccard": union, "subset": _subset_label(masks, combo)})
    return pd.DataFrame(out).sort_values(["size", "lift"], ascending=[True, False]).reset_index(drop=True)
