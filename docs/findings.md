# Findings

The project's conclusions. Written last, revised whenever the numbers moved, and revised
again in sprint 3 when four new signals and real actor data moved several of them.

Corpus: 644 Kubernetes enhancements, 68,768 timestamped events, 19 release cycles
(v1.19–v1.37, 2020–2026), 1,255 `(enhancement, stage, release)` commitments.

Every number here is produced by `cli.py backtest` and committed under
[`out/k8s/`](../out/k8s/). Two cuts (`evidenced` drops rows whose outcome cannot be
verified; `full` counts them as non-positive), two evaluation points (`first_fired` during
the cycle; `at_freeze` at the moment the commitment locks), and two censoring views are
published for every signal. **A claim that does not say which it uses is a defect.**

**Headline figures exclude the two most recent cycles.** v1.36 and v1.37 released 133 and
7 days before this was written, and their slip rates read 0.135 and 0.017 against a corpus
norm near 0.45. Those are not better cycles; they are unfinished ones. A slip is recorded
when work is retargeted *after* its freeze, which happens during the following cycle, so a
milestone needs a full subsequent cycle plus margin before its outcomes are observable.
Including them deflates the base rate, which **inflates every lift measured against it** —
a signal looks strongest exactly where the data is least complete. n=855 rather than 965.
Both views are published; the difference is quantified below.

---

## The question

Can you tell which planned work will slip, early enough to act, using only the artifacts
teams already produce — and does that beat asking the people running the release?

---

## The three hypotheses, tested

The spec ([§1](superpowers/specs/2026-08-26-program-risk-backtest-design.md)) committed to
three hypotheses before any code existed, and to reporting a verdict on each including the
failures. Here they are.

### H1 — "Hollow ownership predicts slips." Half right, and the wrong half is the one it named.

> *Every item has a nominal owner; items whose listed owners are inactive on the item slip
> more often.*

Silence predicts slippage, strongly and everywhere. But narrowing from *anyone* to *the
listed owners* makes the signal consistently and significantly **worse**:

| evidenced, uncensored (n=855, base 0.434) | fired | precision | lift | 95% CI |
|---|---|---|---|---|
| `item_silent` — nobody at all, at freeze | 68 | 0.912 | **2.101** | [1.910, 2.323] |
| `hollow_owner` — no listed owner, at freeze | 171 | 0.725 | 1.671 | [1.509, 1.834] |
| `item_silent`, first-fired | 121 | 0.868 | **2.000** | [1.840, 2.191] |
| `hollow_owner`, first-fired | 282 | 0.631 | 1.455 | [1.337, 1.575] |

The first-fired intervals do not overlap. The ordering holds on both cuts, at both
evaluation points, and at every value of N in the [sensitivity grid](../out/k8s/sensitivity.csv).

So the phenomenon is real and the proposed mechanism is not. What predicts is that *the
work* is untouched, not that *the owner* is absent. Owners delegate; the named author is
often not the person implementing. An item where the author is quiet but a contributor is
merging code is fine, and H1 as stated would flag it.

This was invisible until sprint 3. Git author emails do not map to GitHub handles, so
sprints 1 and 2 could only ask "has anyone touched this" — and published the answer under
the name `hollow_owner`. The tracking-issue timelines supplied 47,573 activity events from
2,147 named people, which is what made the stated hypothesis answerable at all.

### H2 — "A stale dependency is a leading indicator." Not supported, and the corpus cannot settle it.

> *Items depending on another item that is itself late or inactive slip more often, and the
> signal fires early enough to act on.*

| evidenced, at freeze, uncensored | fired | precision | lift | 95% CI |
|---|---|---|---|---|
| `dep_inactive` (S4b) | 56 | 0.411 | 0.947 | [0.677, 1.237] |
| `dep_ordering_conflict` (S4a) | 15 | 0.333 | 0.768 | [0.233, 1.394] |

Both intervals span 1.0. S4b's precision sits on the base rate. Nothing here supports H2 —
and nothing here refutes it either, because the test has almost no power.

