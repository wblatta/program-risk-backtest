# K8s outcome labeling rule — v1 (git history + exceptions.yaml only)

This document is **normative**. `adapters/k8s/outcomes.py` implements exactly the rule
stated here; any change to one requires the same change to the other.

Unit: one `(item, stage, milestone M)` target present in `snapshot(M.enhancements_freeze)`
(i.e. `state.targets[stage] == M.id` as of `M`'s enhancements freeze).

Evaluated only for milestones that are scheduled, have an `enhancements_freeze` date, and
whose `release` date is on or before today.

Precedence (first match wins):

1. **slipped** — after `M.enhancements_freeze`, a `target_set` for the same stage moved
   the target to a milestone with a higher ordinal than `M`. Only a genuine retarget
   counts: a `TARGET_SET` event with `payload.op == "clear"` is a retraction, not a move,
   and is excluded from this check even though it carries a `milestone_id` (see rule 2).
2. **dropped** — after `M.enhancements_freeze` and before the next milestone's
   enhancements freeze (or today, if `M` is the last scheduled milestone), either:
   - the KEP's status changed to one of `withdrawn`, `rejected`, `deferred`, `replaced`,
     `superseded`, with no retarget (rule 1 still takes precedence); or
   - a `TARGET_SET` clear (`payload.op == "clear"`) for this same `(stage, milestone)` —
     i.e. `payload.stage == stage` and `payload.milestone_id == M.id` — recording that the
     KEP's `kep.yaml` retracted this exact target.

   `slipped` always wins over `dropped`: a KEP that clears a stage and later re-adds it at
   a higher-ordinal milestone produces both a clear event (for the original milestone) and
   a normal `target_set` event (for the new one); rule 1 sees the normal `target_set` to a
   higher ordinal and reports `slipped` before rule 2's clear-based check is reached.

   **`removed` is deliberately excluded from the drop-status set.** On the real corpus,
   `removed` is a `kep.yaml` status distinct from the drop vocabulary above — it appears on
   KEPs that shipped alpha and beta years earlier and only later, once the feature itself
   was removed from Kubernetes, had their status updated to record that fact. The status
   describes the *feature's* eventual removal from the product, not that the *KEP* was
   abandoned before delivering the milestone being evaluated. Treating `removed` as a drop
   status would relabel a real, historical success as a failure. (Example on the real
   corpus: `281-dynamic-kubelet-configuration`, milestones
   `{alpha: v1.8, beta: v1.11, deprecated: v1.22, removed: v1.24}` — every one of those
   rows is a shipped deliverable in its own right.)

   Note this is unrelated to `deprecated` and `removed` as **milestone stage keys** (e.g.
   a KEP with `milestone: {deprecated: v1.24, removed: v1.24}`). A planned deprecation or
   removal is a real deliverable like any other stage and produces outcome rows the same
   way `alpha`/`beta`/`stable` do — this document only excludes `removed` the **status**
   from the drop-status set.
3. **exception_denied** — `exceptions.yaml` for `M` lists this KEP (by tracking-issue
   number, i.e. `_kep_number(item_id)`) with status not `approved`.
4. **exception_granted** — `exceptions.yaml` for `M` lists this KEP with status `approved`.
5. **shipped** — none of the above. **In v1 this means "not observed to slip", not
   "verified shipped".** Sprint 2 adds `tracked/yes` at release and code-merge evidence
   and reverses the precedence to verify shipping first.

Outcome `ts` = `M.release` (end-of-day UTC). Source = `derived`.

Known blind spots in v1: a KEP that silently stops (no retarget, no status change, no
target clear) is labeled shipped. A KEP whose yaml was updated only after the next cycle
started is still caught by rule 1 because the rule looks at all later events, not just the
next cycle.
