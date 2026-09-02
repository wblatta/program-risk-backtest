"""MCP wrapper over the store (spec §2, priority 3; §11 names FastMCP).

A thin binding. Everything worth testing lives in `backtest/query.py`; this file adds
transport and nothing else, which is why it has no logic to test.

Read-only by construction: there is no tool here that writes. The leakage boundary is
enforced in `CorpusQuery`, not here, so it cannot be bypassed by calling a tool directly —
`snapshot_at` never returns an outcome, and `signals_firing` refuses a date after the
milestone's freeze rather than answering a question whose answer would be misread as a
prediction.

Run:  .venv/bin/python mcp_server.py
"""
from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from adapters.k8s.config import CONFIG
from backtest.query import CorpusQuery
from core.store import Store

CACHE = Path(__file__).parent / "cache"
OUT = Path(__file__).parent / "out"
CORPUS = "k8s"

mcp = FastMCP("program-risk-backtest")
_query: CorpusQuery | None = None


def query() -> CorpusQuery:
    """Loaded once, on first use — the event stream is ~69k rows and re-reading it per
    tool call would dominate every response."""
    global _query
    if _query is None:
        s = Store(CACHE / "store.sqlite")
        _query = CorpusQuery(CORPUS, s.load_events(CORPUS), s.load_milestones(CORPUS),
                             s.load_org_units(CORPUS), s.load_items(CORPUS), CONFIG)
    return _query


@mcp.tool
def list_milestones() -> list[dict]:
    """Every release milestone in the corpus, with its freeze and release dates."""
    return query().milestones()


@mcp.tool
def snapshot_at(as_of: str) -> dict:
    """What the roadmap said on a given date (YYYY-MM-DD).

    Reconstructed by replaying the event stream to that date. Contains no outcome: this
    is what was knowable then, not what happened after.
    """
    return query().snapshot_at(as_of)


@mcp.tool
def signals_firing(milestone_id: str, as_of: str) -> list[dict]:
    """Which risk signals fire, per committed row, for a milestone on a given date.

    Refuses dates after the milestone's freeze — signals evaluated after the commitment
    locks are not predictions.
    """
    return query().signals_firing(milestone_id, as_of)


@mcp.tool
def item_history(item_id: str) -> list[dict]:
    """Every recorded event for one item, oldest first.

    An audit view of the past: unlike `snapshot_at`, this does include outcomes. Do not
    feed it to anything that makes a prediction.
    """
    return query().item_history(item_id)


@mcp.tool
def signal_metrics(cut: str = "evidenced", evaluation: str = "first_fired") -> list[dict]:
    """The backtest's per-signal table: precision, recall, lift and 95% CIs.

    `cut` is "evidenced" (verified outcomes only) or "full" (unknowns counted as
    not-delivered). `evaluation` is "first_fired" (any time during the cycle) or
    "at_freeze" (at the moment the commitment locks). Never compare across either axis.
    """
    import csv
    name = {("evidenced", "first_fired"): "signals.csv",
            ("evidenced", "at_freeze"): "signals_at_freeze.csv",
            ("full", "first_fired"): "signals_full.csv",
            ("full", "at_freeze"): "signals_full_at_freeze.csv"}.get((cut, evaluation))
    if name is None:
        raise ValueError(f"unknown cut/evaluation {cut!r}/{evaluation!r}")
    path = OUT / CORPUS / name
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run `cli.py backtest` first")
    with path.open() as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    mcp.run()