**The reason is the interesting part.** Spec §14 left open whether KEP prose encodes
dependencies recoverably, "pattern or LLM". Measured over 617 READMEs: **109 (18%)
reference another KEP at all.** The most common match is the document's own title line, and
most of the remainder are related work — *"it also aligns with the extensions outlined in
KEP-365"*, *"closely related KEP-3329"*. Those are citations, not dependencies. The
tracking issues add 164 KEP-to-KEP cross-references, typed by construction as *a link*, with
no relation type. In total **143 of 644 items (22%) carry any edge at all.**

The pattern-or-LLM question is therefore not what limits this. A model would separate
"depends on" from "related to" better than a regex does — a real gain inside the 18% and no
way past it. **You cannot test a dependency hypothesis against a corpus that does not
record dependencies.**

### H3 — "Risk register ≠ status update." Supported, but the separation is mostly definitional.

> *Signals separate by measured lead time into those actionable before freeze (risk) and
> those that fire too late to change anything (status).*

They do separate. Median lead, first-fired, evidenced:

| signal | median lead | class |
|---|---|---|
| `process_tracked` | 8.29 wks | risk |
| `item_silent` | 8.21 wks | risk |
| `prior_slip` | 7.29 wks | risk |
| `late_target` | 5.29 wks | risk |
| **`gate_unassigned`** | **3.29 wks** | **status** |

One signal falls on the status side — and it is the second most predictive in the set
(lift 1.740 at freeze, uncensored). The most useful thing you can know arrives too late to use.

**But that split is largely an artifact of the signal's own definition.** `gate_unassigned`
fires only once the freeze is within `M` weeks, so its lead cannot exceed `M = 4` by
construction. The sensitivity grid settles it: at `M = 6` it reclassifies to `risk` and
still scores **1.694 [1.567, 1.837]**. The lead was a parameter choice, not a property of
the failure mode.

So H3 survives in a weaker and more useful form: signals do differ sharply in lead time,
but the difference tracks how each signal is defined rather than something intrinsic. That
is actionable — **a gate check run six weeks out is both early enough to act on and
materially predictive** — and it is a recommendation the a priori parameters hid.

---

## What predicts, all ten signals

Evidenced cut, uncensored, n=855, base rate 0.434, at the enhancements freeze. Full cut,
first-fired and the censored-inclusive views are all in [`out/k8s/`](../out/k8s/); **the
ordering is identical in every one of the eight.**

| signal | fired | precision | recall | lift | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `item_silent` | 68 | 0.912 | 0.167 | **2.101** | [1.910, 2.323] | strongest, lowest recall |
| `gate_unassigned` | 200 | 0.755 | 0.407 | **1.740** | [1.599, 1.904] | strong, best balance |
| `hollow_owner` | 171 | 0.725 | 0.334 | **1.671** | [1.509, 1.834] | strong |
| `process_tracked` (S0) | 331 | 0.637 | 0.569 | **1.469** | [1.362, 1.571] | the control |
| `org_overcommitted` | 621 | 0.459 | 0.768 | 1.058 | [1.008, 1.102] | marginal, fires on 73% |
| `prior_slip` | 330 | 0.455 | 0.404 | 1.048 | [0.949, 1.146] | null |
| `cross_org` | 389 | 0.450 | 0.472 | 1.037 | [0.953, 1.117] | null |
| `dep_inactive` | 56 | 0.411 | 0.062 | 0.947 | [0.677, 1.237] | null, underpowered |
| `late_target` | 532 | 0.342 | 0.491 | **0.788** | [0.725, 0.846] | **negative** |
| `dep_ordering_conflict` | 15 | 0.333 | 0.013 | 0.768 | [0.233, 1.394] | null, underpowered |

Four signals of ten carry real information. Four are indistinguishable from noise. One is
significantly negative. One pair is untestable on this corpus.

**`late_target` is the interesting failure.** Work committed close to the freeze slipped
*less*, with its entire interval below 1.0 on both cuts and at both evaluation points, and
at every value of K in the grid. The prior was confidently wrong. The most plausible
reading is selection: a team committing late commits with better information, and the work
that was going to fail had already failed by then.

---


## Signals in combination

