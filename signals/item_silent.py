"""`item_silent` — nobody at all has touched the item in N weeks.

The proxy S1 was forced to use through sprints 1 and 2, kept as a published signal rather
than deleted. Sprint 1's activity came from git history, whose author emails do not map to
GitHub handles reliably, so every event carried an unknown actor and owner-scoped silence
could not be asked about. This tests the weaker, answerable question.

It is retained because the comparison against `hollow_owner` is itself the measurement.
If owner-scoped silence scores no better than total silence, then ownership is not the
operative variable and H1's specific claim does not survive its own weaker paraphrase —
which is worth knowing, and is invisible unless both are reported.

Every result published before this split was this signal under the other one's name.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState


def item_silent(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when the item has no activity from anyone within N weeks of `as_of`."""
    cutoff = ctx.as_of - ctx.weeks("N")
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        last = s.last_activity_any
        if last is None or last < cutoff:
            out.update((item_id, stage) for stage in stages)
    return out
