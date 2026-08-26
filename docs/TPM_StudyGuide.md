# TPM Study Guide: Kubernetes as a Program Corpus

A reading list for a TPM who has never worked inside the Kubernetes project and
needs to understand its governance well enough to (a) write an honest outcome
labeling rule and (b) defend every K8s-specific claim in the finding.

Budget: about two hours, targeted. Not "read the SIG docs." Each item below says
what to look for and what question you should be able to answer afterward.

Status of this document: written before the ingestion spike. Everything under
"Verify in the spike" is an assertion, not a fact. Correct this file as you learn.

---

## 1. Vocabulary map: Kubernetes → corporate TPM

Use this when explaining the project in an interview. The point is that K8s has
the same shapes as a corporate SDLC, just with different names and more of it
written down.

| Kubernetes | Corporate equivalent | Notes |
|---|---|---|
| SIG (Special Interest Group) | Org / team with a charter | ~25 of them. Owns code areas via OWNERS files. |
| KEP (Kubernetes Enhancement Proposal) | Epic / program of record | The unit of planned work. Has a `kep.yaml` (metadata) and `README.md` (design doc). |
| `owning-sig` / `participating-sigs` | Owning team / dependent teams | Mandatory in the schema, so "unowned" cannot literally happen — look for *hollow* ownership instead. |
| Stage: alpha → beta → stable | Feature maturity gates | Each stage has its own target release. One KEP = several targets over time. |
| Release (v1.NN) | Quarterly release / planning increment | Roughly three per year, ~15-week cycles. |
| Enhancements freeze | Planning lock / commitment deadline | KEP must be `implementable` and opted-in by the SIG lead to be tracked. |
| Code freeze | Feature complete | After this, only exceptions land. |
| Release team | PMO | Rotating volunteer team. Runs tracking, communications, bug triage. |
| Enhancements tracking (issue labels, board) | Status spreadsheet | The release team's own view of what's on track. This is signal S0 — the control. |
| PRR (Production Readiness Review) | Launch readiness / ops review | A required approver role. A KEP without a PRR approver is blocked. |
| Exception request | Scope change / freeze exception | Filed after freeze to land late. The "near miss" population. |
| Retrospective | Post-mortem / release retro | Per release, human-written, names what went wrong. |
| OWNERS files | Code ownership / approver lists | Per directory. Reviewers and approvers by handle. |

---

## 2. Reading list

### 2.1 The KEP process and template
**Where:** `kubernetes/enhancements` → `keps/README.md`, `keps/NNNN-kep-template/`
**Read for:** what every `kep.yaml` field means and — more important — *who is
supposed to update it and when.* The whole slippage question hinges on whether
SIGs actually update `milestone.*` when they miss.
**Answer afterward:**
- Which fields are mandatory? Which are routinely stale?
- What does `status: implementable` mean vs `provisional` vs `implemented`?
- When a KEP misses a release, what is *supposed* to change in the yaml?

### 2.2 Two real KEPs, end to end
**Where:** pick one that shipped on its first target and one that slipped at
least once. Read the `kep.yaml` history (`git log -p -- <path>`), the README,
the PR(s) that changed it, and its tracking issue in `kubernetes/enhancements`
issues.
**Read for:** the gap between what the yaml says and what the tracking issue
says. This is the mess. Note every place the two disagree.
**Answer afterward:**
- For the slipped one: where is the slip *first* visible — yaml, tracking issue
  label, a comment, or nowhere?
- Who touched the KEP in the eight weeks before freeze? Were they the listed
  authors?
- Does the README name dependencies on other KEPs? In what phrasing?

### 2.3 Release cycle and the exceptions process
**Where:** `kubernetes/sig-release` → the release cycle overview and the
exceptions document (search the repo for "exception"). Also the per-release
directory under `releases/` for a recent cycle.
**Read for:** the exact dates that define a cycle (enhancements freeze, code
freeze, release) and where they are recorded in machine-readable form, if
anywhere. And: how an exception is actually filed — email, issue, PR, comment?
**Answer afterward:**
- Where does the calendar live? Is it parseable, or does the adapter need a
  hand-maintained table?
- Are exception requests findable as structured artifacts? If not, the
  `exception_*` outcome labels are not reliably derivable.

