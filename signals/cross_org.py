"""S3 `cross_org` — more than one org unit is involved in the item.

Spec §7 lists this as an H1 variant: the claim is not about *who* owns the work but about
how many groups have to agree. Coordination across organisational boundaries is the
classic delivery tax, and unlike `hollow_owner` it is knowable on day one — an item's SIG
composition is usually declared at creation, so if it predicts anything it predicts with
the whole cycle as lead time.

**Reading of the spec phrase.** §7 says *"> 1 participating org unit"*, which taken
literally would need two entries in `participating-sigs` *plus* the owner — three orgs
before a signal named `cross_org` fires. That does not match the name or the hypothesis, so
this counts **distinct org units involved** — owning ∪ participating — and fires above one.
The looser reading is also the one that can be wrong in the useful direction: if
coordination cost is real, it should show at two orgs.

Deduplicating by set union matters on this corpus: Enhancement records routinely list the owning SIG
again under `participating-sigs`, which by list length would look like coordination and by
set union correctly does not.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState

ORG_ROLES = ("owning", "participating")


def cross_org(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when an item involves more than one distinct org unit.

    The condition is item-scoped -- org composition is a property of the item, not of a
    stage -- so a firing emits one pair per stage the item targets here, per the
    granularity contract in `signals/base.py`.
    """
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        orgs: set[str] = set()
        for role in ORG_ROLES:
            orgs |= s.owners.get(role, set())
        if len(orgs) > 1:
            out.update((item_id, stage) for stage in stages)
    return out
