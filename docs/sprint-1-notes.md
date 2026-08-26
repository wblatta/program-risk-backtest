# Sprint 1 notes — the first real backtest

Date: 2026-08-26. Corpus: `kubernetes/enhancements`, `kubernetes/sig-release`,
`kubernetes/community`, cloned at HEAD on that date.

This is a working note, not the finding. The finding (`README.md`) is sprint 3.
What follows is what the harness now measures, what the first numbers say, and —
at more length than the results themselves — what they are not yet good enough
to support.

## Reproducing it

```bash
.venv/bin/python cli.py fetch      # clones/updates into cache/k8s/ (gitignored)
.venv/bin/python cli.py build      # ~10 min: walks 649 KEP directories' git history
.venv/bin/python cli.py backtest   # <1s from cache/store.sqlite; writes out/k8s/*.csv
```

`cli.py backtest` with no flags reproduces the committed `out/k8s/*.csv` exactly.
`--min-minor N` restricts to milestones ≥ `v1.N` and is used below as a cut, not
as the default.

## What was built and what it measures

Sprint 1 delivers the core model (`work_item` / `org_unit` / `milestone` + one
event stream), point-in-time `snapshot()`, the Kubernetes adapter reading git
history only, three signals, and the backtest runner.

A **row** is one `(item, stage, milestone)` target that was present in
`snapshot(enhancements_freeze)` — i.e. a commitment the project had actually made
by the time the commitment window closed. Signals are evaluated on a fresh
snapshot every week from cycle start to code freeze, and the first week each
signal fires is recorded. The outcome is joined only from events with
`ts > code_freeze`, so nothing a signal sees can contain its own answer.
`lead` is weeks from first firing to code freeze. Everything a signal reads is
from `kep.yaml` and `keps/prod-readiness/*.yaml` history; no GitHub API call is
made anywhere in sprint 1.

### Corpus as built

| | |
|---|---|
| KEP directories found | 649 |
| Work items after exclusions | **644** |
| Events | **14,513** — activity 5,758, owner_changed 4,615, target_set 1,889, status_changed 996, outcome 1,255 |
| Event sources | `git-history` 13,258, `derived` 1,255 (the outcome labels) |
| Scheduled milestones | **19** (v1.19 – v1.37) |
| Org units from `sigs.yaml` | 24 |

Exclusions, all counted and printed by `cli.py build` rather than dropped
silently: 4 directories declaring `kep-number: 0` (process documents, not
enhancements) and 1 of the two directories sharing `kep-number: 2133`. **0**
`target_set` events were discarded by the known-milestone filter — every target
in the corpus resolves to a milestone the calendar knows about.

## Results

1,255 rows, all labeled. Base rate (positive class = `slipped` ∪ `dropped` ∪
`exception_denied`) = **0.302**.

| outcome | rows |
|---|---|
| shipped | 811 |
| slipped | 370 |
| exception_granted | 65 |
| dropped | 9 |
| exception_denied | **0** |

| signal | fired | precision | recall | lift | lift 95% CI | median lead | IQR | class |
|---|---|---|---|---|---|---|---|---|
| `hollow_owner` | 561 | 0.396 | 0.586 | **1.310** | 1.214 – 1.413 | 9.3 wks | 5.6 – 9.6 | risk |
| `prior_slip` | 483 | 0.331 | 0.422 | **1.097** | 1.002 – 1.207 | 8.1 wks | 5.3 – 9.3 | risk |
| `late_target` | 773 | 0.248 | 0.507 | **0.822** | 0.753 – 0.886 | 5.3 wks | 4.3 – 6.3 | risk |

CIs are 1,000-resample bootstraps over rows, seed 0.

### Reading these honestly

