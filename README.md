# program-risk-backtest

**Can you tell which planned work is going to slip — early enough to do something about it — using only the artifacts teams already produce?**

This project answers that question with a measurement instead of an opinion. It reconstructs what the Kubernetes project's roadmap said on every date across nineteen release cycles, asks three candidate risk signals what they thought at each of those dates, and scores them against what actually happened afterwards.

The answer, on 1,255 committed deliverables: **one of the three signals works, one is actively backwards, and one depends on whether you can verify the outcome at all.** Details below, including the ones that failed.

---

## The problem

Every program manager wants the same thing: to know a commitment is in trouble while there is still time to act, not at the deadline. The usual approaches are status meetings and self-reported RAG ratings — both lagging, both subject to the reporting bias that the work most likely to slip is the work least likely to say so.

The alternative is to infer risk from the exhaust of the work itself: who owns it, how recently it moved, whether it has slipped before. Those are cheap, objective, and available without asking anyone. But "plausible-sounding indicator" is not the same as "predictive," and the difference can only be settled by testing against history.

So: pick some signals, replay real history, and find out.

## Why Kubernetes

The measurement needs a corpus where commitments and outcomes are both public and dated. Kubernetes is unusually good for this:

- Every enhancement (a "KEP") has a `kep.yaml` file declaring which release it targets, versioned in git — so **every change of intent has a timestamp**.
- Releases run on a fixed calendar with a published *enhancements freeze* (the commitment point) and *code freeze* (the delivery deadline).
- Nineteen usable release cycles, v1.19 through v1.37, spanning 2020 to 2026.

That gives 644 enhancements, 14,513 timestamped events, and 1,255 `(enhancement, stage, release)` commitments to score.

## What was built

A general pipeline, with Kubernetes as the first corpus plugged into it:

```
git repos ──► adapter ──► event stream ──► point-in-time snapshot ──► signals
                                │                                       │
                                └──────► outcome labels ────────────────► backtest
```

**Adapters** turn raw sources into a stream of timestamped events — a target was set, an owner changed, a status moved. The Kubernetes adapter reads three git repos, walking each file's history to recover when each fact became true.

**`snapshot(events, as_of)`** replays that stream up to a date and reconstructs the roadmap as it stood. This is the core of the whole thing.

**Signals** are pure functions over a snapshot. They see only what was knowable on that date and cannot reach the adapter or the outcome.

**The backtest** takes weekly snapshots across each release cycle, records the first date each signal fired for each commitment, and joins that to an outcome the signal could not have seen.

The corpus-specific parts live behind an adapter interface with a conformance suite that any new corpus must pass, so pointing this at a different organisation's data is a matter of writing one adapter — not rewriting the analysis.

## The one thing that had to be right

**A backtest that can see the future is worthless, and it fails silently** — every test still passes, the numbers just quietly become fiction.

Three guarantees, each enforced structurally and pinned by a test written to fail if it regressed:

1. `snapshot()` discards outcome events unconditionally, before the date filter. There is no code path by which any caller sees an outcome.
2. An outcome joins a row only when it postdates the window in which the signal was allowed to speak (`outcome.ts > freeze_date`).
3. Prior outcomes handed to a signal are sliced strictly at or before the current date.

Those tests place their fixtures at the *exact* boundary second and were each verified to fail when the comparison is flipped from `>` to `>=`. A boundary test that passes under both spellings pins nothing — a lesson this project learned the hard way, four separate times.

## Results

A row is only scored `shipped` when there is positive evidence the code landed — the tracking issue closed inside the milestone's window, or a `kubernetes/kubernetes` PR cross-referenced from it merged during the cycle. Rows with neither are labelled `unresolved`, meaning *unknown to this instrument*, not *failed*. That splits the corpus in two, so the results are published as two cuts.

The headline table is the **evidenced cut**: the 774 rows whose outcome is known — either delivery evidence says it landed, or a recorded retarget, drop, or exception says it did not. Base rate 49.0% — a signal is useful if it beats that. Confidence intervals are bootstrapped (n=1000).

