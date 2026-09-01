# Program Risk Backtest — Design Spec

Date: 2026-08-26
Status: approved in brainstorming; K8s-specific claims tagged `[verify in spike]`
are assertions to be confirmed in sprint 0 and corrected here.

## 1. Purpose

A backtest harness for program-risk signals, with pluggable corpora. Its first
output is a written finding on the Kubernetes enhancement process: which
observable states of a planned work item preceded a missed release, with what
precision, and how many weeks early. Its second output is the same finding on
GitLab, which is what turns a result into a method.

The tool exists to produce the finding. The finding is the deliverable a
reader consumes; the tool is the appendix that proves it was built.

### Thesis under test

Three opinions, held by the author from prior TPM work, restated as testable
hypotheses:

1. **Hollow ownership predicts slips.** Every item has a nominal owner; items
   whose listed owners are inactive on the item slip more often.
2. **A stale dependency is a leading indicator.** Items depending on another
   item that is itself late or inactive slip more often, and the signal fires
   early enough to act on.
3. **Risk register ≠ status update.** Signals separate by measured lead time
   into those actionable before freeze (risk) and those that fire too late to
   change anything (status). This is derived, not asserted.

The finding reports the verdict on each, including the one that fails.

### Audience

A skeptical hiring manager who will read the README and one analysis, skim the
code, and not run it. Design for reading first, running second.

## 2. Scope and priorities

In scope, in priority order:

1. K8s adapter, core model, signals, backtest, written K8s finding.
   **Presentable at end of sprint 3. This is the critical path.**
2. GitLab adapter and finding; cross-corpus comparison.
3. `register` (live view) and an MCP wrapper over the store.

Out of scope: meeting transcripts, Slack, sentiment or free-text risk
scoring, any hosted infrastructure, any attempt to measure intervention effect.

Constraints: Python; no paid infrastructure; runs on a laptop from a clone;
public repo. Author budget is ~6–8 hours/week of review and judgment for ~3
months; Claude Code does the build.

## 3. Normalized model

Three reference tables and one event stream. All IDs are namespaced by
corpus (`k8s:kep-1234`, `gitlab:issue-98765`) so multiple corpora coexist in
one store.

```
work_item(id, title, url)
org_unit(id, name)
milestone(id, freeze: date, release: date, dates: json)   -- dates holds any extra named dates
event(ts, item_id, kind, payload: json, source)
```

### Event kinds

| kind | payload | notes |
|---|---|---|
| `target_set` | `stage?`, `milestone_id` | `stage` optional; K8s uses alpha/beta/stable, GitLab has none. A later `target_set` for the same stage with a later milestone is a slip. |
| `status_changed` | `status` | Adapter-normalized: provisional, implementable, implemented, withdrawn, tracked, untracked. |
| `owner_changed` | `subject_id`, `role`, `op` (add/remove) | role ∈ owning, participating, author, approver, plus corpus-declared required roles (e.g. `prr_approver`). |
| `dependency_changed` | `depends_on_id`, `op`, `confidence?`, `extractor?` | LLM-sourced events carry `confidence < 1` and `source = llm`. |
| `activity` | `actor_id`, `kind`, `ref` | commit, comment, pr_merged. Feeds hollow-ownership signals. |
| `outcome` | `milestone_id`, `stage?`, `result` | result ∈ shipped, slipped, dropped, exception_granted, exception_denied. |

### Rules

- **Temporal rule.** `ts` is when the fact became true in the source system —
  commit time, label-applied time, milestone-changed time. Never fetch time.
  An adapter that cannot honor this for a kind omits the kind.
- **Provenance.** `source` is mandatory on every event: `git-history`,
  `tracking-issue`, `api`, `retro`, `llm`. When sources disagree, both events
  exist; the adapter's precedence rule is code, documented in its
  `LABELING.md`.
- **Leakage guard.** `snapshot(as_of)` replays only events with
  `kind != 'outcome'` and `ts <= as_of`. Outcomes are joined to snapshots only
  where `outcome.ts > snapshot.as_of`.

### Snapshot

`snapshot(events, as_of) -> DataFrame` with one row per item: current targets
by stage, status, owners by role, dependencies, last activity timestamp per
owner. Computed on demand; persisted only if it proves slow.

