# program-risk-backtest

**Can you tell which planned work is going to slip — early enough to do something about it — using only the artifacts teams already produce?**

This project answers that question with a measurement instead of an opinion. It reconstructs what the Kubernetes project's roadmap said on every date across nineteen release cycles, asks four candidate risk signals what they thought at each of those dates, and scores them against what actually happened afterwards. The fourth signal is the release team's own scope label, included as a control — because a signal that cannot beat the judgment an organisation already writes down is not worth building.

The answer, on 1,255 committed deliverables across six years:

**An enhancement nobody has touched in eight weeks slips 2.3x more often than the base rate — and three signals now beat the release team's own scope label at the moment the commitment locks.** The best of them flags 17% of committed work at 89% precision. A second, checking whether the required approval gate has anyone attached to it, reaches 40% recall at 74% precision.

Then the release team's tracking label went unapplied for four consecutive cycles. The signals that read what people *did* got stronger through that period. The one that read what people *recorded* got weaker.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals that depend on hygiene — exactly when you most need something that does not.

Ten signals were tested. Four carry real information, four are indistinguishable from noise, one is significantly *negative*, and one pair could not be tested at all — each reported. **[`docs/findings.md`](docs/findings.md) is the full conclusion**, including verdicts on all three hypotheses and the six things this project got wrong before arriving at them.

## The three hypotheses, tested

The spec committed to three hypotheses before any code existed, and to reporting a verdict on each — *"including the one that fails."* All three now have one.

| | hypothesis | verdict |
|---|---|---|
| **H1** | items whose **listed owners** are inactive slip more | **Half right, wrong mechanism.** Silence predicts strongly (lift 2.259). Narrowing to the *listed owners* makes it significantly worse (1.787). What predicts is that the work is untouched, not that the owner is absent — owners delegate, and the named author is often not the person implementing. |
| **H2** | a stale dependency is a leading indicator | **Untestable on this corpus.** Both dependency signals are null on 21 and 62 firings. Only 18% of KEP READMEs reference a sibling at all, and those references carry no relation type. You cannot test a dependency hypothesis against a source that does not record dependencies. |
| **H3** | signals separate by lead time into actionable vs too-late | **Supported, but mostly definitional.** They do separate, and the second-best signal lands on the too-late side. But its lead is capped by its own window parameter: widen that window from 4 weeks to 6 and it becomes actionable *and* stays predictive (lift 1.694). The lead was a parameter choice, not a property of the failure. |

H1's verdict was invisible for two sprints. Git author emails do not map to GitHub handles, so the signal named `hollow_owner` was in fact measuring anonymous silence — the tracking-issue timelines, and 47,573 activity events from 2,147 named people, are what made the stated hypothesis answerable at all.

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

**The backtest** takes weekly snapshots across each release cycle, records both the first date each signal fired and whether it is still firing at the freeze, and joins that to an outcome the signal could not have seen. A sensitivity grid re-runs the whole thing across the a priori parameters so the published choice can be checked rather than trusted.

**`register`** runs every signal on today's snapshot for a live cycle and splits the firings into *risk* (early enough to act on) and *status* (fires too late), each annotated with the precision it actually achieved in the backtest. An MCP wrapper exposes the same queries as read-only tools.

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

Ten signals were tested against 1,255 committed deliverables across 19 release cycles. Results are published under two cuts — `evidenced` (only rows whose outcome can be verified) and `full` (all rows, unknowns counted as not-delivered), because 23% of outcomes cannot be confirmed — and at two evaluation points: `first_fired` during the cycle, and `at_freeze` when the commitment locks. Compare the lift column within a cut and evaluation point, never across; the base rates differ and so do the questions.

**At the enhancements freeze, evidenced cut** (n=965, base rate 0.393):