The per-signal table answers "does this predict". The operational question is different:
*if I act only when two independent checks agree, how often am I right, and how much do I
stop seeing?* Evidenced, uncensored, first-fired, n=855, base 0.434:

| combination | fires | precision | recall | lift | 95% CI |
|---|---|---|---|---|---|
| **`gate_unassigned` AND `item_silent`** | 100 (11.7%) | **0.940** | 0.253 | **2.166** | [1.998, 2.367] |
| `gate_unassigned` AND `hollow_owner` | 146 (17.1%) | 0.877 | 0.345 | 2.020 | [1.861, 2.210] |
| `item_silent` AND `process_tracked` | 116 (13.6%) | 0.871 | 0.272 | 2.007 | [1.836, 2.194] |
| `gate_unassigned` AND `process_tracked` | 163 (19.1%) | 0.865 | 0.380 | 1.994 | [1.831, 2.171] |
| `item_silent` alone, for reference | 121 (14.2%) | 0.868 | 0.283 | 2.000 | [1.828, 2.185] |

**The best pair is significantly better than either parent**, tested by paired bootstrap on
the difference rather than by eyeballing overlapping intervals:

| | difference in lift | 95% CI |
|---|---|---|
| pair vs `item_silent` alone | +0.167 | [+0.064, +0.290] |
| pair vs `gate_unassigned` alone | +0.449 | [+0.304, +0.610] |
| pair vs the human control | +1.030 | [+0.858, +1.215] |

The two overlap on only 43% of their combined firings, which is why the conjunction has
anything to add: `item_silent` is mostly filtering `gate_unassigned`'s false positives with
an independent check. **94% precision on 12% of committed work, at the freeze.**

**And it misses 277 of 371 slips.** That is the trade, stated plainly: this is a triage
tool, not a safety net. If you can only look at a dozen items, these are the dozen. If you
need to catch most failures, nothing in this project does that.

**One row in the table is not a finding.** `item_silent AND hollow_owner` reports numbers
identical to `item_silent` alone, because silence-from-everyone is *necessarily* a subset
of no-listed-owner-activity. The analysis flags it as `item_silent ⊆ hollow_owner` rather
than publishing a duplicate as a result. It is a correctness check on both
implementations, and it passes.

**The human label adds nothing to the best pair.** Adding `process_tracked` moves 0.940 to
0.938 and loses three rows. It is not independent of the other two in the way they are
independent of each other.

## Three signals now beat the organisation's own judgment

`process_tracked` is the control — the release team's own `tracked/*` scope label, read at
the same moment on the same rows. The bar sprint 1 set was that *a signal which cannot beat
the project's own status field is not worth reporting*.

At the freeze, `item_silent` (2.101), `gate_unassigned` (1.740) and `hollow_owner` (1.671)
all clear `process_tracked` (1.469), with non-overlapping intervals in the first two cases.

**This reverses an earlier draft of this document**, which reported the human label as
comparable to the best available signal. That draft was written when only one activity
signal existed, it read anonymous git activity, and the comparison ran against a different
form of the label. Both sides of it have since changed.

## And the control decayed while the signals improved

Splitting the corpus at v1.27:

| signal | v1.19–27 (base 0.466) | v1.28–35 (base 0.402) |
|---|---|---|
| `item_silent` | 1.860 [1.67, 2.08] | **2.161** [1.88, 2.49] |
| `gate_unassigned` | 1.547 [1.40, 1.73] | **1.962** [1.71, 2.23] |
| `process_tracked` (S0) | 1.239 [1.14, 1.34] | **1.073** [1.00, 1.15] |

Both eras end at v1.35; the censored cycles are excluded from both. Including them would
have read 2.398 and 2.247 for the first two signals — the censoring inflates precisely the
era this section is about, which is why it is excluded here rather than only mentioned.

Every activity- and process-derived signal got *stronger*. The label-derived control got
weaker. The reason is visible in the raw firing counts: in v1.28 through v1.31 the release
team's `tracked/yes` label was applied to **no row at all** — `process_tracked` fires on
61/61, 65/65, 74/74 and 57/58 rows in those four cycles — before partially returning from
v1.32.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals that
> depend on hygiene — exactly when you most need something that does not.

