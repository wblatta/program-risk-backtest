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

> **Superseded figures below.** The percentages in this section were measured on a
> timeline fetch truncated at page 1 (see §3). The `tracked/yes` conclusion holds — it is
> a separation failure, and completing the data does not rescue a label that is not
> removed when work fails — but the closure and merge percentages here are stale. §3
> carries the current ones.

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

`shipped` no longer means "not observed to slip". It requires positive evidence the code
landed: the tracking issue closed within the milestone's window, or a
`kubernetes/kubernetes` PR **milestoned for that release** was merged. Rows with neither
are `unresolved` — outcome unknown to this instrument, which is not the same as failed.

**This section was published twice with wrong numbers before this one.** Both errors are
recorded below rather than quietly overwritten, because both are instructive and neither
was caught by any test.

### Two corrections

**The timeline fetch was truncated at page 1.** The GitHub client requested
`timeline?per_page=100` and never followed `Link: rel="next"`. 475 of 644 cached
timelines held exactly 100 entries and none held more. Timelines run oldest-first, so
what was lost was always the most recent history, and long-lived KEPs suffered worst —
page 1 covered a median of 35.8% of an issue's life, as little as 1.8% for `kep-4216`
(20 days of 1,082). Completing the fetch took the corpus from 7,322 timeline events to
131,243: **we had been reading 6% of the data.**

That invalidated the previous publication in a specific and embarrassing way. The
`unresolved` bucket was described — here, in `LABELING.md`, in the spec and in the
README — as measuring the project's process hygiene: "nobody linked the implementation
back to the tracking issue." For a large share of it, someone had; we had stopped
reading. And the reported stage gap (`beta` 18.8% against `stable` 54.2%) was explained
as structural, closure being evidence about final stages and merges about first ones.
That story was fitted to an artifact: page-1 truncation hides late history, so it
penalises exactly the stages that arrive late.

**Merge attribution was by date, not by milestone.** The rule asked whether a
cross-referenced PR merged between a cycle's start and its release. That was never
attribution — a KEP's PRs land continuously across a multi-year life, so a cycle-length
window samples a slice of a stream. Measured: 195 `unresolved` rows had merged PRs the
window missed entirely, the nearest landing a median of 86 days before or 218 days
after. In the ten-row audit, **zero** sampled rows had a merged PR in window despite
several KEPs carrying between one and seven.

Kubernetes milestones its PRs, and the cross-reference payload carries it — 96% of the
1,898 merged cross-references do. Attribution is now read rather than inferred.

### Results

| | shipped | unresolved | slipped | exception_granted | dropped |
|---|---|---|---|---|---|
| v1 (fallthrough) | 811 | — | 370 | 65 | 9 |
| truncated + date window | 330 | 481 | 370 | 65 | 9 |
| **complete + milestone attribution** | **521** | **290** | 370 | 65 | 9 |

`slipped`, `exception_granted` and `dropped` never move: evidence only affects the
rule-5/6 branch, which is the check that precedence was never disturbed.

| signal | evidenced (965 rows, base 0.393) | full (1,255 rows, base 0.302) |
|---|---|---|
| `hollow_owner` | **1.436** [1.327, 1.546] | 1.357 [1.253, 1.463] |
| `prior_slip` | 1.080 [0.984, 1.169] | 1.092 [0.997, 1.206] |
| `late_target` | 0.796 [0.731, 0.855] | 0.819 [0.748, 0.883] |

**Compare only the lift column across cuts.** The cuts have different denominators
(965 against 1,255) and different base rates (0.393 against 0.302), so precision is not
comparable between them. Recall is — dropping `unresolved` removes only non-positives, so
the positive set is identical and recall is invariant to the cut by construction.

**The full cut is bit-identical to sprint 1's result, and always will be.** It counts all
1,255 rows, and `shipped` and `unresolved` are both non-positive, so evidence only moves
rows between two buckets the full cut cannot distinguish. That makes the comparison
sharper than "two readings": the full cut *is* the sprint-1 baseline, and the evidenced
cut is what you get by restricting to rows whose outcome can be verified.

### What the comparison shows

**`hollow_owner` is the only signal that works, and it works better where the trail
exists** — 1.436 against 1.357, both CIs clear of 1.0. Silence is a real predictor of a
missed commitment, and it is a stronger one among work whose delivery can be confirmed.

**`prior_slip` is not distinguishable from no effect under either cut.** [0.984, 1.169]
and [0.997, 1.206] both include 1.0.

