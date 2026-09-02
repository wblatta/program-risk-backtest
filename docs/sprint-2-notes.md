# Sprint 2 notes

Date: 2026-09-01. Running record; one section per landed change.

Sprint 1's results and caveats are in [`sprint-1-notes.md`](sprint-1-notes.md). Its
Results section is superseded by the figures here, for the reason below.

---

## 1. `Signal` widened to `(item_id, stage)`

Sprint 1 shipped signals typed `Callable[..., set[str]]` — a set of *item ids* — while
the unit of analysis is the `(item, stage, milestone)` triple of `backtest.run.Row`.
`run_backtest` bridged the gap by broadcasting each returned item id across every stage
that item targeted at the milestone. Signals now return `{(item_id, stage)}` and the
broadcast is gone.

The stated motivation was to unblock spec §7's S2 `gate_unassigned`: required-approval
roles are granted per stage, so an S2 that correctly fires for `stable` would have been
broadcast onto the same item's `alpha` and `beta` rows and scored them as flagged when
they were not. That motivation stands, and S2 can now be written.

### It changed the results, for a reason sprint 1 did not identify

Sprint 1 predicted the blast radius was the 7 multi-stage `(item, milestone)` pairs
covering 18 of 1,255 rows, and expected no change, since "all three sprint-1 signals
agree across stages by construction."

The first half is right and the conclusion is wrong. Per-stage qualification genuinely
never differs within those 7 pairs — measured directly, for both stage-scoped signals,
at every milestone's enhancements freeze. But **99 row-signal firings changed anyway**,
because the real mechanism is temporal rather than structural.

`committed` is the stage set observed at the **enhancements freeze**. The old broadcast
matched on item id alone, so a firing at any earlier week was credited to every row in
that freeze-time set — including rows whose target did not yet exist in the snapshot at
that week. Concretely, `k8s:kep-1797` at `v1.20`:

| week | targets at v1.20 |
|---|---|
| 2020-09-14 | `stable` |
| 2020-09-21 | `stable` |
| 2020-09-28 | `stable` |
| 2020-10-05 | `beta` (stable moved to v1.22) |
| 2020-10-06 (freeze) | `beta` |

The row is `beta @ v1.20`. `hollow_owner` fired on 2020-09-14, when the item targeted
`stable` at that milestone and no `beta` commitment existed — and the old contract
recorded that as the row's `first_fired`, three weeks early.

This is freeze-time knowledge leaking backwards into earlier weeks. It is not a leak of
*outcome* information — the leakage boundary in `core/replay.snapshot()` and the
`outcome.ts > freeze_dt` join are untouched — but it runs in the direction that flatters
the signals, by lengthening lead times and granting firings on rows that were not yet
committed.

Changed firings: `hollow_owner` 69 rows, `prior_slip` 29, `late_target` 1.

### Corrected results

1,255 rows, base rate 0.302 — unchanged, since only `first_fired` moved and no outcome
label changed. Bootstrap CIs, n=1000, seed=0.

| signal | fired | precision | recall | lift | 95% CI | median lead | IQR |
|---|---|---|---|---|---|---|---|
| `hollow_owner` | 505 | 0.410 | 0.546 | **1.357** | 1.253 – 1.463 | 8.6 wks | 4.3 – 9.6 |
| `prior_slip` | 482 | 0.330 | 0.420 | **1.092** | 0.997 – 1.206 | 7.3 wks | 5.3 – 9.3 |
| `late_target` | 772 | 0.247 | 0.504 | **0.819** | 0.748 – 0.883 | 5.3 wks | 4.3 – 6.3 |

Against sprint 1:

| signal | fired | lift | median lead |
|---|---|---|---|
| `hollow_owner` | 561 → 505 | 1.310 → **1.357** | 9.3 → **8.6** wks |
| `prior_slip` | 483 → 482 | 1.097 → **1.092** | 8.1 → **7.3** wks |
| `late_target` | 773 → 772 | 0.822 → **0.819** | 5.3 → 5.3 wks |