---

## What this cannot support

- **Recall is low where precision is high.** The best instrument flags 17% of committed
  work. Most slippage is caught by nothing here. `gate_unassigned` is the better
  operational choice at 40% recall and 0.741 precision.
- **The freeze evaluation point was chosen after seeing results.** It is now published
  beside the designed first-fired metric rather than instead of it, and the ordering is
  the same under both — but the choice was made post hoc and the specific values should
  be read as suggestive.
- **The censoring cutoff is a judgment.** 180 days is about 1.5 release cycles, chosen
  because it is longer than the cycle in which a slip would surface and because the corpus
  agrees with it. A different cutoff moves the magnitudes. It does not move any direction:
  every signal keeps its sign and significance under both views.
- **290 rows (23%) remain `unresolved`** — outcome unknown to the instrument. 105 carry a
  `kep.yaml` self-report claiming delivery, so the residual is work whose paper trail
  cannot be followed, not work that stalled.
- **H2 is untested, not refuted.** 21 and 62 firings decide nothing.
- **One corpus, one organisation.** Kubernetes has unusually strong process hygiene and
  machine-readable artifacts, which makes it the best case for this method rather than a
  typical one. How unusual is now measured rather than asserted — see below.
- **`org_overcommitted` fires on 73% of rows.** Even where its interval clears 1.0 it is
  too indiscriminate to act on, and it is reported as null for that reason as much as for
  its interval.


## Why there is no second corpus

"One corpus, one organisation" is this project's largest limitation, and the obvious
answer is to run the pipeline somewhere else. Before writing a second adapter, 41
candidate GitHub projects were measured against what the pipeline actually needs
([`out/corpus_survey.csv`](../out/corpus_survey.csv), `tools/corpus_survey.py`).
`kubernetes/enhancements` is included as a reference row, so candidates are read against
the corpus known to work rather than against an absolute threshold.

The decisive property is **retargeting**. A `slipped` outcome exists only because work is
moved from one release to a later one and leaves a timestamped trace. Everything else
degrades; this disqualifies.

| | of 41 |
|---|---|
| show no retargeting at all — no positive class to predict | **8** |
| have no milestoned issues at all | 6 |
| have no team/area labels, so `cross_org` and `org_overcommitted` cannot run | 13 |
| have no scope-decision label, so **the S0 control cannot be reproduced** | 22 |
| score adequate on all four criteria | **4** |

And the four that pass are `kubernetes/enhancements` itself, `knative/serving`,
`etcd-io/etcd` and `argoproj/argo-cd` — **all three non-reference passes are
Kubernetes-ecosystem projects that adopted the KEP process.** The artifacts this method
needs, outside Kubernetes, exist mainly where someone copied Kubernetes.

### The largest candidate, and why it was still declined

`golang/go` carries **51,219 milestoned issues** — a hundred times the reference corpus —
with 79% milestone coverage and a 42% retarget rate, under governance genuinely unlike
Kubernetes': a proposal committee rather than SIGs, and no shared process ancestry. It is
the strongest generalisation test available.

It cannot reproduce the control. Go's release-process labels are far too rare to serve
(`early-in-cycle` 281 issues, `okay-after-beta1` 130, against 51k milestoned), and its
`Backlog` and `Unplanned` milestones — 10,304 issues, the obvious candidate — are
**circular**: in Go, "the team deprioritised this" and "the work slipped" are the same
event. In Kubernetes they are two different artifacts, which is what makes S0 a control at
all.

Without a control the result would be "silence predicts slippage in Go at some lift", with
magnitudes not comparable to these, and no answer to the question that makes the
Kubernetes finding worth reading: *does this beat what the organisation already knows?*

### What the survey does and does not establish

It establishes that **the inputs are rare**. It does **not** establish that the signals
would fail elsewhere — that question is untouched, and the honest position remains that
every result here is one organisation's.

But it converts the limitation from an apology into a measurement, and it says something
the second corpus would not have: Kubernetes' artifact discipline is unusual, and a method
built on it inherits that unusualness. A reader deciding whether to adopt any of this
should first check whether their own corpus retargets in a way anyone could observe.

