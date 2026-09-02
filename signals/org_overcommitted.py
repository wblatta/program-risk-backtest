"""S6 `org_overcommitted` — an org has committed to more than it has ever delivered.

Spec §7: *"owning org's targeted count > its historical max shipped per milestone."* This
is the throughput signal, and it is the only one that looks at the org rather than the
item. Kubernetes has no capacity model — no headcount, no story points, nothing to load
against — so the honest proxy for "how much can this group actually finish in a cycle" is
the most it has ever finished in a cycle (spec §13).

**Max, not mean, and not total.** The maximum is the generous reading: it asks whether the
org has committed to more than its own best-ever cycle, so a firing cannot be explained by
an ordinary off-cycle. A lifetime total would grow monotonically and silence the signal
forever; a mean would fire on roughly half of all cycles by construction.

**Leakage.** History comes from `ctx.prior_outcomes`, which `run_backtest` has already
filtered to `ts <= as_of` — the row being scored is by construction absent. Org
attribution comes from the snapshot, which is itself as-of filtered. Nothing here reads
the current cycle's result.

An org with no delivery history yet does not fire. Firing on everyone in the corpus's
first cycle would measure where the data starts, not how the org behaves.
"""
from __future__ import annotations

from collections import defaultdict

from signals.base import Context, targets_at
from core.replay import ItemState

OWNING_ROLE = "owning"

# Evidence the work landed. `exception_granted` is a near-miss and counts as delivered
# per spec §8; `unresolved` explicitly does not -- it means the instrument could not
# find out, and treating an unknown as a delivery would inflate demonstrated throughput
# and silence this signal on exactly the orgs with the worst paper trail.
DELIVERED = frozenset({"shipped", "exception_granted"})


def _owning_org(s: ItemState) -> str | None:
    owners = sorted(s.owners.get(OWNING_ROLE, ()))
    return owners[0] if owners else None


def org_overcommitted(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires for every row of every item whose owning org has committed, at this
    milestone, to more items than it has ever delivered in a single milestone."""
    org_of = {iid: _owning_org(s) for iid, s in states.items()}

    delivered: dict[tuple[str, str], set[str]] = defaultdict(set)
    for e in ctx.prior_outcomes:
        if e.payload.get("result") not in DELIVERED:
            continue
        org = org_of.get(e.item_id)
        if org is None:
            continue
        # Count items, not (item, stage) rows: an item delivering alpha and beta in one
        # cycle is one piece of work carried, not two.
        delivered[(org, e.payload["milestone_id"])].add(e.item_id)

    best: dict[str, int] = defaultdict(int)
    for (org, _milestone), items in delivered.items():
        best[org] = max(best[org], len(items))

    committed: dict[str, set[str]] = defaultdict(set)
    for item_id, s in states.items():
        org = org_of[item_id]
        if org is not None and targets_at(s, ctx.milestone.id):
            committed[org].add(item_id)

    out: set[tuple[str, str]] = set()
    for org, items in committed.items():
        if not best.get(org) or len(items) <= best[org]:
            continue
        for item_id in items:
            out.update((item_id, stage) for stage in targets_at(states[item_id], ctx.milestone.id))
    return out
