"""S7. Items whose target for this milestone was set within K weeks of the commitment point
(enhancements freeze when the milestone has one, else the delivery freeze)."""
from __future__ import annotations
from datetime import datetime, time, timezone
from core.replay import ItemState
from signals.base import Context, targets_at


def late_target(states: dict[str, ItemState], ctx: Context) -> set[str]:
    m = ctx.milestone
    commit_date = m.dates.get("enhancements_freeze") or m.freeze
    if commit_date is None:
        return set()
    cutoff = datetime.combine(commit_date, time(0, 0), tzinfo=timezone.utc) - ctx.weeks("K")
    return {item_id for item_id, s in states.items()
            if any(s.target_set_at.get(stage) is not None and s.target_set_at[stage] >= cutoff
                   for stage in targets_at(s, m.id))}