**Evidenced cut** — 774 rows, base rate 0.490:

| signal | what it looks for | fires on | precision | **lift** | 95% CI | median lead |
|---|---|---|---|---|---|---|
| `hollow_owner` | no activity from anyone in N weeks | 304 rows | 68.1% | **1.39** | 1.30 – 1.49 | 8.4 weeks |
| `prior_slip` | this item has been retargeted before | 276 rows | 57.6% | **1.18** | 1.08 – 1.28 | 7.3 weeks |
| `late_target` | committed close to the freeze | 482 rows | 39.6% | **0.81** | 0.75 – 0.86 | 4.6 weeks |

**`hollow_owner` works.** Silence is the strongest available predictor of a missed commitment — 39% more likely to slip than the base rate, with the confidence interval clear of 1.0, and it says so a median of **8.4 weeks before the deadline**. That is a full sprint and a half of warning, from a signal that requires nobody to fill in a status field.

**`prior_slip` works here, and only here.** Its confidence interval clears 1.0 on the evidenced cut. On the full cut below it does not. See the paragraph after the second table — this is the single most interesting result in the study, and it is not a result about `prior_slip` so much as about what happens when you score a signal against outcomes you never verified.

**`late_target` is backwards.** Its entire confidence interval sits *below* 1.0, under both cuts: work committed close to the freeze slipped **less** often, not more. The most plausible reading is selection — a team that commits late commits with better information, and the ones that were going to fail had already failed by then. Whatever the mechanism, the prior was wrong, and the sign is the interesting part.

### The full cut, and why both are published

The other 481 rows have no delivery evidence. Discarding them would quietly assume they resemble the rows that do, so the same measurement is also run over all 1,255 rows with `unresolved` counted as non-positive — the closest thing to the pessimistic reading:

**Full cut** — 1,255 rows, base rate 0.302:

| signal | fires on | precision | **lift** | 95% CI | median lead |
|---|---|---|---|---|---|
| `hollow_owner` | 505 rows | 41.0% | **1.36** | 1.25 – 1.46 | 8.6 weeks |
| `prior_slip` | 482 rows | 33.0% | 1.09 | 0.997 – 1.21 | 7.3 weeks |
| `late_target` | 772 rows | 24.7% | **0.82** | 0.75 – 0.88 | 5.3 weeks |

**Compare the lift columns and nothing else.** The two cuts have very different base rates — 0.490 against 0.302 — because the 481 excluded rows were overwhelmingly shipped-side, so nearly half of what remains in the evidenced cut is a positive. Lift is normalised by the base rate and is comparable across cuts. **Precision is not.** `hollow_owner` reads 68.1% in one table and 41.0% in the other while behaving identically; what changed is the population it is scored against.

**And this is where `prior_slip` turns.** Its interval is [1.08, 1.28] on the evidenced cut and [0.997, 1.21] on the full one, which includes 1.0. Where the paper trail exists, "it slipped before" predicts; where it does not, the signal is indistinguishable from noise. Earlier runs of this project reported `prior_slip` as simply not significant, which is true of the full cut and false of the evidenced one. The narrow, honest statement: it clears 1.0 on rows with verified outcomes, fails on the full sample, and the two populations differ in a way that may itself be related to the outcome — the evidenced cut is not a random subsample, it is the subsample where somebody linked the work back to its tracking issue.

Reporting the negative and the backwards result is the point. A study that only surfaces the signal that worked is not a study.

## What these numbers cannot support

`unresolved` is 481 rows, **38% of the corpus** — the honest size of what this instrument cannot see. It is visible in the output rather than folded into `shipped`, which is what sprint 1's v1 rule did, but it is not the same thing as knowing those outcomes.