### 2.4 One release retrospective
**Where:** `kubernetes/sig-release` → `releases/release-1.NN/` for a recent
release; look for the retrospective document.
**Read for:** how the release team talks about what went wrong. Which KEPs are
named. Whether the reasons given match anything observable in the data
(ownership churn, late PRR, dependency on another KEP).
**Answer afterward:**
- Could the retro's named problems have been predicted from the yaml and
  tracking-issue history? Which signal would have caught each?

### 2.5 The current release's enhancement tracking board
**Where:** linked from `kubernetes/sig-release` for the in-flight release.
Historically a spreadsheet; more recently a GitHub Project. Find the current
one and at least one older one.
**Read for:** what the release team tracks that the yaml doesn't. Columns,
labels, states. This is the definition of signal S0.
**Answer afterward:**
- What does "tracked" mean operationally? Which label or column is the source
  of truth?
- Has the format changed across the release window you plan to backtest? If
  so, S0 needs a per-cycle adapter rule.

### 2.6 The org chart
**Where:** `kubernetes/community` → `sigs.yaml` and `sig-list.md`; one SIG's
`charter.md`; one `OWNERS` file in `kubernetes/kubernetes`.
**Read for:** how leadership is recorded and how stale it is. Chairs and tech
leads listed in `sigs.yaml` versus who actually approves PRs.
**Answer afterward:**
- Is `sigs.yaml` enough for the `org_unit` entity, or does the adapter also
  need OWNERS files for "who actually works here"?

---

## 3. Verify in the spike

Claims made during design without verification. The spike and the reading
above should confirm or correct each one. Update the design spec when done.

| Claim | Confidence | If wrong |
|---|---|---|
| `kep.yaml` has `owning-sig`, `participating-sigs`, `status`, `stage`, `latest-milestone`, `milestone.{alpha,beta,stable}`, `prr-approvers`, `authors`, `reviewers`, `approvers` | High | Adapter field map changes |
| `sigs.yaml` in `kubernetes/community` is the canonical org chart | High | — |
| Tracking issues in `kubernetes/enhancements` carry `tracked/yes`, `stage/*`, `sig/*`, `lead-opted-in` labels, and the GitHub timeline API gives label-applied timestamps | High | Signal S0 changes source |
| `kubernetes/sig-release` has per-release schedule data with freeze and release dates | Medium — exact path unknown | Hand-maintain a small calendar table in the adapter |
| Exception requests are findable as structured artifacts | Medium-low | Fold `exception_*` outcomes into shipped/slipped and say so |
| PRR became mandatory around v1.21; earlier cycles are not comparable | Medium | Backtest window shrinks or gets a per-cycle rule |
| Retrospectives exist per release as markdown in `sig-release` | Medium | Spot-check source becomes release-team meeting notes |
| The enhancements tracking board has been a GitHub Project recently and a spreadsheet earlier | Medium | Older cycles need a different S0 source or are dropped |
| SIGs frequently do *not* update `milestone.*` when a KEP misses | Medium — this is the crux | If they reliably do, slippage is cheap to detect; if not, the tracking issue is the primary source |

---

## 4. Questions to bring back to the design

After the reading and the spike, you should be able to take a position on:

1. **The labeling rule.** Draft precedence is: shipped → exception → slipped →
   dropped. Is that the right order? What cases fall through?
2. **The cycle window.** Which releases are comparable enough to pool?
3. **Signal S0.** What exactly is "the process says it's on track"?
4. **Dependencies.** How do KEP READMEs phrase cross-KEP dependencies? Is the
   phrasing regular enough for a pattern, or does it need an LLM?
5. **Activity.** What counts as "the owner is active on this item" — commits to
   the KEP, comments on the tracking issue, PRs in `kubernetes/kubernetes`?
   The cheapest one that's honest wins.

---

## 5. Interview framing notes

Things worth being able to say out loud, once the reading backs them up:

- "Kubernetes writes down what most companies keep in people's heads —
  ownership, stage targets, readiness gates — which is why it's a usable
  corpus. The mess isn't missing structure; it's that three sources of truth
  disagree."
- "Every KEP has an owning SIG by schema. Unowned work doesn't exist there.
  What exists is *hollow* ownership: listed owners who haven't touched the
  item in months. That turned out to be the sharper version of my thesis."
- "I set the signal thresholds before running the backtest and reported the
  sensitivity grid, because with a few hundred rows anything I tuned would be
  noise."
- "The backtest can't tell you why something slipped — the retros do that. It
  tells you which observable states preceded slips, and how many weeks early."