**`hollow_owner` improved.** Removing 69 firings raised its precision from 0.396 to
0.410, so the removed firings were disproportionately on negative rows: false positives
bought with borrowed time. Its lead time shortened by the same correction.

**`prior_slip` is no longer significant on the full sample.** Its CI lower bound moved
from 1.002 to 0.997 and now includes 1.0. Sprint 1 already reported it as failing on the
censoring cut (0.985) and described it as marginal; it now fails on both. Read as: there
is no sample in which `prior_slip` is distinguishable from no effect.

> **Superseded by §3.** That last sentence was true of every sample that existed when it
> was written, and false once outcomes were evidenced: on the evidenced cut `prior_slip`
> lifts 1.176 with a CI of [1.084, 1.282], clear of 1.0. The tables in this section are
> the full cut and remain correct as such.

**`late_target` is unchanged in substance** — still negatively predictive, entire CI
below 1.0 across 772 firings.

Censoring cut (v1.19–v1.35, n=1,105, base 0.336), same shape as sprint 1:

| signal | lift | 95% CI | median lead |
|---|---|---|---|
| `hollow_owner` | 1.342 | 1.241 – 1.444 | 8.3 wks |
| `prior_slip` | 1.085 | 0.979 – 1.202 | 7.3 wks |
| `late_target` | 0.818 | 0.748 – 0.888 | 5.1 wks |

### Contract, for whoever writes the next signal

Stated in full at the `Signal` type in `signals/base.py`. In short: emit one pair per
stage the firing genuinely covers. An item-scoped condition (`hollow_owner` reads
item-wide activity) still emits a pair for every stage the item targets at that
milestone; a stage-scoped condition emits only the qualifying stages. Do not reintroduce
an `any(...)` over stages — that was the item-scoped shape. A signal returning bare item
ids now matches nothing and fires on no row, deliberately, so the mistake fails visibly.

### Not carried forward

Two derived analyses in the sprint-1 notes were computed against the pre-widening
figures and are **not** recomputed here:

- The 69-row false-`shipped` reclassification sensitivity. Its input set is unchanged —
  the widening moved `first_fired` only, and the `shipped` population is still 811 — but
  both endpoints of the sensitivity table moved with the corrected firings.

  **A note on an error in an earlier draft of this file:** it reported that the criterion
  could not be reproduced, yielding 10 rows across 5 KEPs rather than 69 across 48, and
  flagged the published bound as unverifiable. That was wrong, and the fault was in the
  reproduction. The check for "any spelling of `implemented`" was a substring test, and
  `"implement" in "implementable"` is `True` — so 59 rows whose status is `implementable`
  were silently excluded. `implementable` means *ready to be implemented*: the opposite of
  shipped, and precisely the rows the bound exists to catch. Matching the status properly
  gives **69 rows across 48 KEPs**, exactly as the sprint-1 notes state. The criterion as
  written there is correct and reproducible.

  The hazard is one this project already documented — `kep.yaml` statuses are dirty, and
  the sprint-1 notes single out `2625-cpumanager-policies-thread-placement` as "the row
  that would break any code switching on `status` literally". A substring test over that
  vocabulary is the same mistake in a different costume.

- The rename-artifact bound (`hollow_owner` 1.310 → 1.295). Its input set is unchanged,
  but both endpoints moved.

Neither affects the corrected table above, which is computed from the committed CSVs.

### Status of sprint 1's P0 list

1. Reverse the labeling precedence — **not started.** Now unblocked by GitHub auth, which
   makes the tracking-issue API data reachable.
2. Widen `Signal` to `(item_id, stage)` — **done, this section.**

---

## 2. Tracking-issue data landed — and it does not say what sprint 1 assumed

Sprint 1's plan for reversing the labeling precedence was: require positive evidence of
delivery, drawn from "the tracking issue closed with `tracked/yes` at release, or
code-merge evidence." The data is now in hand — 644 issues and their full label
timelines, 7,322 label events — and that plan needs revising.

### What was built

