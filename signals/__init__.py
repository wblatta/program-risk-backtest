from signals.hollow_owner import hollow_owner
from signals.item_silent import item_silent
from signals.process_tracked import process_tracked
from signals.prior_slip import prior_slip
from signals.late_target import late_target
from signals.gate_unassigned import gate_unassigned
from signals.cross_org import cross_org
from signals.org_overcommitted import org_overcommitted
from signals.dep_ordering_conflict import dep_ordering_conflict
from signals.dep_inactive import dep_inactive

# Spec §7 numbering: S0 process_tracked (control), S1 hollow_owner, S2 gate_unassigned,
# S3 cross_org, S5 prior_slip, S6 org_overcommitted, S7 late_target.
# `item_silent` is not in spec §7: it is the anonymous-activity proxy S1 was forced to
# use before real actors existed, kept so the two can be compared directly.
# S4a dep_ordering_conflict, S4b dep_inactive.
SIGNALS = {
    "process_tracked": process_tracked,
    "hollow_owner": hollow_owner,
    "item_silent": item_silent,
    "gate_unassigned": gate_unassigned,
    "cross_org": cross_org,
    "dep_ordering_conflict": dep_ordering_conflict,
    "dep_inactive": dep_inactive,
    "prior_slip": prior_slip,
    "org_overcommitted": org_overcommitted,
    "late_target": late_target,
}