| signal | what it looks for | fires | precision | recall | **lift** | 95% CI |
|---|---|---|---|---|---|---|
| `item_silent` | nobody has touched it in 8 weeks | 71 | 0.887 | 0.166 | **2.259** | 2.02 – 2.49 |
| `gate_unassigned` | the required approval gate has no holder | 205 | 0.741 | 0.401 | **1.888** | 1.73 – 2.06 |
| `hollow_owner` | no *listed owner* has touched it | 181 | 0.702 | 0.335 | **1.787** | 1.62 – 1.96 |
| `process_tracked` | **the control** — the team's own scope label | 344 | 0.622 | 0.565 | **1.584** | 1.48 – 1.70 |
| `prior_slip` | it has been retargeted before | 371 | 0.418 | 0.409 | 1.064 | 0.96 – 1.17 |
| `org_overcommitted` | the org committed past its best-ever cycle | 701 | 0.411 | 0.760 | 1.046 | 1.00 – 1.10 |
| `cross_org` | more than one org is involved | 436 | 0.406 | 0.467 | 1.034 | 0.94 – 1.12 |
| `dep_inactive` | something it depends on has gone quiet | 62 | 0.371 | 0.061 | 0.945 | 0.63 – 1.26 |
| `late_target` | committed close to the freeze | 608 | 0.309 | 0.496 | **0.787** | 0.72 – 0.85 |
| `dep_ordering_conflict` | a dependency lands no earlier than this | 21 | 0.238 | 0.013 | 0.606 | 0.17 – 1.09 |

The ordering is identical across both cuts and both evaluation points.

**Silence is the strongest predictor, and it beats the organisation's own judgment.** Three signals clear the `process_tracked` control, the bar sprint 1 set: *a signal that cannot beat the project's own status field is not worth reporting.* An earlier draft of this README reported the human label as comparable to the best signal; that was measured before real actor data existed and against a different form of the label, and it no longer holds.

**`gate_unassigned` is the one you would actually deploy.** `item_silent` is more precise but flags a sixth of the work; the gate check reaches 40% recall at 74% precision, and the [sensitivity grid](out/k8s/sensitivity.csv) shows that running it six weeks out instead of four keeps it predictive (lift 1.694) while making it early enough to act on.

**And then the label was abandoned.** In v1.28 through v1.31 the release team applied `tracked/yes` to no row at all, before partially resuming. Across that break every activity-derived signal got *stronger* — `item_silent` from lift 1.860 to 2.398, `gate_unassigned` from 1.547 to 2.247 — while the label-derived control declined from 1.239 to 1.161.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals that depend on hygiene — exactly when you most need something that does not.

**Half the signals did not work, reported because a study that only surfaces its successes is not a study.** `prior_slip`, `cross_org` and `org_overcommitted` are indistinguishable from noise. Both dependency signals are null on too few firings to decide anything. And `late_target` is *negatively* predictive with its whole interval below 1.0 at every parameter value tested — work committed close to the freeze slipped **less**, most plausibly because a team committing late commits with better information.

## What these numbers cannot support

The labeling rule requires positive evidence that code landed — a tracking issue closed in the milestone's window, or a `kubernetes/kubernetes` PR milestoned for that release merged. Rows with neither are `unresolved`: **290 rows, 23% of the corpus**, outcome unknown rather than failed. 105 of them carry a `kep.yaml` self-report claiming delivery, so the residual is work whose paper trail cannot be followed, not simply work that stalled.

Recall is low throughout — the best instrument here flags a sixth of committed work. Most slippage is caught by none of these signals. The freeze evaluation point was chosen after seeing results, so treat specific lift values as suggestive. And this is one corpus: Kubernetes has unusually strong process hygiene, which makes it the best case for this method rather than a typical one.

**No learned model was tested. That was a design decision, not an omission — see the next section.**

[`docs/findings.md`](docs/findings.md) states all of this in full, along with the six errors this project made and corrected — including a fetch bug that meant an earlier draft published conclusions drawn from 6% of the available data.

## Why there is no model

This project is often assumed to have been aiming at AI inference of risk from structured
inputs. Worth being exact about what was scoped, because the answer is more interesting
than "we ran out of time."

LLMs *were* in scope, for a different job. The spec defines `source = llm`, a confidence
field on LLM-sourced events, and an SHA-256-keyed LLM cache committed to the repo so
results reproduce. Their role was **extraction, not prediction**: read unstructured KEP
prose and emit typed `dependency_changed` events, so that deterministic signals could run
over a richer event stream. **Sprint 3 built it**, and measured its ceiling.