`adapters/k8s/github.py` is a rate-limit-disciplined REST client; `adapters/k8s/tracking.py`
parses issues and replays label history. Every KEP has a tracking issue whose **number is
the KEP number**, carrying the release team's `tracked/*`, `stage/*`, `lead-opted-in` and
`sig/*` labels.

Current labels are the wrong shape for a backtest — they describe today, not what was
knowable at a past date. The timeline endpoint gives `labeled`/`unlabeled` events with
timestamps, so `labels_at()` replays them to any date using the same inclusive `as_of`
convention as `core.replay.snapshot()`. The difference is real, not theoretical:
`kep-3257` carries `stage/stable` today, but on 2022-09-09 it carried `stage/alpha` and
`lead-opted-in`.

Rate-limit discipline is three mechanisms, each with a test: a **reserve** that raises
rather than spending the budget to zero; **ETag conditional requests**, which GitHub does
not charge quota for, making re-runs nearly free; and **`Retry-After`** compliance on
secondary limits. `fetch_tracking()` writes each issue as it arrives and stops cleanly at
the first `RateLimitError`, so a partial run resumes rather than restarting. A full cold
pass is ~1,300 requests against a 5,000/hour authenticated budget.

### `tracked/yes` is not evidence of shipping

Measured against the 1,255 backtest rows, at each row's milestone release date:

| evidence at release | P(evidence \| shipped) | P(evidence \| slipped) | separation |
|---|---|---|---|
| `tracked/yes` | 51.8% | 40.0% | +11.8% |
| `stage/<row stage>` | 41.4% | 34.1% | +7.4% |
| `tracked/no` | 15.7% | 30.8% | −15.2% |
| `lifecycle/stale\|rotten` ever | 45.7% | 48.9% | −3.2% |
| **issue closed within +90d** | **21.6%** | **0.8%** | **+20.8%** |

`tracked/yes` barely separates the classes. That label records that the release team was
*tracking* the work for a release; it is not removed when the work fails, so it survives
on 40% of the rows that slipped. Using it as the shipping gate would have admitted
those — the same fallthrough failure the reversal exists to eliminate, wearing a label
that looks like evidence.

**Issue closure is the real signal.** Only 0.8% of slipped rows have it, so it is close to
conclusive when present.

### But closure only exists for one stage

| shipped rows | closed within +90d |
|---|---|
| `stable` | 153 / 284 (53.9%) |
| `beta` | 11 / 261 (4.2%) |
| `alpha` | 9 / 257 (3.5%) |

A tracking issue spans a KEP's entire lifecycle and closes when the KEP *finishes*, so
closure is evidence about the final stage and almost nothing else. Roughly 78% of
currently-`shipped` rows have no positive delivery evidence in this data at all.

### What that means for reversing the precedence

The reversal as specified is not achievable uniformly across stages with this source. The
options are genuinely different studies, and the choice is not mine to make:

1. **Reverse it anyway.** `shipped` requires closure evidence; everything else becomes
   `unresolved` and leaves the metrics. That yields a high-confidence corpus of roughly
   450 rows, heavily weighted toward `stable`, and discards about two-thirds of the
   sample — including nearly all `alpha` and `beta` commitments, which are the majority
   of the work.
2. **Reverse it for `stable` only**, leaving `alpha`/`beta` on the v1 rule with the
   caveat intact. Keeps the sample, but the labeling rule then differs by stage, which
   has to be reported everywhere the numbers are.
3. **Find a different evidence source for alpha/beta.** Code-merge evidence — the PRs
   referenced from the KEP — is the obvious candidate and was always the other half of
   sprint 1's sentence. It is a larger build: PR lookups per KEP, not one issue each.

Option 3 is the one that actually answers the question, and options 1 and 2 are both
retreats from it. Nothing has been implemented; the labeling rule is unchanged.

### Status of sprint 1's P0 list

1. Reverse the labeling precedence — **blocked on a design decision**, above. The evidence
   source sprint 1 named does not support it.
2. Widen `Signal` to `(item_id, stage)` — **done**, §1.
3. Land the tracking-issue API data — **done**, this section. The data is fetched, parsed,
   and characterised; what it cannot do is now measured rather than assumed.

