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

The **Verdict** column was filled in at the end of sprint 1 (2026-08-26), after
the corpus build and the first backtest run. "Confirmed" means the claim was
checked against the real clones and the path is now in code; "Refuted" means it
is wrong and the design spec has been amended.

| Claim | Confidence | If wrong | Verdict (sprint 1) |
|---|---|---|---|
| `kep.yaml` has `owning-sig`, `participating-sigs`, `status`, `stage`, `latest-milestone`, `milestone.{alpha,beta,stable}`, `prr-approvers`, `authors`, `reviewers`, `approvers` | High | Adapter field map changes | **Partly refuted.** All confirmed except `prr-approvers`, which does not exist in any `kep.yaml` — see the PRR row below. `status` is also not a clean enum (spike findings). |
| `sigs.yaml` in `kubernetes/community` is the canonical org chart | High | — | **Confirmed.** `sigs.yaml` at the repo root → 24 `org_unit` rows. Caveat: `kep.yaml`'s `owning-sig` is *not* validated against it, so a typo becomes its own org (design spec amendment 9, sprint 1). |
| Tracking issues in `kubernetes/enhancements` carry `tracked/yes`, `stage/*`, `sig/*`, `lead-opted-in` labels, and the GitHub timeline API gives label-applied timestamps | High | Signal S0 changes source | **Not yet tested.** Labels confirmed to exist (planning amendment 8); the API is sprint-2 work and no timeline call has been made. |
| `kubernetes/sig-release` has per-release schedule data with freeze and release dates | Medium — exact path unknown | Hand-maintain a small calendar table in the adapter | **Confirmed, with the fallback also used.** Path: `releases/release-1.N/README.md`, a markdown timeline table. Parsed by `adapters/k8s/milestones.py` into `adapters/k8s/calendar.yaml`, which is committed, hand-verified, and is the runtime source of truth — because the format differs by era and v1.19/v1.21/v1.22 contain no year at all (design spec amendment 8, sprint 1). 19 scheduled milestones, v1.19–v1.37. |
| Exception requests are findable as structured artifacts | Medium-low | Fold `exception_*` outcomes into shipped/slipped and say so | **Confirmed.** Path: `releases/release-1.N/exceptions.yaml` in `kubernetes/sig-release`. Two schemas (flat list before v1.24, `enhancementFreeze`/`codeFreeze` mapping after) plus one unparseable file at v1.20; 161 requests recovered over v1.19–v1.37, yielding 65 `exception_granted` labels and 0 `exception_denied`. See design spec amendment 7, sprint 1. |
| PRR became mandatory around v1.21; earlier cycles are not comparable | Medium | Backtest window shrinks or gets a per-cycle rule | **Confirmed in shape, unproven in date, and not acted on.** PRR approvers live in `keps/prod-readiness/<sig>/<kep-number>.yaml` (453 files), *not* in `kep.yaml`; the first was added 2020-12-22, at the start of the v1.21 cycle, which is consistent with the claim. Nothing in the data records "mandatory", so the backtest does **not** filter on it: all 19 cycles are run and comparability is reported as a cut instead (design spec amendment 1, sprint 1). |
| Retrospectives exist per release as markdown in `sig-release` | Medium | Spot-check source becomes release-team meeting notes | **Refuted.** Zero files matching `retro`/`retrospective`/`postmortem` exist anywhere in the `kubernetes/sig-release` clone, and `kubernetes/community` has only contributor-summit and 2016 SIG retros — nothing per release. Sprint 3's label spot-check needs a different source (release-team meeting notes, or the tracking issues themselves). |
| The enhancements tracking board has been a GitHub Project recently and a spreadsheet earlier | Medium | Older cycles need a different S0 source or are dropped | **Not yet tested.** No board data is used in sprint 1; S0 (`process_tracked`) is unimplemented. |
| SIGs frequently do *not* update `milestone.*` when a KEP misses | Medium — this is the crux | If they reliably do, slippage is cheap to detect; if not, the tracking issue is the primary source | **Confirmed as a partial failure, and it is the dominant limit on sprint 1.** They update it often enough to detect 370 slips across 1,255 rows (29.5%), but not reliably: the manual label check in `docs/sprint-1-notes.md` found a KEP (`2804-consolidate-workload-controllers-status`) whose `kep.yaml` still targets `stable: v1.27`, was last touched in 2022, and is labeled `shipped` by rule. The tracking issue is therefore required, as predicted — sprint 2. |

### Spike findings (Task 1 ingestion spike, 2026-08-26)

Ran `cli.py spike` against a real clone of `kubernetes/enhancements`. Glob
`keps/sig-*/*/kep.yaml` matched 612 files; 610 parsed, 2 raised errors. (656
`kep.yaml` files exist under `keps/` in total — the other 44 live under
`keps/provider-aws/`, `keps/prod-readiness/`, and the `keps/NNNN-kep-template/`
placeholder, correctly excluded by the sig-prefixed glob.)

