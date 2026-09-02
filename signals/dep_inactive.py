"""S4b `dep_inactive` — something this item depends on has gone quiet.

Spec §7: *"depends on X for which S1 fires."* The second half of H2, and the half that
carries the actual hypothesis: not that dependencies are risky, but that an *inactive*
dependency is a leading indicator — the trouble is visible on the neighbour before it is
visible here.

This composes `hollow_owner` rather than reimplementing silence, so the two stay defined
identically: if the owner-scoped reading of S1 changes, this changes with it.

The item's own activity is deliberately not consulted. A team working hard on top of a
dead dependency is precisely the case H2 predicts, and requiring the item to be quiet too
would collapse this into S1 with extra steps.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from signals.hollow_owner import hollow_owner
from core.replay import ItemState


def dep_inactive(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when any dependency of the item satisfies S1's silence condition.

    `hollow_owner` only returns pairs for items targeting *this* milestone, so it cannot
    be asked directly about a dependency targeting another one. The silence test is
    applied to the dependency's own state through the same function, with the dependency
    treated as if it were the item under test.
    """
    out: set[tuple[str, str]] = set()
    hollow: dict[str, bool] = {}
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        for dep_id in s.deps:
            dep = states.get(dep_id)
            if dep is None:
                continue
            if dep_id not in hollow:
                # Evaluate S1 against the dependency in isolation, pinned to a milestone
                # it targets so `targets_at` admits it. Any stage will do: `hollow_owner`
                # is item-scoped in its condition and only uses stages to name rows.
                probe = next(iter(dep.targets.values()), None)
                hollow[dep_id] = bool(probe) and bool(
                    hollow_owner({dep_id: dep}, _at(ctx, probe)))
            if hollow[dep_id]:
                out.update((item_id, stage) for stage in stages)
                break
    return out


def _at(ctx: Context, milestone_id: str) -> Context:
    """`ctx` re-pointed at the dependency's own milestone, keeping `as_of` and params.

    Only the milestone identity moves. The silence window is measured from the same
    `as_of` as every other signal in this snapshot, so nothing here reads a different
    point in time.
    """
    m = ctx.milestones_by_id.get(milestone_id) or ctx.milestone
    return Context(ctx.as_of, m, ctx.milestones_by_id, ctx.org_units, ctx.config,
                   ctx.params, ctx.prior_outcomes)