The extraction path is no longer hypothetical: it found **27 dependency edges across 617
READMEs**, because only 18% of them reference a sibling KEP at all and most of those are
citations rather than dependencies. A model would separate "depends on" from "related to"
better than the regexes do — a real gain inside that 18%, and no way past it. The path was
worth building and it is coverage-bound, not technique-bound.

Prediction by model was ruled out in writing before any code existed:

> Not signals, by design: anything read from prose except dependencies. No sentiment, no
> "LLM thinks this is risky" — uncalibratable.

|  | role | status |
|---|---|---|
| **LLM as extractor** | "this README says KEP-1234 blocks this one" → a typed event with confidence | **built**, as `prose-cue-v1` — 27 edges across 617 READMEs |
| **LLM as predictor** | "this KEP looks risky to me" → a score | excluded by design, as uncalibratable |

Running the backtest supplied the evidence for a call the spec had only asserted. **Every
conclusion in this README was wrong at least once**, and each error was caught by tracing a
claim to specific rows — 475 timelines truncated at exactly 100 entries, 22 closures
predating their own cycle, 195 merges attributed by date instead of by milestone, an id
namespace mismatch that would have made an owner-scoped signal fire on the entire corpus. That
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
.venv/bin/python cli.py sensitivity # -> the a priori parameter grid
.venv/bin/python cli.py register --milestone k8s:v1.34   # live view for a cycle

.venv/bin/pytest                   # 283 tests, incl. a conformance run on the real corpus
```

Requires Python 3.12+. Dependencies are `pyyaml`, `pandas`, `numpy`, `pytest` — nothing else.

Outputs land in [`out/k8s/`](out/k8s/). For each of the two cuts: per-signal metrics at both evaluation points (`signals.csv`, `signals_at_freeze.csv`, and `*_full*` for the full sample), plus by-org and by-stage breakdowns. `rows.csv` carries row-level detail and every row's label; `sensitivity.csv` carries the a priori parameter grid.

## Reading further

| document | what it covers |
|---|---|
| [`docs/findings.md`](docs/findings.md) | **The conclusions**, what they cannot support, and the four things this project got wrong before arriving at them |
| [`docs/sprint-1-notes.md`](docs/sprint-1-notes.md) | The first run in full: results, per-release histogram, and an extended section on what the numbers cannot support. Its manual audit validated the *sprint-1* labels, which this rule replaced |
| [`docs/sprint-2-notes.md`](docs/sprint-2-notes.md) | The evidenced labeling rule, both cuts in full, and two corrections that invalidated earlier drafts of these numbers |
| [`adapters/k8s/LABELING.md`](adapters/k8s/LABELING.md) | The outcome rule, normative — the doc states it, the code implements it, and they are kept in agreement |
| [`out/k8s/sensitivity.csv`](out/k8s/sensitivity.csv) | Every conclusion re-run across the a priori parameters — the check that we did not tune toward our own result |
| [`docs/adapters/gitlab.md`](docs/adapters/gitlab.md) | The second corpus: full mapping, and the credential blocker that stopped it |
| [`docs/superpowers/specs/`](docs/superpowers/specs/) | Design spec and the amendments execution forced |

## Status

Sprints 0–3 complete. Sprint 1 built the pipeline and the first three signals. Sprint 2 replaced the fallthrough labeling rule with positive evidence of delivery and added the S0 control. **Sprint 3** built the four remaining spec'd signals (S2, S3, S4a, S4b, S6), gave `activity` real actors so H1 could be tested as stated, added the dependency extraction that answers spec §14's open question, published the sensitivity grid and the `register` live view, and produced verdicts on all three hypotheses.

All ten signals in spec §7 are built. All six conformance checks pass, on 283 tests.

**Sprint 4 — the GitLab adapter — is blocked on a credential, not on design.** GitLab requires authentication for `resource_milestone_events` on every public project, and that endpoint is the timestamped history this project's entire leakage boundary depends on. Without it every `target_set` would carry a fabricated timestamp and the pipeline would emit numbers that are wrong in a way no internal check could catch. [`docs/adapters/gitlab.md`](docs/adapters/gitlab.md) records the full mapping, the measured endpoint statuses, and what unblocks it: a token with `read_api` scope.

A second corpus remains the highest-value next step — and the one that could settle H2, since GitLab's issue-links API types dependencies explicitly, which is exactly what KEP prose does not.