### Deliberately absent

Free-text bodies, comments, transcripts. The raw cache keeps them. Anything a
signal needs from text is extracted adapter-side into an event with
`source = llm`. No `person` table, no org hierarchy, no capacity table until
GitLab needs them.

## 4. Adapter contract

An adapter is a Python package under `adapters/<corpus>/` exposing:

```
fetch(cache_dir)        -> None            idempotent, incremental, raw only
milestones()            -> list[Milestone]
org_units()             -> list[OrgUnit]
events()                -> Iterable[Event]
```

plus `LABELING.md` documenting its outcome rule, and a `config` declaring
required owner roles and any corpus-specific parameters.

### Requirements

- `events()` is deterministic: two runs over the same cache produce identical
  output. LLM calls are keyed by SHA-256 of their input and cached under
  `cache/<corpus>/llm/<hash>.json`; the cache is committed so the repo
  reproduces without an API key.
- Raw cache is never normalized in place. Layout:
  `cache/<corpus>/<source>/…`, gitignored except `llm/`.

### Conformance tests (shared, every adapter must pass)

1. Every `target_set` references a known milestone; every event references a
   known item.
2. No `outcome` precedes its item's first event; no `outcome` precedes its
   milestone's `freeze`.
3. For each milestone, `snapshot(freeze)` contains ≥ 1 item targeted at it.
4. `events()` is byte-identical across two consecutive runs.
5. `adapters/<corpus>/LABELING.md` exists and is non-empty.
6. Every event has a non-empty `source`.

## 5. Kubernetes adapter

### Sources

| Repo | Used for |
|---|---|
| `kubernetes/enhancements` (git clone) | `keps/sig-*/NNNN-*/kep.yaml` and `README.md`, with full history |
| `kubernetes/enhancements` (issues API) | tracking issues: labels, timeline events, comments |
| `kubernetes/community` (git clone) | `sigs.yaml` → `org_unit` `[verify in spike]` |
| `kubernetes/sig-release` (git clone) | release schedules → `milestone`; retrospectives; exceptions process `[verify in spike: exact paths]` |

Git history is walked locally (`git log --format=%H,%ct -- <path>` then
`git show <sha>:<path>`), not via the API — unlimited, fast, and it is the
time-travel the backtest needs. The API is used only for issue timelines.

### Field mapping `[verify in spike]`

| Normalized | K8s | ts |
|---|---|---|
| `work_item` | one per `kep.yaml`; id `k8s:kep-NNNN` | first commit |
| `target_set` | change in `milestone.{alpha,beta,stable}` or `latest-milestone` between consecutive yaml versions | commit time |
| `status_changed` | change in `status` (yaml); `tracked/yes` label add/remove on tracking issue → tracked/untracked | commit time; label event time |
| `owner_changed` | diffs in `owning-sig`, `participating-sigs`, `authors`, `reviewers`, `approvers`, `prr-approvers` | commit time |
| `activity` | comments and commits by listed authors on the KEP's PRs and tracking issue | event time |
| `dependency_changed` | LLM extraction over README versions; output is a list of KEP numbers with confidence | commit time of that README version |
| `outcome` | labeling rule below | milestone release date |

Required roles config: `["prr_approver"]` `[verify in spike: when PRR became mandatory]`.

### Labeling rule, draft v1 `[verify in spike — revise after reading real cases]`

For each `(item, stage, milestone)` target present in `snapshot(freeze)`,
evaluated at `release`:

1. **shipped** — tracking issue closed with `tracked/yes` at release AND yaml
   stage at release ≥ target stage.
2. **exception_granted / exception_denied** — an exception request artifact
   exists for this item and milestone. `[verify in spike: are these
   structured enough to find? If not, drop these labels and say so.]`
3. **slipped** — a later `target_set` moves this stage to a later milestone.
4. **dropped** — status → withdrawn, or removed from tracking with no retarget
   within one subsequent cycle.

Precedence in that order. Retrospectives are not a label source; they are
used to spot-check ~20 labels per cycle and are cited in the finding.

### Known uncertainties

See `docs/TPM_StudyGuide.md` §3 for the full table. The single most
consequential: whether SIGs reliably update `milestone.*` on a miss. If they
do not, the tracking issue becomes the primary slip source and yaml history is
secondary.

