"""Per-signal precision/recall/lift/lead with bootstrap CIs. Rows without an outcome are excluded."""
from __future__ import annotations
from datetime import datetime
import numpy as np
import pandas as pd
from backtest.run import POSITIVE, UNRESOLVED, Row
from core.model import Milestone


# A slip is recorded when work is retargeted *after* its freeze, which in practice happens
# during the following cycle. A Kubernetes cycle runs ~120 days, so a milestone needs a full
# subsequent cycle plus margin before its slips are observable. 180 days is that, and the
# corpus agrees: at 7 and 133 days since release, v1.37 and v1.36 show slip rates of 0.017
# and 0.135 against a ~0.45 norm -- not better cycles, unfinished ones.
CENSOR_DAYS = 180


def uncensored_milestones(milestones, today=None, days: int = CENSOR_DAYS):
    """Milestones old enough for their outcomes to be observable.

    Right-censoring silently deflates the base rate of recent cycles, which *inflates*
    every lift measured against it -- a signal looks better precisely where the data is
    least complete. Excluding the tail costs sample size and buys an unbiased denominator.
    """
    from datetime import date as _date
    today = today or _date.today()
    return [m for m in milestones
            if m.release is not None and (today - m.release).days >= days]


def _apply_cut(rows, cut: str):
    """Evidenced: drop rows whose outcome is unknown. Full: keep them, counted as
    not-positive. The two are published side by side because their difference is the
    finding -- what the signals are worth where process hygiene held, against where it
    did not."""
    if cut == "evidenced":
        return [r for r in rows if r.outcome != UNRESOLVED]
    if cut == "full":
        return list(rows)
    raise ValueError(f"unknown cut {cut!r}; expected 'evidenced' or 'full'")


def rows_frame(rows: list[Row]) -> pd.DataFrame:
    recs = []
    for r in rows:
        d = {"item_id": r.item_id, "stage": r.stage, "milestone_id": r.milestone_id, "org_id": r.org_id, "outcome": r.outcome}
        for k, v in r.first_fired.items():
            d[f"first_fired.{k}"] = v.isoformat() if v else None
        recs.append(d)
    return pd.DataFrame(recs)


def _lead_weeks(fired: datetime, m: Milestone) -> float:
    return (m.freeze - fired.date()).days / 7


EVALUATIONS = ("first_fired", "at_freeze")