**`hollow_owner` is the only signal that beats the base rate.** Lift 1.31, CI
1.214–1.413, clear of 1.0. A KEP with no commit activity of any kind in the
8 weeks before a snapshot lands in the positive class — in practice, slips —
39.6% of the time against a 30.2% base, about a third more often, and it says so a median of 9.3 weeks before code freeze,
which is well inside the window where scope or staffing can still change. That
is H1's first supporting evidence. It is not a strong predictor: 60% of the
KEPs it flags are not observed to slip.

**`prior_slip` is marginal and should not be reported as working.** Lift 1.097
with a CI of 1.002–1.207. The lower bound excludes no-effect by 0.002. On this
data "this stage has been retargeted before" is not distinguishable from a coin
weighted at the base rate, and any narrative built on it would be built on the
third decimal place of a bootstrap. It is a baseline, and it behaves like one.

**`late_target` is negatively predictive. This is a real result and it goes
against the hypothesis.** Its entire CI (0.753–0.886) sits *below* 1.0. Targets
added in the last 3 weeks before enhancements freeze slip **less** often
(24.8%) than targets committed earlier (30.2%). It fires on 773 of 1,255 rows —
62% of everything — so it is not a small-sample artifact.

I do not know the mechanism and this data cannot tell me. The plausible reading
is selection: a KEP whose target lands days before the freeze deadline is
usually one that just cleared PRR and has a merged implementation waiting,
whereas a target set months earlier is an intention. If that is right, "late
target" is measuring *readiness*, not *haste*, and the a priori hypothesis had
the sign backwards. A late-add rule as a risk trigger would spend attention on
the safest population in the corpus.

`late_target` stays in the signal set, reported at lift 0.82. A signal with
sub-1.0 lift is not a useful risk signal and is not described as one anywhere in
this repo. It is also not deleted: the negative result is the most transferable
thing in this report, because "late adds are risky" is exactly the kind of
folk-wisdom rule a program office would otherwise adopt for free.

### Per-milestone outcome histogram

```
outcome       dropped  exception_granted  shipped  slipped
milestone_id
k8s:v1.19           0                  0       11        4
k8s:v1.20           0                  0       22       13
k8s:v1.21           0                  2       48       23
k8s:v1.22           1                  5       41       26
k8s:v1.23           0                  3       32       25
k8s:v1.24           1                  0       55       30
k8s:v1.25           0                  5       37       35
k8s:v1.26           0                  5       38       22
k8s:v1.27           0                  3       65       18
k8s:v1.28           0                  4       31       26
k8s:v1.29           1                  2       39       23
k8s:v1.30           0                 11       32       31
k8s:v1.31           1                  5       35       17
k8s:v1.32           0                  1       39       21
k8s:v1.33           2                  8       51       14
k8s:v1.34           2                  6       47       18
k8s:v1.35           0                  5       46       17
k8s:v1.36           1                  0       60        6
k8s:v1.37           0                  0       82        1
```

Two ends of this table are not trustworthy and both are visible in it.

**v1.19 (15 rows) is thin because the data does not exist before it.** The
earliest `kep.yaml` on `main` is dated 2020-03-17; v1.19's enhancements freeze is
2020-05-19. Every snapshot in that cycle is taken against a repository that is
two months old and still filling up. Cycles v1.21 onward carry 60–90 rows.

**v1.36 and v1.37 are right-censored.** v1.37 released *today* (2026-08-26) and
shows 82 shipped against 1 slip; v1.36 released four months ago and shows 60
against 6. A slip in this corpus is only observable once somebody edits
`kep.yaml` to move the target, which happens weeks to months after the fact. The
recent cycles are not better-run, they are less finished. Dropping v1.37 moves
the base rate from 0.302 to 0.323; dropping v1.36 as well moves it to 0.336.
The honest reading is that **0.302 understates the true slip rate** and that
the last two cycles should carry a censoring caveat in any published table.

### Cuts

By stage, slip rate is flat: alpha 0.299 (422 rows), beta 0.324 (417),
stable 0.290 (407). Whatever drives slips here is not stage.