Status histogram (610 rows, 11 distinct values):
`{'implemented': 286, 'implementable': 254, 'provisional': 46, 'withdrawn': 10,
'replaced': 5, 'rejected': 3, 'deferred': 1, 'superseded': 1,
'provisional|implementable|implemented|deferred|rejected|withdrawn|replaced': 1,
'implemented (alpha)': 1, 'imlpemented': 1, 'removed': 1}`

- **`status` is not a clean enum in the wild.** Alongside the 9 expected
  values, one file has a typo (`imlpemented`,
  `sig-node/2625-cpumanager-policies-thread-placement`), one has an appended
  qualifier (`implemented (alpha)`, `sig-instrumentation/1753-logs-sanitization`),
  and one has the *entire pipe-separated placeholder list from the template*
  leaked in verbatim (`provisional|implementable|implemented|deferred|rejected|withdrawn|replaced`,
  `sig-api-machinery/5000-api-linting-crd-schema-tooling`). Any signal/label
  logic reading `status` must normalize it, not switch on it directly.
- **The `prr-approvers` claim in the table above is wrong.** Zero of the 612
  `kep.yaml` files under `keps/sig-*/` contain a `prr-approvers:` key (checked
  case-insensitively for any `*prr*:` key — none exist). PRR content is a
  free-text Q&A block under a `# PRR answers` comment, not a structured
  approver list. `adapters/k8s/config.py`'s `REQUIRED_ROLES = ["prr_approver"]`
  will need a different extraction source than `kep.yaml` itself (an OWNERS
  file, a PRR-specific doc, or the tracking issue) — flagging for whichever
  later task builds that signal.
- **`kep-number` is not a reliable unique key.** Two live KEP directories both
  declare `kep-number: 2133`: `sig-cloud-provider/2133-out-of-tree-credential-provider`
  and `sig-node/2133-kubelet-credential-providers`. Separately, three
  non-feature process KEPs (`0000-kep-process`, `0000-community-forum`,
  `0000-anago-to-krel-migration`) all declare `kep-number: 0`. An
  `item` ID scheme keyed purely on `k8s:kep-{number}` would collide on both.
  The directory name is the only actually-unique handle in this corpus.
- **Directory numbering and `kep-number` can disagree for reasons beyond
  zero-padding.** `sig-network/0752-endpointslices` vs. `kep-number: 752` is
  the expected cosmetic case. But `sig-node/2043-pod-resource-concrete-assigments`
  declares `kep-number: 1884` — a real mismatch, not padding — presumably a
  renumbering where the directory rename and the yaml field drifted apart.
- **Two files fail to parse outright**, both from the same root cause: PyYAML's
  implicit timestamp resolver raises a bare `ValueError` (not `yaml.YAMLError`)
  for a calendrically-invalid `creation-date`, which the original
  `except yaml.YAMLError` in `parse_kep_yaml` did not catch, crashing the
  whole spike instead of recording a per-file error:
  - `sig-api-machinery/4355-coordinated-leader-election/kep.yaml`:
    `creation-date: 2023-14-05` → `month must be in 1..12, not 14`
  - `sig-scheduling/5075-dra-consumable-capacity/kep.yaml`:
    `creation-date: 2025-30-01` → `month must be in 1..12, not 30`

  Fixed by widening the caught exception to `(yaml.YAMLError, ValueError)`,
  with a regression test (`test_invalid_calendar_date_raises_kep_parse_error`)
  covering the real-world case.
- **Confirmed with no surprises:** `title`, `owning-sig`, and `authors` are
  populated on all 610 parsed KEPs (no empty strings, no empty tuples) —
  matches the "mandatory in the schema" claim in §1. `owning-sig`,
  `status`, `stage`, `latest-milestone`, and `milestone.{alpha,beta,stable}`
  are present and shaped as expected everywhere they appear.
- **Routinely unset, as expected:** `participating-sigs` is empty for
  228/610 (37%) KEPs; `milestones` is an empty dict for 142/610 (23%); `stage`
  and `latest_milestone` are both `None` for 36/610 (6%, plausibly
  `provisional` KEPs that never got a target release). Consistent with §1's
  note that "unowned" can't literally happen but hollow/thin metadata can.
- One stray value worth flagging but not acting on for Task 1 (YAGNI):
  `sig-api-machinery/1152-less-object-serializations` has
  `latest-milestone: '0.0'`, which parses cleanly to `"v0.0"` — it isn't in
  `_PLACEHOLDERS` so it survives, but it reads as an unset sentinel rather
  than a real release. Revisit if a later task's milestone logic trips on it.

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
