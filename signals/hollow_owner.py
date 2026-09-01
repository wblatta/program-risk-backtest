"""S1. Hypothesis: nominal ownership without activity predicts slips.
Fires when an item targeting the milestone has had no activity from anyone in the last N weeks.
(v1 uses any actor; when actor ids are real, restrict to listed owners.)"""
from __future__ import annotations
from core.replay import ItemState
from signals.base import Context, targets_at


def hollow_owner(states: dict[str, ItemState], ctx: Context) -> set[str]:
    cutoff = ctx.as_of - ctx.weeks("N")
    out = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        # Activity is item-wide, so the condition is item-scoped -- but a firing
        # names rows, so emit one pair per stage this item targets here.
        last = s.last_activity_any
        if last is None or last < cutoff:
            out.update((item_id, stage) for stage in stages)
    return out
