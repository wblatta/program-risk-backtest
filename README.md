# program-risk-backtest

**Can you tell which planned work is going to slip — early enough to do something about it — using only the artifacts teams already produce?**

This project answers that question with a measurement instead of an opinion. It reconstructs what the Kubernetes project's roadmap said on every date across nineteen release cycles, asks three candidate risk signals what they thought at each of those dates, and scores them against what actually happened afterwards.

The answer, on 1,255 committed deliverables: **one of the three signals works, one does not, and one is actively backwards.** Details below, including the one that failed.

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

Base rate: 30.2% of commitments were not delivered as planned. A signal is useful if it beats that. Confidence intervals are bootstrapped (n=1000).

| signal | what it looks for | fires on | precision | **lift** | 95% CI | median lead |
|---|---|---|---|---|---|---|
| `hollow_owner` | no activity from anyone in N weeks | 505 rows | 41.0% | **1.36** | 1.25 – 1.46 | 8.6 weeks |
| `prior_slip` | this item has been retargeted before | 482 rows | 33.0% | 1.09 | 0.997 – 1.21 | 7.3 weeks |
| `late_target` | committed close to the freeze | 772 rows | 24.7% | **0.82** | 0.75 – 0.88 | 5.3 weeks |

**`hollow_owner` works.** Silence is the strongest available predictor of a missed commitment — 36% more likely to slip than the base rate, with the confidence interval clear of 1.0, and it says so a median of **8.6 weeks before the deadline**. That is a full sprint and a half of warning, from a signal that requires nobody to fill in a status field.

**`prior_slip` does not.** Its confidence interval includes 1.0, on the full sample and on every subset tested. "It slipped before, so it will slip again" is intuitive and is not supported by this data.

**`late_target` is backwards.** Its entire confidence interval sits *below* 1.0: work committed close to the freeze slipped **less** often, not more. The most plausible reading is selection — a team that commits late commits with better information, and the ones that were going to fail had already failed by then. Whatever the mechanism, the prior was wrong, and the sign is the interesting part.

Reporting the negative and the backwards result is the point. A study that only surfaces the signal that worked is not a study.

## What these numbers cannot support

The labeling rule is v1, and its main weakness is stated plainly: **`shipped` currently means "not observed to slip," not "verified shipped."** It is the fallthrough case.

A ten-row manual audit came back 8 correct, 1 unverifiable, 1 wrong — and every error ran the same direction, toward false `shipped`. A measured floor of **69 of 811 `shipped` rows (8.5%)** can be shown wrong from the corpus itself. Correcting only those moves `hollow_owner` to 1.44 and `late_target` to 0.71, so the known error *understates* the signal that works and *overstates* the one that doesn't.

There is a compounding case worth naming: one abandoned enhancement produced one true positive and two false negatives, and `hollow_owner` was charged a false positive for correctly identifying that it had stopped. **The v1 labeling rule systematically penalises the one signal that works.** Fixing it is the current work — see [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md).

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

.venv/bin/pytest                   # 141 tests, incl. a conformance run on the real corpus
```

Requires Python 3.12+. Dependencies are `pyyaml`, `pandas`, `numpy`, `pytest` — nothing else.

Outputs land in [`out/k8s/`](out/k8s/): per-signal metrics, the full row-level detail, and a by-team cut.

## Reading further

| document | what it covers |
|---|---|
| [`docs/sprint-1-notes.md`](docs/sprint-1-notes.md) | The first run in full: results, per-release histogram, the manual audit, and an extended section on what the numbers cannot support |
| [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md) | Current work, including a contract fix that removed a subtle backwards-crediting bug |
| [`adapters/k8s/LABELING.md`](adapters/k8s/LABELING.md) | The outcome rule, normative — the doc states it, the code implements it, and they are kept in agreement |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design spec and the amendments execution forced |

## Status

Sprint 1 complete and merged: pipeline, three signals, first measured results. Sprint 2 in progress — replacing the fallthrough labeling rule with positive evidence of delivery, drawn from release-team tracking data.