A previous version of this section reported that `prior_slip` crossed the significance
boundary between cuts — significant when evidence-backed, not otherwise — and made that
the centrepiece finding. **It was an artifact of the truncated fetch.** With complete
data the crossing disappears. It was the most interesting thing in that draft and it was
not real, which is the strongest argument available for the audit that found it.

**`late_target` remains negatively predictive under both cuts.** Committing close to the
freeze is associated with *less* slipping, not more. Unchanged across every revision.

### The ten-row manual audit

Spec §7 criterion 4 required re-running the manual audit against the new labels. No task
in the plan did, and it is the only non-self-referential check available — every other
verification compares the corpus against itself, so a hole *in* the corpus is invisible
to all of them. It was run after the final review blocked on exactly that.

It found the merge-attribution defect on its first execution: ten rows sampled from
`unresolved` (seed 0), zero with a merged PR in window, four with `kep.yaml` self-report
claiming `status: implemented` at exactly the row's milestone.

### What this still does not fix

- **290 rows remain `unresolved`, and 105 of them (36%) have a `kep.yaml` self-report
  claiming delivery at exactly that milestone.** Those are implementations never
  cross-referenced from the tracking issue, or PRs never milestoned. The instrument
  cannot see them, and the residual is not explained.
- **Evidence discriminates less well than the first draft suggested.** Coverage of
  `slipped` rows rose from 7.0% to 20.5% once the data was complete — the false-positive
  rate roughly tripled.
- **Closure attribution is coarse.** An issue closes once; tying that to a milestone uses
  a window bounded below by cycle start and above by release + 90 days. The upper bound
  is a heuristic.
- **A merged PR proves code milestoned for a release landed, not that the feature
  shipped.** Reverts, feature gates left off and partial implementations are invisible.
- **`3130-kms-observability` carries status `replaced` — a drop status — yet labels
  `shipped`**, because its status change fell outside the drop window. That is a
  rule-window defect wearing an evidence label.

### Coverage

Of the rows v1 called `shipped`, 64.2% (521/811) now have evidence; of those it called
`slipped`, 20.5% (76/370). By stage: `alpha` 59.5% (153/257), `beta` 59.4% (155/261),
`stable` 72.9% (207/284). Alpha and beta are within a point of each other — the stage gap
reported in the previous draft does not exist.

### Status of sprint 1's P0 list

1. Reverse the labeling precedence — **done**, this section.
2. Widen `Signal` to `(item_id, stage)` — **done**, §1.
3. Land the tracking-issue API data — **done**, §2, and completed here.

---

## 4. S0, the control — and the project's conclusion

Sprint 1 listed S0 `process_tracked` as a P0 and set the bar it exists to enforce: *"a
signal that cannot beat the project's own status field is not worth reporting."* It was
never built. Building it changed the conclusion twice before it settled.

Making it honest required tracking labels inside `snapshot()` — a `LABEL_CHANGED` event
kind, a `tracking-issue` source, and `ItemState.labels` — so the signal reads the release
team's view *during* the cycle. Reading today's labels would have been a leak: they are
the team's final word, not their view at the time.

**The full result is in [`findings.md`](findings.md).** In short: `hollow_owner` and the
human `tracked/no` label are comparably good, overlap on only 39% of firings, and are
significantly better in conjunction (92% precision on 7% of the corpus) than either
alone. Then the label was abandoned after v1.27 — 4–20 firings per cycle down to 1 —
taking the conjunction with it, while `hollow_owner` held at 0.846 precision and rose to
lift 2.52 in exactly that period.

Two corrections were made in the course of getting there, both recorded in `findings.md`:
S0 was first reported as beating our signal, on an invalid comparison between a
freeze-point predictor and a first-fired lift; and the "our signal wins" claim that
replaced it turned out to be cut-dependent, holding on the evidenced cut and vanishing on
the full one.

### Status of sprint 1's P0 list — closed

1. Reverse the labeling precedence — **done**, §3.
2. Widen `Signal` to `(item_id, stage)` — **done**, §1.
3. Land the tracking-issue API data — **done**, §2, completed in §3.
4. Give `activity` real actors — **not done.** `hollow_owner` still tests silence from
   everyone rather than from the listed owners, which is what H1 actually claims.
5. Re-run the manual audit — **done**, §3. It found a real defect on first execution.
6. Sensitivity grid over N, K, L — **not done.** The parameters remain as specified a
   priori and were never tuned, which is the honest position, but their sensitivity is
   unmeasured.
7. Decide about censoring — **partially.** The cut is reported; v1.36/v1.37 remain in the
   headline figures.

The project closes here. What a continuation should tackle is listed at the end of
`findings.md`.
