# program-risk-backtest

**Can you tell which planned work is going to slip — early enough to do something about it — using only the artifacts teams already produce?**

This project answers that question with a measurement instead of an opinion. It reconstructs what the Kubernetes project's roadmap said on every date across nineteen release cycles, asks four candidate risk signals what they thought at each of those dates, and scores them against what actually happened afterwards. The fourth signal is the release team's own scope label, included as a control — because a signal that cannot beat the judgment an organisation already writes down is not worth building.

The answer, on 1,255 committed deliverables across six years:

**Silence predicts slippage about as well as the release team's own label does, and the two find different failures — together they flag 7% of committed work with 92% precision, eight weeks before the deadline.** Then, partway through the corpus, the project stopped applying that label. The conjunction disappeared with it. The activity signal kept working unchanged.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals that depend on hygiene — exactly when you most need something that does not.

Two of the four signals failed, and are reported as failures. **[`docs/findings.md`](docs/findings.md) is the full conclusion**, including what these numbers cannot support and the four errors this project made and corrected before arriving at them.

---

## The problem

Every program manager wants the same thing: to know a commitment is in trouble while there is still time to act, not at the deadline. The usual approaches are status meetings and self-reported RAG ratings — both lagging, both subject to the reporting bias that the work most likely to slip is the work least likely to say so.

The alternative is to infer risk from the exhaust of the work itself: who owns it, how recently it moved, whether it has slipped before. Those are cheap, objective, and available without asking anyone. But "plausible-sounding indicator" is not the same as "predictive," and the difference can only be settled by testing against history.

There is a harder question underneath it, and most studies of this kind skip it: does any of that beat simply asking the people running the release? That question decided this one, so the release team's own scope label is measured alongside the inferred signals rather than assumed away.

So: pick some signals, add the obvious baseline, replay real history, and find out.

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

**[`docs/findings.md`](docs/findings.md) is the conclusion.** What follows is the summary.

Four signals were tested against 1,255 committed deliverables across 19 release cycles. One works, one is backwards, one is null, and the fourth is the project's own status label included as a control. Results are published under two cuts — `evidenced` (only rows whose outcome can be verified) and `full` (all rows, unknowns counted as not-delivered) — because 23% of outcomes cannot be confirmed from the corpus. Compare the lift column across cuts and nothing else; the base rates differ.

**Evaluated at the enhancements freeze, evidenced cut** (n=965, base rate 0.393):

| signal | what it looks for | fires | precision | **lift** | 95% CI |
|---|---|---|---|---|---|
| `hollow_owner` | nobody has touched it in N weeks | 160 | 0.856 | **2.18** | 2.01 – 2.37 |
| `tracked/no` | the release team says it is out of scope | 116 | 0.767 | **1.95** | 1.75 – 2.17 |
| **both together** | | 72 | **0.917** | **2.33** | 2.12 – 2.57 |

**Silence is a real predictor, and it is the durable one.** `hollow_owner` is significant on both cuts and never falls below the base rate in any cycle.

**The project's own label is just as good — while it is maintained.** On the evidenced cut our signal is significantly ahead; on the full cut the difference vanishes. Neither dominates.

**Together they are much better than either.** They overlap on only 39% of firings and the conjunction beats both, significantly, on both cuts: 92% precision on 7% of the corpus, eight weeks before the deadline.

**And then the label was abandoned.** After v1.27 the release team stopped applying `tracked/no` by the freeze — from 4–20 firings per cycle to 1. The conjunction does not exist in any recent cycle. `hollow_owner` in the same period held at 0.846 precision and *rose* to lift 2.52.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals that depend on hygiene — exactly when you most need something that does not.

**Two signals did not work, reported because a study that only surfaces its successes is not a study.** `prior_slip` ("it slipped before") is indistinguishable from no effect under both cuts. `late_target` is *negatively* predictive with its whole interval below 1.0 — work committed close to the freeze slipped **less**, most plausibly because a team committing late commits with better information.

## What these numbers cannot support

The labeling rule requires positive evidence that code landed — a tracking issue closed in the milestone's window, or a `kubernetes/kubernetes` PR milestoned for that release merged. Rows with neither are `unresolved`: **290 rows, 23% of the corpus**, outcome unknown rather than failed. 105 of them carry a `kep.yaml` self-report claiming delivery, so the residual is work whose paper trail cannot be followed, not simply work that stalled.