## 6. GitLab adapter (sprint 4; mapping documented now)

| Normalized | GitLab |
|---|---|
| `work_item` | issues with weight, or epics, in selected `gitlab-org` groups |
| `org_unit` | stage groups from the handbook (`data/stages.yml`) |
| `milestone` | milestones API; monthly releases |
| `target_set` | resource milestone events API (timestamped) |
| `status_changed` | resource label events (`workflow::*`) and state events |
| `owner_changed` | assignee events; group from labels |
| `dependency_changed` | issue links API (`blocks`); `source = api`, no LLM |
| `activity` | notes and MR events by assignees |
| `outcome` | milestone at close vs milestone at freeze; `missed:*` labels |

Capacity (weight, headcount) becomes available here; an optional
`org_unit_capacity` table is added when this adapter lands, not before.

## 7. Signals

Interface: `signal(snapshot, milestone, context) -> dict[item_id, bool]`.
`context` carries org units, adapter config, `params`, and prior outcomes
(`ts < as_of` only). `signals/` imports nothing from `adapters/`; this is the
corpus-agnosticism test and is enforced by a test.

| # | name | fires when | tests |
|---|---|---|---|
| S0 | `process_tracked` | corpus's own process marks the item on track (K8s: tracked status) | control |
| S1 | `hollow_owner` | no owner/author has `activity` on the item in the last N weeks | H1 |
| S2 | `gate_unassigned` | a required role has no holder and freeze ≤ M weeks away | H1 |
| S3 | `cross_org` | > 1 participating org unit | H1 variant |
| S4a | `dep_ordering_conflict` | depends on X whose target for the needed stage is ≥ this item's milestone | H2 |
| S4b | `dep_inactive` | depends on X for which S1 fires | H2 |
| S5 | `prior_slip` | this stage's target was moved before | baseline |
| S6 | `org_overcommitted` | owning org's targeted count > its historical max shipped per milestone | throughput |
| S7 | `late_target` | `target_set` for this milestone within K weeks of freeze | late adds |

Sprint 1 ships S1, S5, S7 (git-history only). S0 lands in sprint 2 with the
tracking-issue API, alongside S2, S3, S6. S4a/b when dependency extraction lands in sprint 3.

`params = {N: 8, M: 4, K: 3, L: 4}` weeks, set a priori before the first
full backtest and recorded in the finding. Any later change is disclosed and
re-reported on the last two cycles only.

Not signals, by design: anything read from prose except dependencies. No
sentiment, no "LLM thinks this is risky" — uncalibratable.

## 8. Backtest

**Row** = one `(item, stage, milestone)` target present in `snapshot(freeze)`.
Positive class = outcome ∈ {slipped, dropped, exception_denied}.
`exception_granted` counts as shipped and is reported separately as near-miss.

**Cycles** = the most recent ~8 releases `[verify in spike: comparability
across PRR and tracking-format changes]`.

**Procedure**, per cycle:

1. Snapshot weekly from cycle start to `freeze`.
2. Run every signal on every snapshot; record `first_fired_at` per
   `(row, signal)`.
3. Join rows to outcomes with `ts > freeze`.

**Metrics per signal**: fired, precision, recall, lift (precision ÷ base
rate), median lead in weeks with IQR, `lead_class` (`risk` if median lead ≥ L
else `status`). Bootstrap 95% CIs on precision and lift by resampling rows.
`lead_class` describes **lead time only** and carries no claim about predictive
value — a signal with sub-1.0 lift can be `risk`. See sprint-1 amendment 11.

**Cuts**: by org unit, by stage, S0 vs each signal.

**Sensitivity**: a small grid over N, M, K; reported, not tuned on.

**Outputs** under `out/<corpus>/`, committed:

- `signals.csv` — the metrics table
- `rows.csv` — every row with all `first_fired_at` values and outcome
- `by_org.csv`, `by_stage.csv`

## 9. Register (live view)

`register --milestone <id>` runs every signal on `snapshot(now)` and prints
one line per item with the signals firing, each annotated with its backtest
precision and `lead_class`. Split into two sections by `lead_class`: risk and
status.
Requires a completed backtest for the same corpus.

