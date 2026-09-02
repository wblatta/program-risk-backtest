"""S1 `hollow_owner` — none of the item's listed owners has touched it in N weeks.

Spec §7: *"no owner/author has `activity` on the item in the last N weeks."* This is H1 as
actually stated — the claim is not that quiet items slip, but that items whose **named
owners** go quiet slip. Every enhancement has a nominal owner; the hypothesis is that the
nominal part is what predicts.

**This signal spent sprint 1 and 2 testing something weaker.** Git author emails do not map
to GitHub handles reliably, so git-derived `activity` events all carried
an unknown actor, and the only answerable question was "has *anyone* touched this".
That proxy is published alongside as `item_silent`, and the pair is the measurement: if the
two score the same, ownership was never the operative variable and the weaker reading is
the honest one to report.

Owners are the roles a corpus declares as accountable, from `OWNER_ROLES`. A participating
SIG is not an owner — it is a stakeholder — and counting its activity would let a busy
neighbour mask an absent author.

An item with no recorded owners fires: an enhancement targeting a release with nobody
accountable for it is the condition in its most acute form, not a data gap to skip over.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState

# Accountable roles. `participating` is deliberately absent: a stakeholder's activity is
# not the owner's, and including it is how a hollow item looks staffed.
OWNER_ROLES = ("author", "approver", "owning")


def hollow_owner(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when no listed owner has activity within N weeks of `as_of`."""
    cutoff = ctx.as_of - ctx.weeks("N")
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        owners: set[str] = set()
        for role in OWNER_ROLES:
            owners |= s.owners.get(role, set())
        recent = any(ts >= cutoff for who, ts in s.last_activity.items() if who in owners)
        if not recent:
            out.update((item_id, stage) for stage in stages)
    return out
