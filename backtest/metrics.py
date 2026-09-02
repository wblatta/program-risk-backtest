"""Per-signal precision/recall/lift/lead with bootstrap CIs. Rows without an outcome are excluded."""
from __future__ import annotations
from datetime import datetime
import numpy as np
import pandas as pd
from backtest.run import POSITIVE, UNRESOLVED, Row
from core.model import Milestone


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


def signal_metrics(rows: list[Row], milestones_by_id: dict[str, Milestone], L: int, n_boot: int = 1000, seed: int = 0,
                   cut: str = "evidenced") -> pd.DataFrame:
    rows = _apply_cut(rows, cut)
    labeled = [r for r in rows if r.outcome is not None]
    y = np.array([r.outcome in POSITIVE for r in labeled])
    base = y.mean() if len(y) else float("nan")
    rng = np.random.default_rng(seed)
    names = sorted({k for r in labeled for k in r.first_fired})
    out = []
    for n in names:
        f = np.array([r.first_fired.get(n) is not None for r in labeled])
        fired, tp = int(f.sum()), int((f & y).sum())
        prec = tp / fired if fired else float("nan")
        rec = tp / int(y.sum()) if y.sum() else float("nan")
        lift = prec / base if fired and base else float("nan")
        leads = [_lead_weeks(r.first_fired[n], milestones_by_id[r.milestone_id]) for r in labeled if r.first_fired.get(n)]
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
    df.insert(0, "cut", cut)
    return df


def by_org(rows: list[Row], cut: str = "evidenced") -> pd.DataFrame:
    rows = _apply_cut(rows, cut)
    df = rows_frame([r for r in rows if r.outcome is not None])
    if df.empty:
        out = pd.DataFrame(columns=["org_id", "rows", "slips", "slip_rate"])
        out.insert(0, "cut", cut)
        return out
    df["slip"] = df["outcome"].isin(POSITIVE)
    g = df.groupby("org_id", dropna=False).agg(rows=("slip", "size"), slips=("slip", "sum")).reset_index()
    g["slip_rate"] = g["slips"] / g["rows"]
    g = g.sort_values("slip_rate", ascending=False)
    g.insert(0, "cut", cut)
    return g