---

## 3. Evidenced outcomes

`shipped` was the fallthrough. Sprint 1's rule checked for a retarget, a drop, and an
exception, and if none of them matched it called the row `shipped` — so the label meant
"not observed to slip", not "verified shipped". Sprint 1 measured a floor of 69 of 811
`shipped` rows that could be shown wrong from the corpus itself, and every error in the
ten-row manual audit ran the same direction. A label that is assigned by exhaustion
absorbs every gap in the instrument as a success.

Rules 5 and 6 in [`LABELING.md`](../adapters/k8s/LABELING.md) now read the other way:

5. **shipped** — positive evidence the code landed for this milestone: the tracking issue
   closed between cycle start and 90 days after release, **or** a `kubernetes/kubernetes`
   PR cross-referenced from that issue merged between cycle start and release. The
   evidence kind is written to the outcome event's `evidence` key, so every `shipped` row
   can name why.
6. **unresolved** — nothing matched and no delivery evidence exists.

`unresolved` is the new label and the whole design turns on what it means: **unknown to
this instrument, not failed.** The usual cause is that nobody linked the implementation
back to the tracking issue. `POSITIVE` stays `{slipped, dropped, exception_denied}`;
`unresolved` is neither positive nor negative, which is why the results below are
published under two cuts rather than one.

### `tracked/yes` was rejected as evidence

§2 measured the candidate evidence sources and the obvious one lost. The release team's
`tracked/yes` label appears on **51.8% of shipped rows and 40.0% of slipped ones**. It
records that the release team was *tracking* the work for a release, and it is not removed
when the work fails. Gating `shipped` on it would have admitted 40% of the failures — the
same fallthrough it was meant to replace, wearing a label that looks like evidence. Issue
closure separates the classes (21.6% vs 0.8%) and is what rule 5 uses, alongside merges.

### The label distribution

1,255 rows, before and after:

| label | v1 rule | evidenced rule |
|---|---|---|
| `shipped` | 811 | **330** |
| `unresolved` | — | **481** |
| `slipped` | 370 | 370 |
| `exception_granted` | 65 | 65 |
| `dropped` | 9 | 9 |

The three unchanged labels are the check that precedence was not disturbed. Evidence is
consulted only in the rule-5/6 branch, after rules 1–4 have had their say, so `slipped`,
`exception_granted` and `dropped` come out byte-identical to the pre-change baseline. If
they had moved, the reversal would have been rewriting outcomes it was not supposed to
touch.

### Coverage, and where it is thin

Evidence exists for **40.7% of the rows v1 called `shipped` (330/811)** and for **7.0% of
the rows it called `slipped` (26/370)** — the asymmetry is the point, since evidence is
supposed to be rare on rows that did not deliver.

By stage, against v1's `shipped` rows:

| stage | evidence | share |
|---|---|---|
| `alpha` | 123 / 257 | 47.9% |
| `beta` | 49 / 261 | **18.8%** |
| `stable` | 154 / 284 | 54.2% |

`beta` is weakest by a wide margin, and the mechanism is structural: a tracking issue
closes once, at the end of a KEP's life, so closure is evidence about the final stage;
cross-referenced merges cluster on the first. `beta` is in the middle and gets neither.
212 of 417 `beta` rows are now `unresolved`, so **the evidenced cut under-represents `beta`
and any per-stage reading has to say so.**

### Two cuts, and the denominators that separate them

- **evidenced** — 774 rows, `unresolved` excluded. Base rate **0.490**.
- **full** — all 1,255 rows, `unresolved` counted as non-positive. Base rate **0.302**.

Bootstrap CIs, n=1000, seed=0.

**evidenced cut** (n=774, base 0.490):

| signal | fired | precision | recall | lift | 95% CI | median lead | IQR |
|---|---|---|---|---|---|---|---|
| `hollow_owner` | 304 | 0.681 | 0.546 | **1.391** | 1.304 – 1.494 | 8.4 wks | 5.3 – 10.3 |
| `prior_slip` | 276 | 0.576 | 0.420 | **1.176** | 1.084 – 1.282 | 7.3 wks | 5.3 – 9.3 |
| `late_target` | 482 | 0.396 | 0.504 | **0.809** | 0.752 – 0.864 | 4.6 wks | 4.3 – 6.3 |

