# Evidenced outcomes and the hygiene signal — design

Date: 2026-09-01. Supersedes the labeling half of `adapters/k8s/LABELING.md` v1.
Sprint-1 background: [`docs/sprint-1-notes.md`](../../sprint-1-notes.md).
Measurements behind every number here: [`docs/sprint-2-notes.md`](../../sprint-2-notes.md) §2.

## 1. The problem

`shipped` is the fallthrough case of the v1 labeling rule. It means "not observed to
slip", not "verified shipped", and every measured error runs that one direction: a
ten-row manual audit returned 8 correct, 1 unverifiable, 1 wrong, and a floor of 69 of
811 `shipped` rows (8.5%) is provably wrong from the corpus itself.

The bias is not neutral with respect to the conclusions. Correcting only that floor moves
`hollow_owner` from 1.36 to 1.44 and `late_target` from 0.82 to 0.71: the labeling error
**understates the signal that works and overstates the one that does not**. Worse, one
abandoned KEP produced one true positive and two false negatives, and `hollow_owner` was
charged a false positive for correctly identifying that it had stopped. The rule
systematically penalises the best signal.

## 2. Evidence model

A row is `(item, stage, milestone)`. Two independent sources answer "did the code land":

| evidence | definition | P(e \| shipped) | P(e \| slipped) |
|---|---|---|---|
| **closure** | the KEP's tracking issue closed within 90 days of the milestone's release | 21.6% | 0.8% |
| **merge** | a `kubernetes/kubernetes` PR cross-referenced from that issue merged between cycle start and release | 24.0% | 6.5% |
| **either** | union of the two | **43.4%** | **7.0%** |

They are complementary, not redundant — the intersection is 2.2%, and their stage
profiles are inverse:

| stage | closure | merge | union |
|---|---|---|---|
| `alpha` | 3.5% | 45.5% | 48.2% |
| `beta` | 4.2% | 18.0% | 22.2% |
| `stable` | 53.9% | 10.2% | 58.5% |

A tracking issue spans a KEP's whole lifecycle and closes when the KEP *finishes*, so
closure is evidence about the final stage. Implementation PRs cluster at first delivery,
so merges are evidence about the first. `beta` sits between both and is the weakest.

Both sources come from data already on disk: 644 tracking issues and their timelines,
containing 938 `kubernetes/kubernetes` PR cross-references, each carrying `merged_at`.
**No additional API calls are required.**

### Why not `tracked/yes`

Sprint 1 assumed the release team's `tracked/yes` label was the shipping gate. It is not:
it appears on 51.8% of `shipped` rows and 40.0% of `slipped` ones. The label records that
the release team was *tracking* the work and is not removed when the work fails. Gating on
it would readmit the rows the reversal exists to exclude.

## 3. Label vocabulary

Precedence, first match wins. Rules 1–4 are unchanged from v1; rule 5 is replaced.

1. `slipped` — retargeted to a later milestone after the freeze
2. `dropped` — status moved to a drop status, or the target was retracted, within the window
3. `exception_denied` — an exception request exists and was not approved
4. `exception_granted` — an exception request exists and was approved
5. **`shipped`** — **positive evidence exists** (closure or merge, per §2)
6. **`unresolved`** — no rule above matched and no evidence exists

`unresolved` is new and is not a synonym for failure. It means the outcome is unknown to
this instrument: usually because nobody linked the implementation back to the tracking
issue, not because the work stopped.

`POSITIVE` remains `{slipped, dropped, exception_denied}`. `unresolved` is neither
positive nor negative; how it is handled is the subject of §4.

## 4. Two published cuts

Every result is reported twice, side by side:

- **Evidenced cut** — `unresolved` rows excluded. Roughly 796 rows, every label backed by
  evidence. This is the headline.
- **Full cut** — `unresolved` treated as negative (not delivered). All 1,255 rows.

Neither is "the answer". Their difference is the finding: it shows what the signals are
worth where process hygiene held, against what they are worth where it did not. A reader
deciding whether to adopt one of these signals needs both, because their own organisation
sits somewhere on that spectrum.

Publishing only the evidenced cut would hide that most of the corpus lacks a paper trail.
Publishing only the full cut would assume failure without proof — inverting the v1 bias
rather than removing it. Reporting both, labelled, lets the reader weigh it.

**Every table, CSV and figure states which cut it is.** A number that does not say is a
defect.

## 5. The hygiene signal (S8 `broken_trail`)

Absence of a paper trail is itself a candidate risk signal: a well-defined process that is
not being followed is a symptom, and symptoms should predict.

Measured post-hoc against v1 labels it scores lift 1.378 — nominally above `hollow_owner`
at 1.357 — but **that measurement is partly circular**: rows labelled `slipped` did not
ship, so they necessarily lack merge and closure records, and the predictor is partly
restating the label. That number must not be published as a signal result.

The circularity is an artifact of measuring after the fact. S8 removes it by evaluating
hygiene **at snapshot time**, like every other signal:

> Fires when, as of the current date, the item's tracking artifacts are absent or
> incomplete — no tracking issue, or no `tracked/*` label applied for the cycle in
> progress, or no linked implementation work — for an item that has committed to this
> milestone.

Evaluated before the outcome, against evidence-backed labels, this is a fair test of the
hypothesis. It may well score lower than 1.378; that is the point.

S8 is item-scoped and emits `(item_id, stage)` for every stage the item targets at the
milestone, per the granularity contract in `signals/base.py`.

### Dependency

S8 needs tracking-label history inside `snapshot()`, which today replays only git-derived
events. That requires tracking data to enter the event stream with a new `source` value
(`tracking-issue`, added to `core.model.SOURCES`) and a place in `ItemState` for
point-in-time labels. This is the one part of this design that touches the core model, and
it is the reason S8 is specified after the labeling change rather than alongside it.

## 6. What this design does not fix

- **Coverage is capped by the source.** Only 306 of 644 KEPs have any merged
  cross-referenced PR. A KEP whose implementation never referenced its tracking issue is
  invisible to the merge rule no matter how the window is tuned.
- **`beta` remains weakest** at 22.2%. Its rows are disproportionately `unresolved` and
  therefore disproportionately excluded from the evidenced cut. Any per-stage reading must
  say so.
- **Closure is coarse.** An issue closes once, at the end of the KEP's life; attributing
  that to a specific milestone uses a 90-day window, which is a heuristic.
- **A merged PR is not proof the feature shipped in that release.** It is proof code
  landed in the window. Reverts, feature gates left off, and partial implementations are
  all invisible.

Each of these belongs in the notes' "what these numbers cannot support" section, not in a
footnote.

## 7. Success criteria

1. Every row carries a label whose basis can be named: which rule fired, and for `shipped`,
   which evidence and when.
2. Both cuts are produced, clearly labelled, from one run.
3. The 69-row known-error floor either disappears from the evidenced cut or is re-measured
   against it. If rows in that floor are still labelled `shipped`, the evidence model is
   wrong and that is a finding.
4. The ten-row manual audit is re-run against the new labels. It is the only check that is
   not self-referential.
5. `LABELING.md` and the code agree exactly, as they do today.
6. No regression in the leakage guarantees: outcome evidence still joins only where
   `outcome.ts > freeze_dt`, and no evidence source reaches `snapshot()` except through
   properly timestamped events.
