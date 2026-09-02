"""S0 `process_tracked` — the control every other signal is measured against.

The sprint-1 notes set the bar: *"a signal that cannot beat the project's own status
field is not worth reporting."* This is that status field. The release team applies
`tracked/yes|no|out-of-tree` to a KEP's tracking issue during each cycle, recording
whether they consider the work in scope for the release. S0 fires when that record is
absent or negative as of the current date.

It is deliberately the crudest signal in the set. It reads one human-applied label and
does no inference at all. If a signal derived from activity, retarget history or
commitment timing cannot beat it, that signal is not carrying its weight — the
organisation already had the answer, written down, for free.

**Read the result carefully.** `tracked/no` is not purely a prediction: it is the
release team stating intent at the decision point, and that intent partly *causes* the
outcome it appears to predict. The absence-of-`tracked/yes` form is less exposed to
that objection, which is why both are reported. Neither is corpus-specific in shape —
any corpus with a scope-decision artifact has an equivalent — but the label vocabulary
here is Kubernetes', which is why the prefix is a parameter rather than a constant.

Labels come from `ItemState.labels`, replayed to `as_of` like every other fact, so this
signal sees the team's view *during* the cycle rather than their final word.
"""
from __future__ import annotations

from signals.base import Context, targets_at
from core.replay import ItemState

TRACKING_PREFIX = "tracked/"
TRACKED_IN_SCOPE = "tracked/yes"


def process_tracked(states: dict[str, ItemState], ctx: Context) -> set[tuple[str, str]]:
    """Fires when the project's own tracking record does not affirm this work.

    That covers two cases, both of which read as "not affirmed in scope":
      - a negative decision is recorded (`tracked/no`, `tracked/out-of-tree`), or
      - no tracking decision has been recorded at all as of this date.

    An item carrying `tracked/yes` is silent. The condition is item-scoped — the label
    is on the KEP, not on a stage — so a firing emits one pair per stage the item
    targets at this milestone, per the granularity contract in `signals/base.py`.
    """
    out: set[tuple[str, str]] = set()
    for item_id, s in states.items():
        stages = targets_at(s, ctx.milestone.id)
        if not stages:
            continue
        if TRACKED_IN_SCOPE not in s.labels:
            out.update((item_id, stage) for stage in stages)
    return out