Recall is low throughout — the best instrument here flags a sixth of committed work. Most slippage is caught by none of these signals. The freeze evaluation point was chosen after seeing results, so treat specific lift values as suggestive. And this is one corpus: Kubernetes has unusually strong process hygiene, which makes it the best case for this method rather than a typical one.

**No learned model was tested. That was a design decision, not an omission — see the next section.**

[`docs/findings.md`](docs/findings.md) states all of this in full, along with the four errors this project made and corrected — including a fetch bug that meant an earlier draft published conclusions drawn from 6% of the available data.

## Why there is no model

This project is often assumed to have been aiming at AI inference of risk from structured
inputs. Worth being exact about what was scoped, because the answer is more interesting
than "we ran out of time."

LLMs *were* in scope, for a different job. The spec defines `source = llm`, a confidence
field on LLM-sourced events, and an SHA-256-keyed LLM cache committed to the repo so
results reproduce. Their role was **extraction, not prediction**: read unstructured KEP
prose and emit typed `dependency_changed` events, so that deterministic signals could run
over a richer event stream. That was sprint 3, and it was never reached.

Prediction by model was ruled out in writing before any code existed:

> Not signals, by design: anything read from prose except dependencies. No sentiment, no
> "LLM thinks this is risky" — uncalibratable.

|  | role | status |
|---|---|---|
| **LLM as extractor** | "this README says KEP-1234 blocks this one" → a typed event with confidence | in scope, deferred, never built |
| **LLM as predictor** | "this KEP looks risky to me" → a score | excluded by design, as uncalibratable |

Running the backtest supplied the evidence for a call the spec had only asserted. **Every
conclusion in this README was wrong at least once**, and each error was caught by tracing a
claim to specific rows — 475 timelines truncated at exactly 100 entries, 22 closures
predating their own cycle, 195 merges attributed by date instead of by milestone. That
tracing is possible because a firing means one inspectable fact: *no commit touched this
directory between these two dates*. A model emits a score, and a wrong score has nothing to
trace. **And the labels could not support training anyway**: 379 positives over 1,255 rows,
a measured ~8.5% floor of known label error, 23% of outcomes unverifiable. A model fit
before those two label defects surfaced would have encoded them invisibly — and validated
against the same corrupted labels.

The version of this worth building is not a risk classifier. It is the extraction path:
use a model for what models are good at — turning prose into structure — and keep the
prediction step inspectable. That also attacks coverage, which is the actual weakness here.
[`docs/findings.md`](docs/findings.md#on-models-and-why-there-isnt-one) sets out the full
reasoning.

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

.venv/bin/pytest                   # 188 tests, incl. a conformance run on the real corpus
```

Requires Python 3.12+. Dependencies are `pyyaml`, `pandas`, `numpy`, `pytest` — nothing else.

Outputs land in [`out/k8s/`](out/k8s/): per-signal metrics and a by-team cut for each of the two cuts (`signals.csv` / `by_org.csv` are evidenced, `*_full.csv` are the full sample), plus `rows.csv` with the row-level detail and every row's label.

## Reading further

| document | what it covers |
|---|---|
| [`docs/findings.md`](docs/findings.md) | **The conclusions**, what they cannot support, and the four things this project got wrong before arriving at them |
| [`docs/sprint-1-notes.md`](docs/sprint-1-notes.md) | The first run in full: results, per-release histogram, and an extended section on what the numbers cannot support. Its manual audit validated the *sprint-1* labels, which this rule replaced |
| [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md) | The evidenced labeling rule, both cuts in full, and two corrections that invalidated earlier drafts of these numbers |
| [`adapters/k8s/LABELING.md`](adapters/k8s/LABELING.md) | The outcome rule, normative — the doc states it, the code implements it, and they are kept in agreement |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design spec and the amendments execution forced |

## Status

**Closed.** Sprint 1 built the pipeline and the first three signals. Sprint 2 replaced the fallthrough labeling rule with positive evidence of delivery, added `unresolved` as a first-class label, published both cuts, and built the S0 control that sprint 1 specified and skipped — which is what produced the conclusion above.

Three items on sprint 1's list are deliberately not done and are recorded as such in [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md) §4: real actors for the activity signal, a sensitivity grid over the a priori parameters, and a decision about right-censoring. [`docs/findings.md`](docs/findings.md) ends with what a continuation should tackle first — the extraction path described above, the five untested signals, and a second corpus.