## 10. The finding

`README.md` is the finding. Order:

1. Headline — one paragraph: which signals predicted slips, lift, lead.
2. Three hypotheses, tested — verdict and number for each; the failure gets
   equal space.
3. The signal table with CIs.
4. Cuts — by SIG, by stage, S0 vs yours.
5. What the program should change — recommendations tied to rows above.
6. Limits — no *why*; no intervention effect; one governance model; label
   rule uncertainty; sample size.
7. Method, briefly — links to this spec, `LABELING.md`, the study guide.
8. Appendix: the tool — run it, add an adapter.

## 11. Repository

```
README.md                 the finding
docs/
  TPM_StudyGuide.md
  finding-gitlab.md       sprint 5
  adapters/gitlab.md      §6 of this spec, expanded, until built
  superpowers/specs/
core/                     model.py, store.py (SQLite), replay.py (snapshot)
adapters/k8s/             fetch.py, events.py, milestones.py, org_units.py, extract_deps.py, LABELING.md, config.py
adapters/gitlab/          sprint 4
signals/                  one module per signal; registry
backtest/                 run.py, metrics.py
cli.py                    fetch · build · backtest · register
tests/                    conformance/, signals/, backtest/
out/<corpus>/             committed CSVs
cache/<corpus>/           gitignored except llm/
```

Stack: Python 3.12, SQLite via stdlib, pandas for snapshots and metrics,
PyYAML, `requests` for the GitHub API with a token from env, an LLM client
isolated to `adapters/*/extract_*.py`. DuckDB is the swap if analysis queries
get slow. FastMCP for the wrapper in sprint 5. `pytest`.

## 12. Sequence

| Sprint | Build | Author judgment |
|---|---|---|
| 0 | Spike: clone `enhancements`, dump every `kep.yaml` at HEAD to `out/k8s/spike.json`. | Reading list (study guide §2). Revise §5 of this spec. |
| 1 | `core/`, `snapshot()`, K8s events from git history, milestones, org units, conformance tests, S1 S5 S7, first backtest run. | Calendar source. Slip rule from yaml alone. Read the first numbers. |
| 2 | Tracking-issue events → S0, `activity`. Labeling rule v2. Exceptions if findable. S2 S3 S6. Sensitivity grid. Cuts. | Source precedence. A priori `params`, written down. |
| 3 | Dependency extraction → S4a/b. Retro spot-check. **Draft finding.** | Read retros. Write the headline. |
| 4 | GitLab adapter, conformance, backtest run. | Comparable groups and milestones. |
| 5 | GitLab finding, cross-corpus comparison, `register`, MCP wrapper, README polish. Buffer. | Recommendations. |

Fallback: if sprints 4–5 slip, the K8s finding ships alone with
`docs/adapters/gitlab.md` as the documented next step.

## 13. Non-goals and stated limits

- The backtest does not explain *why* an item slipped. Retrospectives do.
- It does not measure whether acting on a signal improves delivery; that
  requires intervention and is confounded even inside an org.
- It does not model capacity for Kubernetes; there is none. Throughput (S6)
  is the honest proxy.
- Generality is claimed only to the extent a second adapter passes
  conformance and produces a finding.

## 14. Open questions, resolved in sprint 0

1. Where the release calendar lives and whether it is parseable.
2. Whether exception requests are structured enough to label.
3. Whether SIGs update `milestone.*` on a miss.
4. How KEP READMEs phrase dependencies — pattern or LLM.
5. What the cheapest honest definition of `activity` is.
6. Which cycles are comparable.

## Amendments (planning, 2026-08-26)

Found by fetching real files from the K8s repos while writing the sprint 0–1
plan. These override the corresponding lines in §3–§5 above.

1. **PRR approvers are not in `kep.yaml`.** They live in
   `keps/prod-readiness/<sig>/<kep-number>.yaml` as
   `{alpha: {approver: "@x"}, beta: {...}, stable: {...}}`. The adapter diffs
   that file's history into `owner_changed` events with `role = prr_approver`
   and a `stage` payload field.
