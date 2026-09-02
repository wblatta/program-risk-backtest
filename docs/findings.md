# Findings

The project's conclusions, after three revisions that each overturned the previous one.
Written last, when the numbers stopped moving.

Corpus: 644 Kubernetes enhancements, 21,195 timestamped events, 19 release cycles
(v1.19–v1.37, 2020–2026), 1,255 `(enhancement, stage, release)` commitments.

---

## The question

Can you tell which planned work will slip, early enough to act, using only the artifacts
teams already produce — and does that beat simply asking the people running the release?

The second half is the part most such studies skip. It is also the part that decided
this one.

---

## 1. Silence predicts slippage, and it is the durable signal

`hollow_owner` — no activity from anyone on the enhancement for N weeks — evaluated at
the enhancements freeze:

| cut | fires | precision | lift | 95% CI |
|---|---|---|---|---|
| evidenced (n=965, base 0.393) | 160 (17%) | 0.856 | **2.180** | [2.008, 2.373] |
| full (n=1255, base 0.302) | 223 (18%) | 0.614 | **2.034** | [1.835, 2.253] |

Significant on both cuts. Stable across every milestone with enough firings to measure:
precision 0.73–1.00, **never below the base rate in any cycle**.

It is a high-precision, low-recall instrument. It flags about a sixth of committed work
and is right most of the time about what it flags. It does not find everything that
slips, and it is not a general-purpose predictor.

## 2. The project's own label is just as good — while it is maintained

The release team applies `tracked/no` when an enhancement is not in scope for a release.
Read at the same moment, on the same population:

| predictor at enhancements freeze | fires | precision | lift |
|---|---|---|---|
| `tracked/no` (human label) | 116 | 0.767 | 1.954 |
| `hollow_owner` (ours) | 160 | 0.856 | 2.180 |

On the evidenced cut our signal is significantly ahead (difference +0.223, CI [+0.030,
+0.440]). **On the full cut the difference vanishes** (−0.023, CI [−0.287, +0.230]).
Neither dominates. Anyone claiming inference beats human judgment here, or the reverse,
is reading one cut and ignoring the other.

## 3. They find different failures, and the pair is much better than either

| fires | rows | precision |
|---|---|---|
| **both** | 72 | **0.917** |
| `hollow_owner` only | 88 | 0.807 |
| `tracked/no` only | 44 | 0.523 |

They overlap on only 39% of firings. The conjunction beats **both** single signals
significantly, on **both** cuts:

| cut | conjunction | vs `hollow_owner` | vs `tracked/no` |
|---|---|---|---|
| evidenced | 2.334 [2.116, 2.568] | +0.158 [+0.005, +0.314] | +0.385 [+0.216, +0.593] |
| full | 2.541 [2.228, 2.900] | +0.508 [+0.254, +0.765] | +0.488 [+0.261, +0.736] |

Note the conjunction is *stronger* on the full cut, the opposite direction from a
selection artifact. Fire on both and you get 92% precision on 7% of the corpus, eight
weeks before the deadline.

## 4. The finding that reframes the rest: the label was abandoned

`tracked/no` firings at the enhancements freeze, per cycle:

```
v1.19–v1.27   4 – 20 per cycle      the label is applied by the freeze
v1.28–v1.37   1 –  4 per cycle      it is not
```

The practice stopped after v1.27. The conjunction from §3 therefore **does not exist**
in any recent cycle — it is a historical result.

`hollow_owner` in the same two eras:

| cut | era | base | fires | precision | lift | 95% CI |
|---|---|---|---|---|---|---|
| evidenced | v1.19–27 (label maintained) | 0.466 | 95 | 0.863 | 1.853 | [1.68, 2.08] |
| evidenced | v1.28–37 (label abandoned) | 0.335 | 65 | 0.846 | **2.524** | [2.21, 2.90] |
| full | v1.19–27 | 0.347 | 124 | 0.661 | 1.904 | [1.68, 2.15] |
| full | v1.28–37 | 0.264 | 99 | 0.556 | **2.103** | [1.75, 2.47] |

Significant in every era on every cut, precision essentially flat (0.863 → 0.846) across
a period in which the project's own labeling practice collapsed.

**This is the conclusion.** A human-applied label and an activity-derived signal are
comparably good, are complementary, and are strongest together. But one of them depends
on somebody remembering to do something, and over six years that practice decayed. The
other reads what people did rather than what they recorded, and it did not notice.

> Broken process hygiene is not only a risk signal in itself. It destroys the signals
> that depend on hygiene — exactly when you most need something that does not.

## 5. What did not work

**`prior_slip`** — "it has been retargeted before" — is not distinguishable from no
effect. CI [0.984, 1.169] evidenced, [0.997, 1.206] full. Both include 1.0. Intuitive,
unsupported.

**`late_target`** — committed close to the freeze — is *negatively* predictive, with its
entire CI below 1.0 on both cuts (0.796 and 0.819). Work committed late slipped **less**.
The most plausible reading is selection: a team committing late commits with better
information, and the work that was going to fail had already failed. The prior was
wrong, and the sign is the interesting part.

---

## What this cannot support

- **The freeze evaluation point was chosen after seeing the results.** The backtest's
  designed metric is first-fired; four evaluation points were compared and the one
  favouring our signal was reported. Treat the specific lift values as suggestive. The
  complementarity result in §3 and the era result in §4 do not depend on that choice.
- **No learned model was tested.** All signals are hand-written deterministic rules. This
  study says nothing about whether an ML model would do better; it was never tried.
- **290 rows (23%) remain `unresolved`** — outcome unknown to the instrument. 105 of them
  carry a `kep.yaml` self-report claiming delivery, so the residual is not simply stalled
  work; it is work whose paper trail cannot be followed.
- **One corpus, one organisation.** Kubernetes has unusually strong process hygiene and
  machine-readable artifacts. That makes it the best case for this method, not a typical
  one.
- **Recall is low throughout.** The best instrument here flags a sixth of committed work.
  Most slippage is not caught by any of these signals.

## What we got wrong along the way

Recorded because the corrections are more instructive than the result.

1. **The timeline fetch was truncated at page 1.** 475 of 644 issues; we were reading 6%
   of the data (7,322 events against 131,243). It produced a `unresolved` bucket we
   described as measuring process hygiene when it substantially measured our own fetch,
   and a "beta is structurally weakest" story fitted to a pagination artifact.
2. **Merge evidence was attributed by date rather than by the PR's milestone.** A
   cycle-length window sampled a slice of a multi-year stream. Kubernetes milestones its
   PRs; attribution should have been read, not inferred.
3. **`prior_slip` was published as crossing the significance boundary between cuts** — the
   centrepiece finding of one draft. It was an artifact of (1) and did not survive.
4. **"The human label beats our signal" was published on an invalid comparison** — a
   freeze-point predictor against a first-fired lift, two different measurements.

Every one was found by going outside the corpus. Nothing internal caught them, because
every internal check compares the corpus against itself. The ten-row manual audit — the
one success criterion the plan skipped — found (2) on its first execution.

## If someone continues this

- **Test a learned model.** The obvious gap. Everything here is hand-specified.
- **Build the remaining spec'd signals** — five of eight are untried, and `cross_org` and
  `org_overcommitted` are structural rather than activity-based, so they are not
  obviously correlated with what has been measured.
- **Find a second corpus.** One organisation cannot separate "this method works" from
  "this method works on Kubernetes."
- **Chase recall.** Precision is adequate; coverage is the weakness.