By SIG (`out/k8s/by_org.csv`), the spread is wider — sig-storage 0.377 (151
rows), sig-instrumentation 0.375 (56), sig-node 0.351 (336) at the top;
sig-scheduling 0.209 (110), sig-release 0.077 (13) at the bottom — but most
groups are small enough that the differences are not separable from noise, and
no CI is computed for them. Treat `by_org.csv` as descriptive.

By cycle era (`--min-minor 26`, the most recent 12 cycles — the answer to
spec §14.6, "which cycles are comparable"): 836 rows, base rate 0.264,
`hollow_owner` lift 1.33 (CI 1.17–1.49), `prior_slip` 1.16 (1.03–1.30),
`late_target` 0.85 (0.76–0.93). Every conclusion above survives the restriction,
including the sign on `late_target`. The lower base rate is the censoring
effect: the recent-cycles window is the one that contains v1.36 and v1.37.
This is a cut, not the headline — the committed CSVs are the full range.

One row in `by_org.csv` is a data-quality artifact, not a SIG:
`k8s:api-machinery` (1 row) exists because
`sig-api-machinery/4346-informer-metrics` declared `owning-sig: api-machinery`
without the `sig-` prefix and fixed it on 2024-02-12, three days *after* v1.30's
enhancements freeze. The snapshot is correct about what the file said at the
commitment point; the org id is still wrong. Org ids are not validated against
`sigs.yaml`.

### The a priori parameters

Set in the design spec (§7) **before** any backtest ran, and unchanged since.
Sprint 1 uses three of the four; `M` belongs to S2, which is not implemented.