Evidence coverage is uneven and the unevenness is structural. Only **306 of 644** enhancements have any merged cross-referenced PR at all. A tracking issue closes once, at the end of an enhancement's life, so closure is evidence about its final stage and merges about its first: coverage runs `stable` 54.2%, `alpha` 47.9%, and `beta` just **18.8%**, so `beta` rows are disproportionately excluded from the evidenced cut and any per-stage reading has to say so. Closure's attribution window is a heuristic, and a merged PR proves code landed — not that the feature shipped, since reverts, disabled feature gates and partial implementations are all invisible to it.

The rule is also checked against its predecessor and does not fully agree with it. Of the rows sprint 1 could prove wrong from the corpus itself, 60 are now `unresolved` and **nine are still `shipped`** — enhancements whose own `latest-milestone` never claims to have reached the release, sitting next to positive delivery evidence — seven a closed tracking issue, two a merged PR. Those nine are reported rather than patched away: an unmaintained metadata field alongside real delivery evidence reads better as *delivered with poor hygiene* than as *not delivered*, and poor hygiene is the phenomenon this project set out to measure. The reasoning is in [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md).

## Findings about the data

Real corpora are messier than their schemas, and several of these silently corrupt results rather than failing loudly:

- **Enhancement IDs are not unique by directory.** Two directories declared the same number after a working-group move. Merging their event streams made a live enhancement look abandoned and fabricated a failure outcome — invisible to unit tests, wrong in the output.
- **`git log --follow` walks copy detections into unrelated files.** Following renames naively attributed one enhancement's history to four others and terminated at the project's template file, dating its "creation" to the template's birthday. The fix follows rename status and stops at copy.
- **A status of `removed` does not mean the work was dropped.** One enhancement shipped in v1.8 and v1.11; its status records the *feature's* later removal. Treating it as a drop would relabel a success as a failure.
- **A retracted target leaves a trace, and ignoring it manufactures successes.** Roughly fifty items withdrew a future commitment. Without an event for the retraction, the stale target persisted and the row was scored as delivered.
- **One data file was unparseable because of a zero-width space.** Recovering it and a second undocumented schema variant restored 40 records.
- **`implementable` contains the substring `implement`.** A status check that pattern-matched silently dropped 59 rows — the status means *ready to start*, the opposite of shipped.

Each of these was found by measuring against the real corpus rather than reasoning about the schema, and each is recorded in the spec with the evidence.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'

.venv/bin/python cli.py fetch      # clone the source repos (a few minutes)
.venv/bin/python cli.py build      # events -> SQLite (walks git history; minutes)
.venv/bin/python cli.py backtest   # -> out/k8s/*.csv (under a second)

.venv/bin/pytest                   # 168 tests, incl. a conformance run on the real corpus
```

Requires Python 3.12+. Dependencies are `pyyaml`, `pandas`, `numpy`, `pytest` — nothing else.

Outputs land in [`out/k8s/`](out/k8s/): per-signal metrics and a by-team cut for each of the two cuts (`signals.csv` / `by_org.csv` are evidenced, `*_full.csv` are the full sample), plus `rows.csv` with the row-level detail and every row's label.

## Reading further

| document | what it covers |
|---|---|
| [`docs/sprint-1-notes.md`](docs/sprint-1-notes.md) | The first run in full: results, per-release histogram, the manual audit, and an extended section on what the numbers cannot support |
| [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md) | The evidenced labeling rule, both cuts in full, why `prior_slip` changes verdict between them, and the nine known-error rows that survived |
| [`adapters/k8s/LABELING.md`](adapters/k8s/LABELING.md) | The outcome rule, normative — the doc states it, the code implements it, and they are kept in agreement |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design spec and the amendments execution forced |

## Status

Sprint 1 complete and merged: pipeline, three signals, first measured results. Sprint 2 complete: the fallthrough labeling rule is replaced with positive evidence of delivery drawn from release-team tracking issues and cross-referenced merges, `unresolved` is a first-class label, and results are published under both cuts. The figures above are the sprint-2 numbers.
