# Findings

The project's conclusions. Written last, revised whenever the numbers moved, and revised
again in sprint 3 when four new signals and real actor data moved several of them.

Corpus: 644 Kubernetes enhancements, 68,768 timestamped events, 19 release cycles
(v1.19–v1.37, 2020–2026), 1,255 `(enhancement, stage, release)` commitments.

Every number here is produced by `cli.py backtest` and committed under
[`out/k8s/`](../out/k8s/). Two cuts (`evidenced` drops rows whose outcome cannot be
verified; `full` counts them as non-positive) and two evaluation points (`first_fired`
during the cycle; `at_freeze` at the moment the commitment locks) are published for every
signal. **A claim that does not say which cut and which evaluation point it uses is a
defect.**

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

| evidenced cut | fired | precision | lift | 95% CI |
|---|---|---|---|---|
| `item_silent` — nobody at all, at freeze | 71 | 0.887 | **2.259** | [2.020, 2.489] |
| `hollow_owner` — no listed owner, at freeze | 181 | 0.702 | 1.787 | [1.624, 1.955] |
| `item_silent`, first-fired | 126 | 0.841 | **2.142** | [1.940, 2.373] |
| `hollow_owner`, first-fired | 310 | 0.584 | 1.487 | [1.364, 1.606] |

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

| evidenced, at freeze | fired | precision | lift | 95% CI |
|---|---|---|---|---|
| `dep_inactive` (S4b) | 62 | 0.371 | 0.945 | [0.626, 1.264] |
| `dep_ordering_conflict` (S4a) | 21 | 0.238 | 0.606 | [0.171, 1.088] |

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
(lift 1.888 at freeze). The most useful thing you can know arrives too late to use.

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

Evidenced cut, n=965, base rate 0.393, at the enhancements freeze. Full cut and
first-fired in [`out/k8s/`](../out/k8s/); the ordering is identical in all four views.

| signal | fired | precision | recall | lift | 95% CI | verdict |
|---|---|---|---|---|---|---|
| `item_silent` | 71 | 0.887 | 0.166 | **2.259** | [2.020, 2.489] | strongest, lowest recall |
| `gate_unassigned` | 205 | 0.741 | 0.401 | **1.888** | [1.734, 2.064] | strong, best balance |
| `hollow_owner` | 181 | 0.702 | 0.335 | **1.787** | [1.624, 1.955] | strong |
| `process_tracked` (S0) | 344 | 0.622 | 0.565 | **1.584** | [1.477, 1.698] | the control |
| `prior_slip` | 371 | 0.418 | 0.409 | 1.064 | [0.957, 1.167] | null |
| `org_overcommitted` | 701 | 0.411 | 0.760 | 1.046 | [0.997, 1.096] | null |
| `cross_org` | 436 | 0.406 | 0.467 | 1.034 | [0.940, 1.117] | null |
| `dep_inactive` | 62 | 0.371 | 0.061 | 0.945 | [0.626, 1.264] | null, underpowered |
| `late_target` | 608 | 0.309 | 0.496 | **0.787** | [0.723, 0.849] | **negative** |
| `dep_ordering_conflict` | 21 | 0.238 | 0.013 | 0.606 | [0.171, 1.088] | null, underpowered |

Four signals of ten carry real information. Four are indistinguishable from noise. One is
significantly negative. One pair is untestable on this corpus.

**`late_target` is the interesting failure.** Work committed close to the freeze slipped
*less*, with its entire interval below 1.0 on both cuts and at both evaluation points, and
at every value of K in the grid. The prior was confidently wrong. The most plausible
reading is selection: a team committing late commits with better information, and the work
that was going to fail had already failed by then.

---

## Three signals now beat the organisation's own judgment

`process_tracked` is the control — the release team's own `tracked/*` scope label, read at
the same moment on the same rows. The bar sprint 1 set was that *a signal which cannot beat
the project's own status field is not worth reporting*.

At the freeze, `item_silent` (2.259), `gate_unassigned` (1.888) and `hollow_owner` (1.787)
all clear `process_tracked` (1.584), with non-overlapping intervals in the first two cases.

**This reverses an earlier draft of this document**, which reported the human label as
comparable to the best available signal. That draft was written when only one activity
signal existed, it read anonymous git activity, and the comparison ran against a different
form of the label. Both sides of it have since changed.

## And the control decayed while the signals improved

Splitting the corpus at v1.27:

| signal | v1.19–27 (base 0.466) | v1.28–37 (base 0.335) |
|---|---|---|
| `item_silent` | 1.860 [1.67, 2.08] | **2.398** [2.05, 2.78] |
| `gate_unassigned` | 1.547 [1.40, 1.72] | **2.247** [1.96, 2.57] |
| `hollow_owner` | 1.340 [1.22, 1.47] | **1.573** [1.35, 1.81] |
| `process_tracked` (S0) | 1.239 [1.15, 1.34] | **1.161** [1.08, 1.25] |

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
- **290 rows (23%) remain `unresolved`** — outcome unknown to the instrument. 105 carry a
  `kep.yaml` self-report claiming delivery, so the residual is work whose paper trail
  cannot be followed, not work that stalled.
- **H2 is untested, not refuted.** 21 and 62 firings decide nothing.
- **One corpus, one organisation.** Kubernetes has unusually strong process hygiene and
  machine-readable artifacts, which makes it the best case for this method rather than a
  typical one. The second corpus is [blocked on credentials](adapters/gitlab.md), not on
  design.
- **`org_overcommitted` fires on 73% of rows.** Even where its interval clears 1.0 it is
  too indiscriminate to act on, and it is reported as null for that reason as much as for
  its interval.

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

- **A second corpus.** The single highest-value next step, and the one thing that separates
  "this works" from "this works on Kubernetes." Blocked on a GitLab API token, not on
  design — see [`docs/adapters/gitlab.md`](adapters/gitlab.md).
- **Run `gate_unassigned` at M=6.** The grid says it is both actionable and predictive
  there. This is the one finding here that is directly operational.
- **Chase recall, not precision.** Precision is adequate. Coverage is the weakness, in the
  signals and in the dependency graph alike.
- **Give the dependency graph a real source.** H2 deserves a corpus that records
  dependencies — GitLab's issue-links API types them, which is exactly what KEP prose
  does not.