## On models, and why there isn't one

This project is often assumed to have been aiming at AI inference of risk from structured
inputs. The spec drew the line explicitly, before any code existed:

> Not signals, by design: anything read from prose except dependencies. No sentiment, no
> "LLM thinks this is risky" — uncalibratable.

LLMs *were* in scope, for a different job. The spec defines `source = llm`, a confidence
field on LLM-sourced events, and an SHA-256-keyed cache committed so results reproduce.
The role was **extraction, not prediction**: read prose, emit typed dependency events with
a confidence, and let deterministic signals run over the richer stream.

| | role | status |
|---|---|---|
| **LLM as extractor** | "this README says KEP-1234 blocks this one" → a typed event with confidence | **built in sprint 3**, as `prose-cue-v1` |
| **LLM as predictor** | "this KEP looks risky to me" → a score | excluded by design, as uncalibratable |

Sprint 3 built the extraction path and measured its ceiling: **27 prose edges across 617
READMEs.** A model would beat those regexes at telling "depends on" from "related to". It
would not change that 82% of READMEs name no sibling at all. The extraction path was the
right thing to build and it is coverage-bound, not technique-bound.

The case against the *predictor* is now empirical rather than asserted. Every conclusion in
this document was wrong at least once, and each error was caught by tracing a claim to
specific rows — 475 timelines truncated at exactly 100 entries; 22 closures predating their
own cycle; 195 merges attributed by date instead of milestone; an id namespace mismatch
that would have made an owner-scoped signal fire on the entire corpus. Each was findable
because a firing means one inspectable fact. A score means nothing you can trace.

And the labels would not support training: 1,255 rows, 379 positives, ~8.5% measured floor
error, 23% unverifiable. A model fit before the two label defects surfaced would have
encoded them invisibly and validated against the same corrupted labels.

## What we got wrong along the way

Recorded because the corrections are more instructive than the result.

1. **The timeline fetch was truncated at page 1** — 475 of 644 issues; 6% of the data. It
   produced an `unresolved` bucket described as measuring process hygiene when it
   substantially measured our own fetch.
2. **Merge evidence was attributed by date rather than by the PR's milestone.** Kubernetes
   milestones its PRs; attribution should have been read, not inferred.
3. **`prior_slip` was published as crossing significance between cuts** — the centrepiece
   of one draft, an artifact of (1), and null in every view today.
4. **"The human label beats our signal" was published on an invalid comparison** — a
   freeze-point predictor against a first-fired lift. Both evaluation points are now
   computed by the committed pipeline, with an `eval` column, so the two cannot be mixed
   silently.
5. **`hollow_owner` did not test H1 for two sprints** and nothing in the code said so. It
   measured anonymous silence under a name that claimed ownership.
6. **The activity actor id nearly shipped wrong.** Owners are minted `k8s:@alice` from
   kep.yaml; the API returns `alice`. Emitting `k8s:alice` would have matched no owner,
   made every item read as hollow, and scored well for exactly the wrong reason.

Errors 1, 2 and 6 were found by going outside the corpus or by checking one path against
another. Nothing internal caught them: every internal check compares the corpus to itself.

## If someone continues this

- **A second corpus, knowing what it costs.** Measured, not guessed: of 41 candidates only
  three non-Kubernetes projects clear the bar, and all three copied the KEP process.
  `knative/serving` is the cleanest replication and proves the least; `golang/go` is the
  strongest test and cannot reproduce the control. Either is a real week of work for a
  claim that will not be numerically comparable to these results. Read
  [`out/corpus_survey.csv`](../out/corpus_survey.csv) before committing to it.
- **Run `gate_unassigned` at M=6.** The grid says it is both actionable and predictive
  there. This is the one finding here that is directly operational.
- **Chase recall, not precision.** Precision is adequate. Coverage is the weakness, in the
  signals and in the dependency graph alike.
- **Give the dependency graph a real source.** H2 needs a corpus that records typed
  dependency edges. Neither KEP prose nor GitHub cross-references carry a relation type,
  so on this platform H2 stays open — and a second GitHub corpus will not close it.
