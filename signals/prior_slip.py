"""S5. Baseline: a stage that has already been retargeted once slips again."""
from __future__ import annotations
from core.replay import ItemState
from signals.base import Context, targets_at


def prior_slip(states: dict[str, ItemState], ctx: Context) -> set[str]:
    return {(item_id, stage) for item_id, s in states.items()
            for stage in targets_at(s, ctx.milestone.id)
            if len(s.target_history.get(stage, [])) > 1}