**full cut** (n=1,255, base 0.302):

| signal | fired | precision | recall | lift | 95% CI | median lead | IQR |
|---|---|---|---|---|---|---|---|
| `hollow_owner` | 505 | 0.410 | 0.546 | **1.357** | 1.253 – 1.463 | 8.6 wks | 4.3 – 9.6 |
| `prior_slip` | 482 | 0.330 | 0.420 | **1.092** | 0.997 – 1.206 | 7.3 wks | 5.3 – 9.3 |
| `late_target` | 772 | 0.247 | 0.504 | **0.819** | 0.748 – 0.883 | 5.3 wks | 4.3 – 6.3 |

The full-cut table is identical to §1's, to every digit, and that is a check rather than a
coincidence: `shipped` and `unresolved` are both non-positive, so relabelling 481 rows from
one to the other cannot move a metric computed over all 1,255. Any difference would have
meant the reversal had disturbed the positive set.

**Read the lift columns across the cuts and nothing else.** The 481 rows dropped from the
evidenced cut were overwhelmingly shipped-side, so removing them lifts the base rate from
0.302 to 0.490 — nearly half of what remains is a positive. Lift is normalised by base
rate, so it is comparable. **Precision is not**: `hollow_owner` reads 0.410 against 0.681
between the tables and its behaviour did not change; the population it is being scored
against did. Recall happens to be identical in both tables, and for the same reason —
every excluded row was a non-positive, so the positive set is the same set either way.
A reader who assumes the two tables describe the same 1,255 rows will misread the
precision column badly.

### The finding: `prior_slip` crosses the boundary

**Under the evidenced cut `prior_slip`'s CI is [1.084, 1.282] — clear of 1.0. Under the
full cut it is [0.997, 1.206] — it includes 1.0.** Same signal, the same firings on the rows the
two cuts share, opposite verdicts on significance.

Where a paper trail exists, "it slipped before" predicts. Where it does not, the signal is
indistinguishable from noise. This is the clearest statement of what the two cuts are for,
and it is also a warning about what a single number would have hidden: sprint 1 and §1 of
this file both reported `prior_slip` as failing, and that finding was true only of a
sample in which 38% of the rows had no verified outcome at all.

What it does **not** establish is that `prior_slip` predicts slippage in general. The
evidenced cut is not a random subsample — it is the subsample where somebody linked the
work back to its tracking issue, which is itself a hygiene property — and hygiene is not
independent of delivery. The honest statement is narrower than the
significance test: on rows with verified outcomes, `prior_slip` clears 1.0; on the full
sample it does not; and the two populations differ in a way that is plausibly related to
the outcome.

**`hollow_owner` holds up under both** — 1.391 [1.304, 1.494] evidenced, 1.357 [1.253,
1.463] full, CIs clear of 1.0 in both, median lead 8.4 and 8.6 weeks. It is the one signal
whose reading does not depend on which cut you are looking at.

**`late_target` is backwards under both** — 0.809 [0.752, 0.864] and 0.819 [0.748, 0.883],
entire CI below 1.0 either way. Requiring evidence moved it slightly further below
1.0 rather than toward it; its median lead in the evidenced cut is 4.6 weeks against 5.3
in the full. Nothing
here rescues it.

### The 69-row floor: 60 fixed, nine standing

Spec §7's third success criterion was that the sprint-1 known-error rows come out
`unresolved`. Re-running that criterion against the new labels:

```
known-wrong rows, by new label: {'unresolved': 60, 'slipped': 4, 'shipped': 9, 'dropped': 1}
```

**60 became `unresolved`. Nine are still `shipped`.** (The predicate matches 74 rows on the
current corpus checkout rather than sprint 1's 69; the count drifts with the
`cache/k8s/enhancements` HEAD it is evaluated against, which is part of why it was only
ever a bound.)

