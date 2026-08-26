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
rate), median lead in weeks with IQR, class (`risk` if median lead ≥ L else
`status`). Bootstrap 95% CIs on precision and lift by resampling rows.

**Cuts**: by org unit, by stage, S0 vs each signal.

**Sensitivity**: a small grid over N, M, K; reported, not tuned on.

**Outputs** under `out/<corpus>/`, committed:

- `signals.csv` — the metrics table
- `rows.csv` — every row with all `first_fired_at` values and outcome
- `by_org.csv`, `by_stage.csv`

## 9. Register (live view)

`register --milestone <id>` runs every signal on `snapshot(now)` and prints
one line per item with the signals firing, each annotated with its backtest
precision and class. Split into two sections by class: risk and status.
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
