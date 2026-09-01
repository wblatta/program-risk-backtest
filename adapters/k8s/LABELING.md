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
5. **shipped** — positive evidence the code landed for this milestone:
   - the tracking issue closed within 90 days of the milestone's release, or
   - a `kubernetes/kubernetes` PR cross-referenced from that issue merged between
     cycle start and release.

   The evidence kind is recorded on the outcome event's `evidence` payload key, so
   every `shipped` row can name why it was called shipped.

6. **unresolved** — none of the above matched and no delivery evidence exists.

   **This is not a synonym for failure.** It means the outcome is unknown to this
   instrument. The usual cause is that nobody linked the implementation back to the
   tracking issue, not that the work stopped. Measured coverage: evidence exists for
   43.4% of rows that v1 called shipped, and for 7.0% of rows it called slipped.
   Coverage is uneven by stage — `alpha` 48.2%, `beta` 22.2%, `stable` 58.5% — because
   closure is evidence about a KEP's final stage and merges about its first.

   `unresolved` is neither positive nor negative. `POSITIVE` remains
   `{slipped, dropped, exception_denied}`.

**Deliberately not used as evidence:** the release team's `tracked/yes` label. It
appears on 51.8% of shipped rows and 40.0% of slipped ones — it records that the team
was tracking the work and is not removed when the work fails.

Outcome `ts` = `M.release` (end-of-day UTC). Source = `derived`.

## Positive class

The labels above partition into a **positive**, a **negative**, and a neutral,
excluded-from-either class. This partition is part of the normative rule —
`backtest/run.py`'s `POSITIVE` set implements exactly what is stated here, and the two
must agree exactly:

| label | class | why |
|---|---|---|
| `slipped` | **positive** | the commitment was not met at the milestone it was made for |
| `dropped` | **positive** | the commitment was abandoned |
| `exception_denied` | **positive** | the project itself refused to let the deliverable through |
| `exception_granted` | negative | a **near-miss, not a miss**: the deliverable landed, with the project's explicit consent to land late in the cycle. Counting a granted exception as a failure would score the project's own working escape hatch as a defect. Reported separately as a near-miss rather than folded into either class silently. |
| `shipped` | negative | positive evidence the code landed — see rule 5 |
| `unresolved` | **neither** | no evidence either way — see rule 6. Excluded from `POSITIVE`, and not folded into the negative class either. |

`exception_granted` is the load-bearing one: 65 rows of the first backtest sit in the
negative class because of it, and moving them would move the base rate off 0.302. It is
called out here rather than left implicit in the code.

### `exception_denied` is currently unreachable

The positive set has three members but only two of them can occur. **No corpus row can
ever be labeled `exception_denied` under the precedence above**, so `POSITIVE` is in
practice `{slipped, dropped}`.

The cause is rule 1's precedence, not missing data. Over v1.19–v1.37 the recovered
`exceptions.yaml` files hold 161 requests, 33 of them not approved; fifteen of those 33
correspond to an actual backtest row, and **all fifteen are labeled `slipped`**. A SIG
refused an exception has to retarget its `kep.yaml`, which produces a genuine `target_set`
to a higher-ordinal milestone — and rule 1 (slipped) is evaluated before rule 3
(exception_denied), so the slip wins every time. The label is unreachable for exactly the
population it was written to describe.

**This is a vocabulary defect, not a measurement one.** All fifteen shadowed rows are
labeled `slipped`, which is the correct label for a denied-then-retargeted KEP: the
deliverable did not land at the milestone it was committed to. Under the opposite
precedence those rows would read `exception_denied` and would still be in the positive
class. **No row changes class under either ordering**, and no metric in the first backtest
depends on which one is chosen. What is wrong is that the vocabulary advertises a
distinction the rule cannot express.

Labeling v2 must settle it one way or the other — either an exception decision outranks
the retarget it caused, or the label is removed and the reason published. Leaving an
unreachable member in the vocabulary is worse than either. See spec amendment 10 (sprint 1)
and `docs/sprint-1-notes.md`.

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
