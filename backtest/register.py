"""The live view (spec §9) — run every signal on `snapshot(now)` and say what is firing.

*"`register --milestone <id>` runs every signal on `snapshot(now)` and prints one line per
item with the signals firing, each annotated with its backtest precision and `lead_class`.
Split into two sections by `lead_class`: risk and status."*

The split is the product. A backtest tells you which signals predict; a register tells you
what they are saying about work in flight right now — and the only reason to look is to
decide whether to do something. A firing you cannot act on is a status update, and mixing
the two is how a risk register becomes a report nobody reads. `lead_class` is measured, not
asserted: it comes from the median lead time this signal actually achieved on this corpus.

**A register is only as good as its backtest.** Every annotation here — precision, lift,
lead class — is a historical measurement carried forward, and it is honest only while the
backtest that produced it describes the same corpus and the same signals. Requiring a
completed backtest for the same corpus is spec §9's constraint and this module enforces it
by taking the metrics table as an argument rather than inventing defaults.

An unbacktested signal is reported without annotations rather than dropped. It fired; a
reader needs to know that, and a fabricated precision would be worse than a blank.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from core.model import Milestone


@dataclass(frozen=True)
class SignalHit:
    name: str
    precision: float | None
    lift: float | None
    lead_class: str


@dataclass
class RegisterLine:
    item_id: str
    stage: str
    risk: list[SignalHit] = field(default_factory=list)
    status: list[SignalHit] = field(default_factory=list)

    @property
    def top_precision(self) -> float:
        best = [h.precision for h in self.risk + self.status if h.precision is not None]
        return max(best) if best else -1.0


def build_register(firing: dict[tuple[str, str], list[str]], metrics: pd.DataFrame,
                   milestone: Milestone, cut: str = "evidenced") -> list[RegisterLine]:
    """One line per firing row, signals split by `lead_class` and ordered by precision.

    Args:
        firing: (item_id, stage) -> names of signals firing on it now.
        metrics: a completed backtest's `signal_metrics` table.
    """
    table = metrics[metrics["cut"] == cut] if "cut" in metrics.columns else metrics
    by_name = {r["signal"]: r for _, r in table.iterrows()}

    lines: list[RegisterLine] = []
    for (item_id, stage), names in firing.items():
        if not names:
            continue
        line = RegisterLine(item_id, stage)
        for name in names:
            row = by_name.get(name)
            hit = SignalHit(name,
                            float(row["precision"]) if row is not None else None,
                            float(row["lift"]) if row is not None else None,
                            str(row["lead_class"]) if row is not None else "n/a")
            # An unmeasured signal cannot claim to be actionable, so it lands in `status`
            # -- the section that makes no promise about lead time.
            (line.risk if hit.lead_class == "risk" else line.status).append(hit)
        for bucket in (line.risk, line.status):
            bucket.sort(key=lambda h: (-(h.precision if h.precision is not None else -1), h.name))
        lines.append(line)

    lines.sort(key=lambda l: (-l.top_precision, l.item_id, l.stage))
    return lines


def format_register(lines: list[RegisterLine], milestone: Milestone, cut: str = "evidenced") -> str:
    """Plain text, because the audience reads this in a terminal during a release cycle."""
    head = [f"register — {milestone.id}"
            + (f", freeze {milestone.freeze.isoformat()}" if milestone.freeze else "")
            + f"  [{cut} cut]"]
    if not lines:
        return "\n".join(head + ["", "no signals firing on work committed to this milestone."])

    def render(hits):
        return ", ".join(
            h.name + (f" (p={h.precision:.2f}, lift={h.lift:.2f})" if h.precision is not None else " (unmeasured)")
            for h in hits)

    head.append("")
    for section, key in (("risk — actionable before freeze", "risk"),
                         ("status — fires too late to change the outcome", "status")):
        rows = [l for l in lines if getattr(l, key)]
        head.append(f"## {section}  ({len(rows)} rows)")
        if not rows:
            head.append("  (none)")
        for l in rows:
            head.append(f"  {l.item_id}  {l.stage:<10}  {render(getattr(l, key))}")
        head.append("")
    return "\n".join(head).rstrip() + "\n"