2. **Exception requests are structured.** `releases/release-1.N/exceptions.yaml`
   in `kubernetes/sig-release` (present back to at least 1.26) lists
   `enhancementFreeze:` and `codeFreeze:` requests with `issue` (= KEP number),
   `date_requested`, `date_reviewed`, `status`. The `exception_granted` /
   `exception_denied` outcomes are derivable; §5's `[verify in spike]` on this
   point is resolved.
3. **The release calendar is a markdown table** in
   `releases/release-1.N/README.md` with stable row names (`Start of Release
   Cycle`, `Begin [Enhancements Freeze]`, `Begin [Code Freeze]`, `v1.N.0
   released`) and free-text dates. The adapter parses it into a committed,
   hand-verified `adapters/k8s/calendar.yaml`, which is the source of truth.
4. **Two freezes.** `Milestone.freeze` is **code freeze** — the delivery
   deadline lead time is measured against. `Milestone.dates["enhancements_freeze"]`
   is the commitment point; backtest rows are the targets present in the
   snapshot at enhancements freeze. Weekly snapshots run from cycle start to
   code freeze.
5. **`snapshot()` returns `dict[item_id, ItemState]`**, not a DataFrame.
   Signals read `ItemState` fields; pandas is used only in backtest metrics.
6. **Adapter contract gains `work_items()`.** Five calls, not four; conformance
   check 1 needs the item list.
7. **Sprint-1 activity has no actor.** Git author emails do not map to GitHub
   handles reliably, so sprint-1 `activity` events carry `actor_id =
   k8s:unknown` and S1 fires on "no activity from anyone in N weeks". Sprint 2
   replaces this with tracking-issue commenters and PR authors from the API.
8. Tracking-issue labels confirmed for sprint 2: `tracked/yes|no|out-of-tree`,
   `stage/alpha|beta|stable`, `lead-opted-in`, `sig/*`.

## Amendments (sprint 1, 2026-08-26)

Found by building the corpus and running the first backtest. These override
the corresponding lines in §3–§5 and §8 above; the planning amendments stand
unless contradicted here. Every number below is measured on the clone of
`kubernetes/enhancements` used for the run, not estimated.

1. **`kep.yaml` history begins 2020-03-17.** The first `kep.yaml` added on
   first-parent `main` is dated 2020-03-17; 104 were added during 2020 and
   none earlier (the KEP process before that lived in freeform markdown).
   This, not calendar parsing, is why milestones before v1.19 can never
   produce backtest rows: their enhancements freezes predate the data
   entirely. It also bounds the earliest usable cycle — v1.19's enhancements
   freeze is 2020-05-19, roughly two months after the corpus starts, so its
   snapshots see a partially-populated repository (15 rows, versus 60–90 for
   a mature cycle). §8's "most recent ~8 releases" is superseded: all 19
   scheduled milestones (v1.19–v1.37) are backtested, and comparability is
   reported as a cut rather than imposed as a filter.

2. **Item ids must derive from `kep-number`, not the directory prefix, and
   the mapping is not injective.** §5's `work_item` row ("one per `kep.yaml`;
   id `k8s:kep-NNNN`") is right about the id and wrong to assume it falls out
   of the path. Three distinct failure modes on the real corpus:
   - Four directories declare `kep-number: 0` — `sig-architecture/0000-kep-process`,
     `sig-contributor-experience/0000-community-forum`,
     `sig-release/0000-anago-to-krel-migration`,
     `sig-cloud-provider/providers/0000-cloud-provider-template`. These are
     process documents, not enhancements; they are excluded, counted, and
     printed by `cli.py build`.
   - `sig-cloud-provider/2133-out-of-tree-credential-provider` (status
     `replaced`) and `sig-node/2133-kubelet-credential-providers` (status
     `implemented`) are the *same* KEP either side of a SIG move. Merging the
     two directories' histories into one stream produced a status transition
     into `replaced` and hence a fabricated `dropped` label on a KEP that is
     alive and implemented. The adapter keeps one directory per number and
     prints which one it dropped.
   - `sig-node/2043-pod-resource-concrete-assigments` declares
     `kep-number: 1884` and no `1884-*` directory exists anywhere in the repo,
     so the directory prefix and the declared number disagree with no third
     source to arbitrate. The declared number wins.

   Net: 649 directories → 644 work items.

