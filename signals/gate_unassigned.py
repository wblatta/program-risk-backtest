"""S2 `gate_unassigned` — a required approval role has no holder as the freeze closes in.

Spec §7: *"a required role has no holder and freeze ≤ M weeks away."* Tests H1 from a
different direction than `hollow_owner`: that one measures whether anyone is *working* on
the item, this one whether the process gate that must be cleared has anybody attached to
it. Silence and an unheld gate are different failures, and an item can have either without
the other.

**Why this signal needed the widened `Signal` contract.** Kubernetes grants PRR approval
*per stage* — an approver signed up for `alpha` says nothing about `beta`. Under the old
item-scoped contract the two collapsed, and a covered alpha would have silenced an
uncovered beta on the same item. `ItemState.stage_owners` keeps them apart and this signal
emits one pair per uncovered stage.

Which roles gate is the corpus's business, not this module's: `AdapterConfig.required_roles`
names them, and a corpus that configures none gets no firings rather than an invented gate.

**The window matters.** An unheld gate is not news in itself — most items start without an
approver and acquire one. It becomes news only once there is not much time left to fix it,
which is what `M` encodes. Before the window opens the signal is deliberately silent.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState


def gate_unassigned(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires for each targeted stage that lacks a holder for some required role, once the
    freeze is within `M` weeks.

    Reads `stage_owners`, not `owners`: the item-wide union answers "does this item have
    an approver anywhere", which is the wrong question — a stage is gated on its own
    approval, and the union would report a stage as covered because a different one was.
    """
    if not ctx.config.required_roles or ctx.milestone.freeze is None:
        return set()
    if ctx.milestone.freeze - ctx.as_of.date() > ctx.weeks("M"):
        return set()
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        for stage in targets_at(s, ctx.milestone.id):
            if any(not s.stage_owners.get(role, {}).get(stage) for role in ctx.config.required_roles):
                out.add((item_id, stage))
    return out
