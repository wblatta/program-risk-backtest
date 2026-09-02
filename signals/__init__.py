from signals.hollow_owner import hollow_owner
from signals.process_tracked import process_tracked
from signals.prior_slip import prior_slip
from signals.late_target import late_target
from signals.gate_unassigned import gate_unassigned
from signals.cross_org import cross_org
from signals.org_overcommitted import org_overcommitted

# Spec §7 numbering: S0 process_tracked (control), S1 hollow_owner, S2 gate_unassigned,
# S3 cross_org, S5 prior_slip, S6 org_overcommitted, S7 late_target.
# S4a/S4b (dependency signals) require dependency extraction and are not yet built.
SIGNALS = {
    "process_tracked": process_tracked,
    "hollow_owner": hollow_owner,
    "gate_unassigned": gate_unassigned,
    "cross_org": cross_org,
    "prior_slip": prior_slip,
    "org_overcommitted": org_overcommitted,
    "late_target": late_target,
}