3. **KEP directories nest deeper than two levels.** `keps/sig-*/NNNN-*/kep.yaml`
   matches 612 files; 37 more live one level deeper under a provider or group
   directory (e.g. `keps/sig-cloud-provider/azure/2328-ccm-instance-metadata/kep.yaml`),
   four of which carry milestone blocks and therefore produce real rows.
   Directory discovery is "contains a `kep.yaml` under `keps/sig-*`", not a
   fixed depth.

4. **Renames are real and must be followed; copies must not be.** 29 of the
   649 directories' `kep.yaml` files cross at least one rename in first-parent
   history — renumberings (`2144-clientgo-apply` → `2155-clientgo-apply`,
   `20200309-consistent-resource-versions-semantics` →
   `2523-…`), retitles (`3716-webhook-predicates` →
   `3716-admission-webhook-match-conditions`), and typo fixes
   (`2307-job-tracking-wihout-lingering-pods` → `…-without-…`). Dropping them
   truncates the item's history at the rename and dates its "creation" wrongly.
   But plain `git log --follow` also walks git's *copy* detections, and KEP
   authors routinely seed a new KEP from a sibling's file — on this corpus an
   unbounded follow walked `3257-cluster-trust-bundles` out into unrelated
   KEPs and terminated at `keps/NNNN-kep-template/kep.yaml`, inflating 7 real
   versions to 22 and dating the KEP to the template's birthday. The rule is:
   follow `R` status, stop at `C`.

5. **`status` is dirty and must be normalized, never switched on.** §3's
   "Adapter-normalized" note is load-bearing, not decorative. Across the whole
   history the `status_changed` stream carries, besides the documented
   vocabulary: `imlpemented`, `implementeable` (×3), `implemented (alpha)`
   (×2), `implemented (beta)` (×2), `alpha`, `removed`, `superseded`, and one
   KEP whose status is the template's pasted pipe-separated enum list
   (`provisional|implementable|implemented|deferred|rejected|withdrawn|replaced`).
   `superseded` is a genuine drop and is in the drop-status set.
   **`removed` is not.** `sig-node/281-dynamic-kubelet-configuration` shipped
   alpha in v1.8 and beta in v1.11; its status records the *feature's* later
   removal from Kubernetes, years after the deliverables it is being scored on
   landed. Treating it as a drop would relabel a historical success as a
   failure. See `adapters/k8s/LABELING.md`, which is normative on this.

6. **A retracted milestone stage is observable and must emit an event.**
   §3's `target_set` row assumed targets only move forward. They also
   disappear: a KEP deletes `stable: v1.31` from its `milestone` block while
   keeping `alpha: v1.27`, recording that the future commitment was withdrawn
   (real example: `sig-storage/3476-volume-group-snapshot`). 71 such
   retractions occur across 50 items. Without an explicit event the stale
   target simply persists in every later snapshot and the row is labeled
   `shipped`. The adapter emits a `target_set` with `payload.op == "clear"`;
   `LABELING.md` rule 2 consumes it as evidence of a drop, and rule 1
   explicitly excludes it from the slip check so that a clear-then-retarget
   is scored as a slip rather than a drop.

7. **`exceptions.yaml` has two schemas plus one unrecoverable file.** Planning
   amendment 2 described only the modern schema. Files before v1.24 are a
   single flat top-level list with the freeze phase recorded only in a
   free-text header comment — never as structured data — so requests recovered
   from them carry `phase = "unspecified"` rather than a phase guessed from
   prose. release-1.23 additionally fails to parse solely because U+200B
   zero-width spaces contaminate its header comments; stripping them is data
   cleaning, not a heuristic. Recovering v1.21, v1.22 and v1.23 added 40
   requests — over the scheduled range v1.19–v1.37, 121 → 161. release-1.20's
   file is genuinely malformed (a block-mapping error surviving ZWSP
   stripping) and contributes zero; v1.20 is therefore the one milestone in
   range whose exception data is *known-missing* rather than known-absent, and
   `load_exceptions` surfaces it as a `SkippedExceptionsFile` so it is never
   silently invisible.

