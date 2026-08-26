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
2. **dropped** — after `M.enhancements_freeze` and no later than the end of the next
   scheduled milestone's enhancements-freeze day (or today's, if `M` is the last
   scheduled milestone) — i.e. `event.ts <= window_end`, where `window_end` is that
   day at end-of-day UTC, consistent with this document's `ts = M.release` end-of-day
   convention below. "Next" means the scheduled milestone with the smallest ordinal
   greater than `M`'s, regardless of what order milestones are passed in — not simply
   the next one encountered in iteration order. Either of the following, within that
   window:
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

## exceptions.yaml: schema recovery and one known-missing milestone

`exceptions.yaml` files predating v1.24 (real examples: release-1.10, -1.11, -1.16,
-1.17, -1.21, -1.22, -1.23) use a different, older schema than the
`enhancementFreeze:`/`codeFreeze:` mapping shown above: a single flat top-level list,
with the freeze phase recorded only in a free-text header comment (e.g. `# Enhancements
Freeze Exceptions requested in 1.21`), never as structured data. `adapters/k8s/exceptions.py`
recovers these: every request from a flat-list file is still returned, tagged with
`phase = "unspecified"` rather than a phase parsed out of a comment. This is safe for
labeling because `outcome_events` builds `exc_by_issue` keyed on issue number alone and
never reads `phase` — the placeholder is honest bookkeeping, not a guess presented as
fact. `exceptions.py` also strips U+200B (zero-width space) before parsing — a data-
cleaning step, not a heuristic — which is what makes release-1.23 (a clean flat list once
the ZWSP contaminating its header comments is removed) recoverable at all.

**`release-1.20/exceptions.yaml` remains genuinely unparseable** even after ZWSP-stripping
(a block-mapping error from an unquoted trailing comma inside a nested list) and
contributes zero requests. Within the scheduled range (v1.19–v1.37), this is the one
milestone whose exception data is **known-missing** rather than **known-absent**: an
`exception_granted`/`exception_denied` label can never appear for KEPs targeting
v1.20's freezes not because no exceptions were requested, but because the record of what
was requested could not be recovered. `load_exceptions(repo, skipped=[])` surfaces this
(and any future case like it) as a `SkippedExceptionsFile(milestone_id="k8s:v1.20", ...)`
so it is never silently invisible to whoever calls it.

Known blind spots in v1: a KEP that silently stops (no retarget, no status change, no
target clear) is labeled shipped. A KEP whose yaml was updated only after the next cycle
started is still caught by rule 1 because the rule looks at all later events, not just the
next cycle. `release-1.20`'s exception data is unrecoverable (see above) — any label that
depends on it is silently as-if-no-exception-was-requested, not verified absent.