def signal_metrics(rows: list[Row], milestones_by_id: dict[str, Milestone], L: int, n_boot: int = 1000, seed: int = 0,
                   cut: str = "evidenced", evaluation: str = "first_fired") -> pd.DataFrame:
    """Per-signal precision/recall/lift, under one of two evaluation points.

    `first_fired` -- spec §8's designed metric -- asks whether the signal fired at any
    point during the cycle, and reports how early. `at_freeze` asks whether it is firing
    at the moment the commitment locks, which is the question a release lead faces.

    Both are published because they answer different questions and neither dominates. They
    must never be compared across modes: reporting one signal's freeze-point precision
    against another's first-fired lift is a published error this project already made once
    (findings.md, "what we got wrong"). The `eval` column exists so a table cannot lose
    track of which it is.
    """
    if evaluation not in EVALUATIONS:
        raise ValueError(f"unknown evaluation {evaluation!r}; expected one of {EVALUATIONS}")
    rows = _apply_cut(rows, cut)
    labeled = [r for r in rows if r.outcome is not None]
    y = np.array([r.outcome in POSITIVE for r in labeled])
    base = y.mean() if len(y) else float("nan")
    rng = np.random.default_rng(seed)
    names = sorted({k for r in labeled for k in r.first_fired})
    at_freeze = evaluation == "at_freeze"
    out = []
    for n in names:
        f = np.array([bool(r.fired_at_freeze.get(n)) if at_freeze else (r.first_fired.get(n) is not None)
                      for r in labeled])
        fired, tp = int(f.sum()), int((f & y).sum())
        prec = tp / fired if fired else float("nan")
        rec = tp / int(y.sum()) if y.sum() else float("nan")
        lift = prec / base if fired and base else float("nan")
        # Lead is undefined at a fixed evaluation point: it is zero for every firing by
        # construction, and reporting it would invite comparison against first-fired leads.
        leads = ([] if at_freeze else
                 [_lead_weeks(r.first_fired[n], milestones_by_id[r.milestone_id]) for r in labeled if r.first_fired.get(n)])
        med = float(np.median(leads)) if leads else float("nan")
        q1, q3 = (float(np.percentile(leads, 25)), float(np.percentile(leads, 75))) if leads else (float("nan"),) * 2
        boots_p, boots_l = [], []
        for _ in range(n_boot if len(y) else 0):
            idx = rng.integers(0, len(y), len(y))
            fb, yb = f[idx], y[idx]
            if fb.sum() and yb.mean():
                pb = (fb & yb).sum() / fb.sum()
                boots_p.append(pb); boots_l.append(pb / yb.mean())
        ci = lambda xs: (float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))) if xs else (float("nan"),) * 2
        plo, phi = ci(boots_p); llo, lhi = ci(boots_l)
        out.append({"signal": n, "rows": len(labeled), "base_rate": base, "fired": fired, "precision": prec, "recall": rec,
                    "lift": lift, "median_lead_weeks": med, "lead_q1": q1, "lead_q3": q3,
                    # Named `lead_class`, not `class`: it is a statement about *lead time*
                    # only -- "does this fire early enough to act on (>= L weeks)" -- and
                    # says nothing about whether the signal is predictive. A signal with
                    # sub-1.0 lift can still be `risk` here (late_target is), which is
                    # exactly the confusion the old name caused. Predictive value is the
                    # `lift` column and its CI; read them together.
                    "lead_class": ("risk" if med >= L else "status") if leads else "n/a",
                    "precision_ci_lo": plo, "precision_ci_hi": phi, "lift_ci_lo": llo, "lift_ci_hi": lhi})
    df = pd.DataFrame(out)
    df.insert(0, "eval", evaluation)
    df.insert(0, "cut", cut)
    return df


# Lifecycle order, not alphabetical: alphabetising interleaves the pipeline
# (`deprecated` and `disabled` sort between `beta` and `stable`), which makes a
# stage table read as noise. Unknown stages sort after these, alphabetically, so a
# corpus with a different vocabulary still produces a stable ordering.
STAGE_ORDER = ("alpha", "beta", "stable", "deprecated", "removed", "disabled")


def _rate_by(rows: list[Row], column: str, cut: str, order=None) -> pd.DataFrame:
    """Slip rate grouped by one row attribute. Backs both published cuts (spec §8).

    Rows with `outcome is None` are held out by the backtest, not observed negatives,
    and are excluded before any rate is taken -- counting them would dilute every
    group toward zero.
    """
    kept = [r for r in _apply_cut(rows, cut) if r.outcome is not None]
    df = rows_frame(kept)
    if df.empty:
        out = pd.DataFrame(columns=[column, "rows", "slips", "slip_rate"])
        out.insert(0, "cut", cut)
        return out
    df["slip"] = df["outcome"].isin(POSITIVE)
    g = df.groupby(column, dropna=False).agg(rows=("slip", "size"), slips=("slip", "sum")).reset_index()
    g["slip_rate"] = g["slips"] / g["rows"]
    if order is None:
        g = g.sort_values("slip_rate", ascending=False)
    else:
        rank = {v: i for i, v in enumerate(order)}
        g = g.sort_values(column, key=lambda c: c.map(lambda v: (rank.get(v, len(rank)), str(v))))
    g.insert(0, "cut", cut)
    return g


def by_org(rows: list[Row], cut: str = "evidenced") -> pd.DataFrame:
    """Slip rate per owning org unit, worst first."""
    return _rate_by(rows, "org_id", cut)


def by_stage(rows: list[Row], cut: str = "evidenced") -> pd.DataFrame:
    """Slip rate per stage, in lifecycle order.

    Spec §8 names stage alongside org as a required cut, and the evidenced-labeling
    design predicted the two evidence sources would have inverse stage profiles --
    closure is weighted toward a KEP's final stage, merges toward whichever stage the
    code landed for. Publishing the axis is what lets a reader check that.
    """
    return _rate_by(rows, "stage", cut, order=STAGE_ORDER)
