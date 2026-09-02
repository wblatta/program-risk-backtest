"""S4a `dep_ordering_conflict` — this item is due before what it depends on.

Spec §7: *"depends on X whose target for the needed stage is >= this item's milestone."*
The first half of H2 — a stale dependency is a leading indicator — in its purely
structural form. No judgment about how the dependency is going: just whether the plan
sequences at all. If A is committed to v1.30 and the thing A depends on is committed to
v1.31, the schedule is arithmetically impossible before anyone is late.

Same-milestone counts as a conflict, not as satisfied. Two items landing in one cycle with
a dependency between them have nothing sequencing them, so a slip in the dependency is a
slip in both. Reading `>=` rather than `>` is spec §7's wording and the conservative
choice.

A dependency with no target at this point in time is quiet. It may be finished, abandoned
or out of scope, and the snapshot cannot tell which; firing would mean every reference to
a long-completed enhancement raised an ordering conflict forever.

**Milestone visibility.** Ordering compares `Milestone.ordinal` through
`ctx.milestones_by_id`, which `run_backtest` has filtered to milestones at or before the
one being scored. A dependency targeting a milestone not yet visible is not resolvable and
does not fire — reaching around that filter to order against a later milestone's stored
dates would be reading post-hoc actuals. See `signals/base.py`.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState


def dep_ordering_conflict(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when any dependency targets a milestone at or after this item's."""
    here = ctx.milestone.ordinal
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        for dep_id in s.deps:
            dep = states.get(dep_id)
            if dep is None:
                continue
            ordinals = [m.ordinal for ms in dep.targets.values()
                        if (m := ctx.milestones_by_id.get(ms)) is not None]
            if ordinals and min(ordinals) >= here:
                out.update((item_id, stage) for stage in stages)
                break
    return out