- **`N = 8` weeks** (`hollow_owner`'s silence window). A Kubernetes cycle is
  about 15 weeks. Eight weeks is over half a cycle: long enough that a normal
  review lull, a conference, or a holiday does not trip it, short enough that
  it can still fire with a cycle's worth of runway left. The measured median
  lead of 9.3 weeks is a consequence of this choice, not independent of it.
- **`K = 3` weeks** (`late_target`'s window before the commitment point). Three
  weeks is the tail of the enhancements-freeze scramble — targets added inside
  it were added under deadline pressure rather than during planning.
- **`L = 4` weeks** (the risk/status boundary). A signal has to fire at least a
  month before code freeze for a team to do anything but watch. Under four
  weeks it is a status update. All three signals clear it, so the risk/status
  split does no discriminating work yet; that is a property of this signal set,
  not evidence that the boundary is well chosen.
- (`M = 4` weeks, for S2 `gate_unassigned`: a required approver still missing a
  month out. Unused in sprint 1.)

Any later change to these is disclosed and re-reported on the last two cycles
only, per §7.

## The first manual label check

Ten rows sampled from `rows.csv` with `random_state=0`, checked against each
KEP's `kep.yaml` at HEAD and its commit history. The two HEAD fields leaned on
most below — `stage` and `latest-milestone`, the KEP's own summary of how far it
actually got — are **never turned into events** by `adapters/k8s/events.py` and
so are invisible to the labeler; commit recency is likewise not an input.
`status` is only partly independent (rule 2 reads `status_changed` inside the
drop window). This is a weak form of independence, not a clean holdout: it is
still the same repository. Sprint 2 should redo it against release notes.

| # | row | label | verdict |
|---|---|---|---|
| 1 | `kep-1682` alpha @ v1.19 (Skip Volume Ownership Change) | shipped | **Correct.** HEAD: `status: implemented`, `milestone.alpha: v1.19`. |
| 2 | `kep-2227` stable @ v1.27 (kubectl default container) | shipped | **Unverified.** HEAD carries `milestone.stable: v1.27` but `status: implementable`, and the file's last commit is 2023-02-02 — ten weeks before v1.27 shipped. Nothing in the corpus ever confirms or denies GA. Consistent with the rule; not evidence. |
| 3 | `kep-1209` stable @ v1.21 (Metrics Stability Framework) | exception_granted | **Correct**, and a near-miss rather than a failure: `release-1.21/exceptions.yaml` lists it approved, and HEAD shows `status: implemented`, `milestone.stable: v1.21`. Granted exception, then shipped in the same release. |
| 4 | `kep-4802` beta @ v1.34 (Windows Graceful Node Shutdown) | shipped | **Correct.** HEAD: `milestone.beta: v1.34`, `stage: beta`, `latest-milestone: v1.34` — the KEP advanced its own self-report to the target after the fact, which is the strongest evidence this corpus offers. |
| 5 | `kep-2625` alpha @ v1.22 (SMT-aware cpumanager policy) | shipped | **Correct.** HEAD: `milestone.alpha: v1.22`. Its status is `imlpemented` (sic) — the row that would break any code switching on `status` literally. |
| 6 | `kep-1258` beta @ v1.20 (Default Pod Topology Spread) | shipped | **Correct.** HEAD: `milestone.beta: v1.20`, and it went on to `stage: stable`, `latest-milestone: v1.24`. |
| 7 | `kep-2906` beta @ v1.24 (Kustomize Function Catalog) | slipped | **Correct.** Beta moved v1.24 → v1.25 after the freeze. See below — the *same KEP's* other two rows are both wrong. |
| 8 | `kep-2804` stable @ v1.27 (Consolidate Workload controllers status) | shipped | **Wrong.** HEAD: `stage: alpha`, `latest-milestone: v1.24`, `status: implementable`; last content commit 2022-02-03 (the 2022-09-22 commit is a repo-wide PRR-field cleanup). It did not go stable in v1.27 — it silently stopped, and v1's rule has no way to see that. |
| 9 | `kep-2413` beta @ v1.25 (Seccomp by default) | shipped | **Correct.** HEAD: `milestone.beta: v1.25`, later `stage: stable`, `latest-milestone: v1.27`. |
| 10 | `kep-1440` stable @ v1.28 (kubectl events) | shipped | **Correct.** HEAD: `milestone.stable: v1.28`, `stage: stable`, `latest-milestone: 1.28` (unquoted, no `v` — a formatting wart the parser normalizes). |

**8 correct, 1 unverifiable, 1 demonstrably wrong.** Every error and every
uncertainty runs the same direction: falsely `shipped`. Not one row was
falsely `slipped`. That is the expected shape given the rule — `shipped` is the
fallthrough — but seeing it hold across ten independent draws is the first
concrete measure of it.

Two rows deserve to be read together, because they show how the failure
compounds:

- `kep-2906` contributes three rows. Beta @ v1.24 is correctly `slipped`. But
  beta @ v1.25 and stable @ v1.27 are both labeled `shipped`, and the KEP is
  still `provisional` with no commit since 2022-02-23 — it was abandoned, not
  delivered. **One abandoned KEP produced one true positive and two false
  negatives.**
- `hollow_owner` fired on `kep-2804`'s stable @ v1.27 row on 2023-01-09, the
  first snapshot of the cycle, and on both of `kep-2906`'s false-`shipped`
  rows. In each case it was charged a **false positive for correctly
  identifying a KEP that had stopped.** The v1 labeling rule systematically
  penalizes the one signal that works.

### How big is that effect? A bound, not a guess

A `shipped` row can be shown wrong from the corpus itself when the KEP's own
`latest-milestone` at HEAD is *earlier* than the milestone the row claims it
shipped in, and its status is not any spelling of `implemented` — i.e. the KEP
never claims to have got there. That is true of **69 of 811 `shipped` rows
(8.5%), across 48 distinct KEPs.** It is a lower bound: it cannot catch a KEP
that stopped without ever revising `latest-milestone` (which is precisely what
`kep-2227` did).

Reclassifying only those 69 as positives moves the numbers as follows:

| | base rate | `hollow_owner` lift | `prior_slip` lift | `late_target` lift |
|---|---|---|---|---|
| v1 labels | 0.302 | 1.310 | 1.097 | 0.822 |
| 69 reclassified | 0.357 | **1.438** | 1.096 | **0.707** |

The labeling error is not neutral with respect to the conclusions. It
**understates** `hollow_owner` (which catches these rows) and **overstates**
`late_target` (which does not). `prior_slip` is unmoved and remains marginal.
This is a sensitivity check, not a result — the corrected column is not the
headline number, because the correction is itself unvalidated. It is here to
show which direction the known error pushes.

## What v1 gets wrong

1. **`activity` has no actor.** Git author emails do not map to GitHub handles
   reliably, so all 5,758 `activity` events carry `actor_id = k8s:unknown` and
   `hollow_owner` fires on "nobody touched this in N weeks", not "the listed
   owners did not touch this". The hypothesis under test is about *owners*.
   Sprint 1 tests a weaker proxy and the result must be read as such.
2. **`shipped` means "not observed to slip", not "verified shipped".** It is
   rule 5 of `LABELING.md`, the fallthrough. A KEP that goes quiet — no
   retarget, no status change, no target retraction — is labeled shipped.
   Measured floor on how often that happens: 8.5% of shipped rows (above).
3. **The positive class is `slipped` alone.** 379 positive rows, of which 370
   are `slipped`, 9 `dropped`, 0 `exception_denied`. The three-way class in
   §8 is aspirational; every number in the results table is really a
   slip-detection number. Separately, the 65 `exception_granted` rows sit in
   the *negative* class by design (§8: a granted exception is a near-miss, not
   a miss) — worth knowing when reading a base rate of 0.302.
4. **`exception_denied` is empty because precedence shadows it, not because
   the data is missing.** Over v1.19–v1.37 the recovered `exceptions.yaml`
   files contain 161 requests: 128 approved, 33 not approved. Fifteen of the 33
   match an actual backtest row — and **all fifteen are labeled `slipped`**,
   because `LABELING.md` rule 1 (slipped) is evaluated before rule 3
   (exception_denied). A SIG that is refused an exception and then honestly
   retargets its `kep.yaml` produces a slip event, and the slip wins. The label
   is therefore unreachable for exactly the population it was meant to
   describe. Either the precedence changes in v2 or the label should be dropped
   and the fact reported. It is not a data gap and should not be described as
   one. (The gap between 128 approved requests and 65 `exception_granted` rows
   is ordinary: a request only becomes a label if that KEP also had a target at
   that milestone at enhancements freeze.)
5. **v1.20's exception data is unrecoverable.** `release-1.20/exceptions.yaml`
   is malformed beyond the ZWSP cleanup that rescues v1.23. For v1.20, an
   `exception_*` label can never appear — not because none were requested, but
   because the record could not be read. `load_exceptions` reports it as a
   `SkippedExceptionsFile`; the build prints it. Known-missing, not
   known-absent.
6. **Targets dropped by the known-milestone filter: 0.** Recorded because it
   would otherwise be an invisible loss. It is genuinely zero on this corpus.
7. **Org attribution is point-in-time and unvalidated.** See `k8s:api-machinery`
   above.
8. **Recent cycles are censored** (v1.36, v1.37) and the earliest cycle is
   data-starved (v1.19). Neither is excluded; both are quantified above.
9. **Signals were not tuned, and also not swept.** `N`, `K`, `L` are the a
   priori values. The sensitivity grid over them (§8) is sprint 2. Nothing here
   is tuned on the test set, and nothing here is robust to the parameters
   either — both statements are currently true.

## What these numbers cannot support

- **They cannot support "hollow ownership predicts slips" as stated in the
  thesis.** They support "*inactivity from anyone* precedes an *observed
  retarget*". Two substitutions, both weakening. H1 is not yet tested.
- **They cannot support any claim about shipping.** Nothing in sprint 1
  observes a feature landing in a release. The word "shipped" in `rows.csv`
  means "no contrary evidence appeared in `kep.yaml`". No code-merge evidence,
  no `tracked/yes` at release, no release notes.
- **They cannot support a precision figure a program office should act on.**
  With a known error floor of 8.5% of `shipped` rows (69 rows, 5.5% of the
  total) concentrated entirely in one class, the precision column is accurate to
  roughly the first decimal place, not the third. The CIs quantify sampling error only; they say nothing about label
  error, which is the larger term here.
- **They cannot support cross-SIG comparison.** `by_org.csv` has no CIs and
  several groups under 20 rows.
- **They cannot support a claim about intervention.** By design (§13) — the
  backtest measures association between an observable state and an outcome, and
  never whether acting on it helps.
- **They can support the negative result.** `late_target`'s CI lies entirely
  below 1.0 across 773 firings and 19 cycles, and the known label error pushes
  its lift *further* down, not up. "Late-added targets are riskier" is not true
  in this corpus, and that conclusion survives the caveats above.

## Known blind spots carried from `adapters/k8s/LABELING.md`

Repeated here so this note is readable alone; `LABELING.md` is normative.

- A KEP that silently stops is labeled `shipped` (rule 5, fallthrough).
- A KEP whose yaml is updated late is still caught, because rule 1 looks at all
  later events rather than only the next cycle. Lateness costs nothing except
  in the censored recent cycles.
- `removed` is deliberately **not** in the drop-status set:
  `281-dynamic-kubelet-configuration` shipped alpha in v1.8 and beta in v1.11,
  and its status records the *feature's* eventual removal from Kubernetes years
  later, not the KEP's abandonment. Treating it as a drop would relabel a
  historical success as a failure.
- `superseded` **is** a genuine drop and is in the set.
- Exception `phase` from pre-v1.24 files is `"unspecified"` — the freeze phase
  in those files lives only in a free-text comment. No label reads `phase`, so
  the placeholder is bookkeeping rather than a guess dressed as data.
- `release-1.20` exception data is unavailable (above).

## What sprint 2 must do

In priority order, and the first two are the same problem:

1. **Reverse the precedence: verify shipping first.** Rule 5 must stop being
   the fallthrough. `shipped` should require positive evidence — the tracking
   issue closed with `tracked/yes` at release, or code-merge evidence — and
   everything without it should fall through to a new label (`unresolved`,
   distinct from both `shipped` and `slipped`) rather than being counted as a
   success. Every finding in this note that runs one direction runs that
   direction because of this ordering. While the precedence is open, settle
   `exception_denied` too: either an exception decision outranks the retarget
   it caused, or the label goes and the reason is published. Leaving an
   unreachable label in the vocabulary is worse than either.
2. **Land the tracking-issue API data.** `tracked/yes|no|out-of-tree`,
   `stage/*`, `lead-opted-in` labels with timeline timestamps. This is the
   source that answers "did it actually land", and it also brings S0
   (`process_tracked`) — the control the whole exercise needs, because a signal
   that cannot beat the project's own status field is not worth reporting.
3. **Give `activity` real actors.** Tracking-issue commenters and PR authors
   from the API, so `hollow_owner` can finally test what H1 claims: silence
   *from the listed owners*, not silence from everyone.
4. **Re-run the ten-row manual check against release notes**, not against
   `kep.yaml`, and extend it to ~20 rows per cycle for a few cycles. The check
   in this note is bounded by using the same repository as the labeler.
5. **Sensitivity grid over `N`, `K`, `L`**, reported and not tuned on, plus CIs
   on the by-SIG cut or its removal from any published table.
6. **Decide what to do about censoring.** Either exclude cycles whose release is
   within ~6 months, or model the lag. Do not publish v1.36/v1.37 alongside
   mature cycles without a caveat.

Also queued and cheap: S2, S3, S6 (spec §7), and a `by_stage.csv` output, which
is a one-line `groupby` on `rows.csv`.