8. **Release README timelines vary by era; three files have no year at all.**
   Planning amendment 3 said the calendar is "a markdown table with free-text
   dates". Only v1.24 and later use the modern format. v1.19–v1.23 use
   month-first dates with abbreviated weekdays, including the non-standard
   `Thur`, and the READMEs for v1.19, v1.21 and v1.22 contain **no year
   anywhere in the file**. The year for those three cycles is a hand-verified
   constant in `adapters/k8s/calendar.yaml`, not a value inferred from the
   document. `calendar.yaml` is committed and is the source of truth; the
   parser exists to regenerate a candidate for a human to check, not to be
   trusted at runtime.

9. **Org attribution is point-in-time and inherits the source's typos.** A
   row's `org_id` is the owning SIG in the snapshot at enhancements freeze,
   taken verbatim from `kep.yaml`, and is not validated against `sigs.yaml`.
   `sig-api-machinery/4346-informer-metrics` declared `owning-sig:
   api-machinery` (no `sig-` prefix) from 2024-02-08 and fixed it on
   2024-02-12 — three days *after* v1.30's enhancements freeze. Its row is
   therefore attributed to `k8s:api-machinery`, an org unit that does not
   exist in `sigs.yaml`, and `out/k8s/by_org.csv` has a one-row group for it.
   This is the correct point-in-time answer and the wrong org; a
   `by_org` consumer must treat unmatched org ids as a data-quality signal
   rather than a SIG.

10. **`exception_denied` is unreachable under §5's precedence order.** Over
    v1.19–v1.37 the recovered `exceptions.yaml` files hold 161 requests: 128
    approved, 33 not approved. Fifteen of the 33 correspond to an actual
    backtest row, and every one of those fifteen is labeled `slipped`, because
    the labeling rule evaluates slip (rule 1) before denied-exception (rule 3).
    That ordering is not accidental — a SIG refused an exception has to
    retarget, which *is* a slip — but it means `exception_denied` can never
    fire for the population it was written to describe, and the first backtest
    reports 0 of them. §5's precedence must either be reordered in labeling v2
    so an exception decision outranks the retarget it caused, or the label must
    be removed and the reason stated. It is not a data gap.

11. **`signals.csv`'s `class` column is renamed `lead_class`.** §8 defines it on
    median lead alone (`risk` if median lead ≥ L else `status`) and the
    implementation is faithful to that, but the name invites reading it as a
    verdict on whether the signal predicts anything. It does not: on the first
    backtest `late_target` has lift 0.822 — its whole CI below 1.0, i.e.
    negatively predictive — and still classes as `risk`, because it fires a
    median 5.3 weeks out. Naming the column `lead_class` keeps the definition
    §8 chose and removes the conflation; predictive value is the `lift` column
    and its CI, and the two must be read together. `register` (§9) splits on
    `lead_class` for the same reason. Renamed rather than gated on `lift > 1`,
    because the column genuinely describes lead time and a lead-time fact about
    a non-predictive signal is still a fact worth reporting.

12. **`by_stage.csv` is specified in §8's committed outputs but is not produced
    in sprint 1.** `signals.csv`, `rows.csv` and `by_org.csv` are written;
    `by_stage.csv` is not. The by-stage cut itself was computed and is reported
    in `docs/sprint-1-notes.md` (alpha 0.299 / beta 0.324 / stable 0.290, flat),
    so the analysis is not missing — only the committed artifact is. It is a
    one-line `groupby` on `rows.csv` and is queued for sprint 2 alongside S2,
    S3 and S6. Recorded here because every other deviation from the spec is
    recorded here, and an output listed as committed that no command produces
    should not be discoverable only by running `ls`.

13. **`out/k8s/spike.json` is deleted and is no longer committed.** It was the
    sprint-0 spike's raw dump of every parsed `kep.yaml` (320KB). It is not in
    §8's committed-artifacts list, it is fully regenerable with `cli.py spike`,
    and it had gone stale: it keys rows by *directory name*, which amendment 2
    superseded when item ids moved to `kep-number`, so it disagrees with
    `rows.csv` about the identity of the corpus. A stale, uncited, regenerable
    artifact that contradicts a current one is a liability rather than a
    record. Deleted, and added to `.gitignore` so a later `cli.py spike` run
    does not silently re-commit it. Nothing reads it: the spike's *findings*
    live in the planning amendments and in `calendar.yaml`, both of which are
    committed and current.