The nine, each with a `latest-milestone` one to three minors behind the row it claims:

| kep | status | latest-milestone | row | evidence |
|---|---|---|---|---|
| `1451-multi-scheduling-profiles` | implementable | v1.19 | stable @ v1.22 | closure |
| `1867-disable-accelerator-usage-metrics` | implementable | v1.20 | stable @ v1.22 | merge |
| `2891-simplified-config` | implementable | v1.23 | beta @ v1.24 | closure |
| `3000-artifact-distribution` | provisional | v1.24 | alpha @ v1.25 | closure |
| `3130-kms-observability` | replaced | v1.24 | stable @ v1.26 | closure |
| `3498-extending-stability` | implementable | v1.27 | stable @ v1.28 | closure |
| `4176-cpumanager-spread-cpus-preferred-policy` | implementable | v1.30 | beta @ v1.31 | merge |
| `4358-custom-resource-field-selectors` | implementable | v1.31 | stable @ v1.32 | closure |
| `2902-cpumanager-distribute-cpus-policy-option` | implementable | v1.33 | stable @ v1.35 | closure |

**These stand, and the reason is worth stating rather than burying.** The sprint-1
criterion was always a heuristic *bound*, not ground truth. What it actually asserts is
"the KEP never claims to have got there" — which is evidence of non-delivery only if the
author kept `latest-milestone` current. An unmaintained field sitting next to a closed
tracking issue reads better as *delivered with poor hygiene* than as *not delivered*, and
poor hygiene alongside real delivery is precisely the phenomenon this project exists to
measure. Two imperfect sources disagree on 9 of 1,255 rows; the disagreement is
informative and adjusting the rule to make it go away would have destroyed the
information.

Seven of the nine rest on closure, which is the weaker of the two evidence kinds — an
issue closes once and the window decides which milestone gets credit. If the nine are
wrong, that is where the error lives.

One row deserves a line of its own: **`3130-kms-observability` carries status `replaced`,
a drop status, and still labels `shipped`.** Rule 2's drop window closed before the status
changed, so rule 2 never saw it and precedence carried through to rule 5, which found
closure evidence. The label is what the rule says; the rule's window is the thing to argue
with.

### What this still does not fix

From spec §6, unchanged by anything above:

- **Coverage is capped by the source.** Only **306 of 644 KEPs** have any merged
  cross-referenced PR at all. A KEP whose implementation never referenced its tracking
  issue is invisible to the merge rule no matter how the window is tuned.
- **`beta` coverage is 18.8%**, the weakest of the three stages, so `beta` rows are
  disproportionately `unresolved` and disproportionately absent from the evidenced cut.
- **Closure's window is a heuristic.** An issue closes once, at the end of a KEP's life.
  Attributing that to a specific milestone uses a window bounded below by cycle start and
  above by release + 90 days; the upper bound is a judgement call. The lower bound is not
  optional — without it, 22 rows took closure that predated their cycle by up to sixteen
  months as evidence of delivery within it.
- **A merged PR proves code landed, not that the feature shipped.** Reverts, feature gates
  left off, and partial implementations are all invisible to it.

- **The ten-row manual audit has not been re-run.** Spec §7's fourth success criterion
  asks for it, and it is the only check here that is not self-referential — every other
  check in this section compares one derived artefact against another. It is outstanding.

`unresolved` at 481 rows is 38% of the corpus. That is the honest size of what this
instrument cannot see, and it is now visible in the output instead of being folded into
`shipped`.

### Status of sprint 1's P0 list

1. Reverse the labeling precedence — **done, this section.** `shipped` requires positive
   delivery evidence; rows with none are `unresolved`; both cuts are published from one
   run.
2. Widen `Signal` to `(item_id, stage)` — **done**, §1.
3. Land the tracking-issue API data — **done**, §2.

Spec §5's S8 `broken_trail` is deliberately not in this sprint. It needs point-in-time
tracking labels inside `snapshot()`, which is the only part of the design that touches the
core model, and it needs these evidence-backed labels in order to be measured without
circularity. It gets its own plan.
