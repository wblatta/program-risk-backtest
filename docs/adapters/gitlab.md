# GitLab adapter — mapping, and why it is not built

Spec §11 lists this file as the deliverable that stands in for `adapters/gitlab/` "until
built", and §12's fallback anticipates exactly this outcome: *"if sprints 4–5 slip, the K8s
finding ships alone with `docs/adapters/gitlab.md` as the documented next step."*

This is that document. The adapter is **blocked on a credential, not on design.**

## The blocker

GitLab requires authentication for the endpoints this adapter's spine depends on, on every
public project. Measured 2026-09-02, unauthenticated, against `gitlab-org/gitlab` (278964),
`gitlab-org/gitlab-runner` (250833) and one other public project:

| endpoint | status | needed for |
|---|---|---|
| `/projects/:id/issues` | **200** | `work_item` |
| `/projects/:id/repository/tags` | **200** | — |
| `/projects/:id/milestones` | **401** | `milestone` |
| `/projects/:id/issues/:iid/resource_milestone_events` | **401** | **`target_set`** |
| `/projects/:id/releases` | **403** | milestone dates |
| `/groups/:id/milestones` | **401** | group-level `milestone` |

Issues are readable and carry an embedded `milestone` object with `title` and `due_date`,
so the milestone *catalog* can be reconstructed without the milestones endpoint.

**`resource_milestone_events` cannot be.** That endpoint is the timestamped history of
which milestone an issue was assigned to and when. Without it there is only the issue's
*current* milestone — a fact about today, not about any past date.

That is fatal, and fatal quietly, which is why it stops the work rather than degrading it.
This project rests entirely on `snapshot(as_of)`: reconstructing what the roadmap said on a
past date. With only current milestones, every `target_set` event would carry a fabricated
timestamp. `prior_slip` and `late_target` would be unmeasurable, the retarget-based outcome
rule would have nothing to read, and the leakage boundary — the one property the whole
design exists to protect — would be violated by construction. The pipeline would still run.
It would still emit CSVs. The numbers would be wrong in a way no internal check could catch,
because every internal check compares the corpus against itself.

## What unblocks it

A GitLab personal access token with the `read_api` scope, in `GITLAB_TOKEN`. Free-tier
accounts can issue one; the endpoints above are not paid features, they are simply
authenticated. `adapters/k8s/github.py` is the model for the client: rate-limit reserve,
ETag conditional requests, `Retry-After` handling, and pagination that follows
`Link: rel="next"` — GitLab paginates by `X-Next-Page` instead, which is the one
substantive difference.

## Mapping (spec §6, expanded)

| normalized | GitLab source | notes |
|---|---|---|
| `work_item` | issues with weight, or epics, in selected `gitlab-org` groups | readable unauthenticated |
| `org_unit` | stage groups from the handbook (`data/stages.yml`) | plain file in a public repo |
| `milestone` | milestones API; monthly releases | 401; reconstructable from issues' embedded milestone |
| `target_set` | `resource_milestone_events` | **401 — the blocker** |
| `status_changed` | `resource_label_events` (`workflow::*`) and state events | 401 |
| `owner_changed` | assignee events; group from labels | 401 for the event history |
| `dependency_changed` | issue links API (`blocks`) | **typed**, unlike anything in the K8s corpus |
| `activity` | notes and MR events by assignees | notes are readable; author logins present |
| `outcome` | milestone at close vs milestone at freeze; `missed:*` labels | needs milestone history |

### Two things GitLab has that Kubernetes does not

**Typed dependencies.** The issue-links API records `blocks` / `is_blocked_by` explicitly.
The K8s corpus has no such thing — sprint 3 measured that only 18% of KEP READMEs reference
a sibling at all, and none of those references carry a relation type, which is why H2 is
untested rather than answered. GitLab is the corpus that could settle H2, and that is the
strongest single argument for building this adapter.

**Capacity.** Issue weight and group headcount are recorded, so `org_unit_capacity` becomes
possible and `org_overcommitted` (S6) can load against real capacity instead of the
throughput proxy Kubernetes forces. S6 is null on the K8s corpus; that may be the proxy's
fault rather than the hypothesis's, and this is how you would find out.

Per spec §6, the `org_unit_capacity` table is added **when this adapter lands, not before.**

## Conformance

The shared suite in `tests/conformance/` is corpus-agnostic and is what any new adapter
must pass — six checks, of which two bear directly on the blocker above:

2. No `outcome` precedes its item's first event; no `outcome` precedes its milestone's freeze.
3. For each milestone, `snapshot(freeze)` contains at least one item targeted at it.

Check 3 is the one a fabricated `target_set` timestamp would fail, if the fabrication were
honest about itself, and pass if it were not. It is not a substitute for having the real
history.

## Status

Not started. No `adapters/gitlab/` package exists, and none should be written against
inaccessible endpoints — a fetch layer that cannot be run against the real API is a guess
with tests around it.

The K8s finding ships alone, which is the fallback the spec provided for.

---

## Superseded: the second corpus should be on GitHub

GitLab was set aside in favour of another GitHub project, for two reasons that have
nothing to do with the 401s above.

**A second corpus is a proxy either way.** GitLab is not related to Kubernetes, and
running the pipeline on it would not validate the Kubernetes finding — it would test
whether the *method* survives contact with different data. Any second corpus does that
equally well, and the spec is deliberately modest about the claim: generality is asserted
"only to the extent a second adapter passes conformance and produces a finding."

**GitHub already supplies the one endpoint GitLab withholds.** The timeline API carries
`milestoned` / `demilestoned` events with `created_at` and the milestone title — the same
point-in-time target history `resource_milestone_events` would have given. The rate-limited
client in `adapters/k8s/github.py` already handles it, and no new credential is needed.

What GitLab uniquely offered was **typed dependency edges** (`blocks` / `is_blocked_by`),
which would have made H2 testable. That is a real loss and it is recorded as such: H2 stays
open, because neither KEP prose nor GitHub cross-references carry a relation type. Answering
H2 on GitLab would have answered it *for GitLab* — it could never have answered it here.

Candidate selection for the GitHub corpus is measured rather than assumed, by
`tools/corpus_survey.py`. The decisive property is retargeting: a `slipped` outcome exists
only because work is moved between releases and leaves a timestamped trace, and a repo
without it has no positive class to predict.
