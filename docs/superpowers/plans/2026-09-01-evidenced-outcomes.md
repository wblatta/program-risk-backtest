# Evidenced Outcomes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fallthrough `shipped` label with one that requires positive delivery evidence, add `unresolved` for rows where no evidence exists, and publish every result as two labelled cuts so the difference between "hygiene held" and "hygiene did not" is itself reportable.

**Architecture:** A new `adapters/k8s/delivery.py` reads the already-cached tracking issues and PR cross-references and answers one question per row — is there evidence this landed. `outcome_events()` consumes it exactly the way it already consumes `exceptions`, so the labeler gains an input rather than a dependency on the network. `cli.py backtest` then emits each output twice, once per cut.

**Tech Stack:** Python 3.12+, stdlib `json`/`datetime`, `pandas` for metrics, `pytest`. No new dependencies. No network calls — all data is on disk under `cache/k8s/github/`.

**Spec:** `docs/superpowers/specs/2026-09-01-evidenced-outcomes-design.md`

## Global Constraints

- Python 3.12+. Dependencies limited to `pyyaml`, `pandas` (<3), `numpy`, `pytest`.
- All timestamps are timezone-aware UTC `datetime`; all calendar dates are `date`.
- Outcome events use `source = "derived"` and `ts = M.release`.
- `snapshot()` never reads outcome events; outcomes join only where `outcome.ts > freeze_dt`. **No task in this plan may weaken that.**
- `adapters/k8s/LABELING.md` is normative: the doc states the rule, the code implements it, and any change to one requires the same change to the other in the same commit.
- `POSITIVE = {"slipped", "dropped", "exception_denied"}` is unchanged. `unresolved` is neither positive nor negative.
- Signals return `set[tuple[str, str]]` — `(item_id, stage)`. Do not reintroduce an item-scoped return.
- Output must be deterministic — byte-identical across runs.
- `out/k8s/*.csv` are committed; `cache/` is gitignored.
- Commit after every task with a conventional message.

## Corpus facts (measured, do not re-derive)

- 1,255 rows: shipped 811, slipped 370, exception_granted 65, dropped 9, exception_denied 0.
- `cache/k8s/github/issues/<n>.json` and `cache/k8s/github/timeline/<n>.json` exist for all 644 KEPs; `<n>` is the KEP number.
- 938 `kubernetes/kubernetes` PR cross-references across the timelines, each with `merged_at` (720 non-null, across 306 KEPs).
- Evidence rates: closure 21.6% of shipped / 0.8% of slipped; merge 24.0% / 6.5%; union 43.4% / 7.0%.
- Union coverage by stage: `alpha` 48.2%, `beta` 22.2%, `stable` 58.5%.

## File structure

```
adapters/k8s/delivery.py      NEW  DeliveryEvidence, load_delivery_evidence(), has_evidence()
adapters/k8s/outcomes.py      MOD  outcome_events() gains `delivery` param; rule 5 split into shipped/unresolved
adapters/k8s/LABELING.md      MOD  rule 5 replaced, rule 6 added, evidence model documented
backtest/run.py               MOD  POSITIVE unchanged; add UNRESOLVED constant
backtest/metrics.py           MOD  signal_metrics()/by_org() gain a `cut` label column
cli.py                        MOD  backtest emits both cuts
tests/k8s/test_delivery.py    NEW
tests/k8s/test_outcomes.py    MOD  new rule-5/6 cases
tests/backtest/test_metrics.py MOD  cut labelling
```

---

### Task 1: Delivery evidence from cached tracking data

**Files:**
- Create: `adapters/k8s/delivery.py`
- Test: `tests/k8s/test_delivery.py`

**Interfaces:**
- Produces: `DeliveryEvidence(closed_at: datetime | None, merges: tuple[datetime, ...])` frozen dataclass; `load_delivery_evidence(github_cache: Path) -> dict[int, DeliveryEvidence]` keyed by KEP number; `has_evidence(ev: DeliveryEvidence | None, cycle_start: date, release: date, closure_days: int = 90) -> str | None` returning `"closure"`, `"merge"`, or `None`.
- Consumes: nothing from other tasks. Reads JSON off disk only.

- [ ] **Step 1: Write the failing tests**

```python
# tests/k8s/test_delivery.py
"""Delivery evidence: did the code actually land? Reads cached GitHub JSON only."""
import json
from datetime import date, datetime, timezone
import pytest
from adapters.k8s.delivery import DeliveryEvidence, load_delivery_evidence, has_evidence

UTC = timezone.utc
START, RELEASE = date(2024, 5, 13), date(2024, 8, 13)


def _write(tmp_path, n, issue, timeline):
    (tmp_path / "issues").mkdir(parents=True, exist_ok=True)
    (tmp_path / "timeline").mkdir(parents=True, exist_ok=True)
    (tmp_path / "issues" / f"{n}.json").write_text(json.dumps(issue))
    (tmp_path / "timeline" / f"{n}.json").write_text(json.dumps(timeline))


def xref(repo, merged_at, number=1):
    return {"event": "cross-referenced", "created_at": "2024-06-01T00:00:00Z",
            "source": {"issue": {"number": number, "repository": {"full_name": repo},
                                 "pull_request": {"merged_at": merged_at}}}}


def test_loads_closure_and_merge_timestamps(tmp_path):
    _write(tmp_path, 7, {"number": 7, "closed_at": "2024-09-01T00:00:00Z"},
           [xref("kubernetes/kubernetes", "2024-06-15T00:00:00Z")])
    got = load_delivery_evidence(tmp_path)
    assert got[7] == DeliveryEvidence(closed_at=datetime(2024, 9, 1, tzinfo=UTC),
                                      merges=(datetime(2024, 6, 15, tzinfo=UTC),))


def test_ignores_prs_from_other_repositories(tmp_path):
    """Only kubernetes/kubernetes merges count as implementation evidence."""
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/website", "2024-06-15T00:00:00Z"),
            xref("kubernetes/enhancements", "2024-06-16T00:00:00Z")])
    assert load_delivery_evidence(tmp_path)[7].merges == ()


def test_ignores_unmerged_pull_requests(tmp_path):
    """A closed-but-unmerged PR is not evidence anything landed."""
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/kubernetes", None)])
    assert load_delivery_evidence(tmp_path)[7].merges == ()


def test_merges_are_sorted_for_determinism(tmp_path):
    _write(tmp_path, 7, {"number": 7, "closed_at": None},
           [xref("kubernetes/kubernetes", "2024-07-01T00:00:00Z", 2),
            xref("kubernetes/kubernetes", "2024-06-01T00:00:00Z", 1)])
    m = load_delivery_evidence(tmp_path)[7].merges
    assert m == tuple(sorted(m))


def test_has_evidence_reports_closure_within_the_window():
    ev = DeliveryEvidence(closed_at=datetime(2024, 10, 1, tzinfo=UTC), merges=())
    assert has_evidence(ev, START, RELEASE) == "closure"


def test_has_evidence_rejects_closure_beyond_the_window():
    """Closure 200 days after release says nothing about this milestone."""
    ev = DeliveryEvidence(closed_at=datetime(2025, 3, 1, tzinfo=UTC), merges=())
    assert has_evidence(ev, START, RELEASE) is None


def test_has_evidence_reports_a_merge_inside_the_cycle():
    ev = DeliveryEvidence(closed_at=None, merges=(datetime(2024, 6, 15, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) == "merge"


def test_has_evidence_rejects_a_merge_before_the_cycle_opened():
    """A merge predating the cycle belongs to earlier work, not this commitment."""
    ev = DeliveryEvidence(closed_at=None, merges=(datetime(2024, 1, 1, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) is None


def test_closure_takes_precedence_over_merge_when_both_hold():
    ev = DeliveryEvidence(closed_at=datetime(2024, 9, 1, tzinfo=UTC),
                          merges=(datetime(2024, 6, 15, tzinfo=UTC),))
    assert has_evidence(ev, START, RELEASE) == "closure"


def test_missing_evidence_record_is_not_an_error():
    assert has_evidence(None, START, RELEASE) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_delivery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adapters.k8s.delivery'`

- [ ] **Step 3: Implement**

```python
# adapters/k8s/delivery.py
"""Did the code actually land? Evidence from cached tracking issues and PR cross-refs.

Two independent sources, measured complementary rather than redundant (intersection
2.2%, inverse stage profiles):

  closure  the KEP's tracking issue closed within `closure_days` of the release.
           Present on 21.6% of shipped rows and 0.8% of slipped ones. A tracking
           issue spans a KEP's whole lifecycle, so this is evidence about the
           FINAL stage -- 53.9% of `stable` rows, under 5% of alpha and beta.
  merge    a kubernetes/kubernetes PR cross-referenced from the tracking issue
           merged between cycle start and release. 24.0% vs 6.5%. Implementation
           PRs cluster at first delivery, so this is evidence about the FIRST
           stage -- 45.5% of `alpha`, 10.2% of `stable`.

Deliberately NOT used: the release team's `tracked/yes` label. It appears on 51.8%
of shipped rows and 40.0% of slipped ones -- it records that the team was tracking
the work and is not removed when the work fails.

Reads only from `cache/k8s/github/`, populated by `cli.py fetch-issues`. No network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

IMPL_REPO = "kubernetes/kubernetes"


@dataclass(frozen=True)
class DeliveryEvidence:
    closed_at: datetime | None
    merges: tuple[datetime, ...]


def _ts(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _merges(timeline) -> tuple[datetime, ...]:
    out = []
    for e in timeline or []:
        if not isinstance(e, dict) or e.get("event") != "cross-referenced":
            continue
        src = (e.get("source") or {}).get("issue") or {}
        if (src.get("repository") or {}).get("full_name") != IMPL_REPO:
            continue
        merged = _ts((src.get("pull_request") or {}).get("merged_at"))
        if merged:
            out.append(merged)
    return tuple(sorted(out))


def load_delivery_evidence(github_cache: Path) -> dict[int, DeliveryEvidence]:
    """Read every cached issue + timeline into evidence records keyed by KEP number."""
    github_cache = Path(github_cache)
    out: dict[int, DeliveryEvidence] = {}
    for p in sorted((github_cache / "issues").glob("*.json")):
        try:
            n = int(p.stem)
            issue = json.loads(p.read_text())
        except (ValueError, OSError):
            continue
        tp = github_cache / "timeline" / f"{n}.json"
        try:
            timeline = json.loads(tp.read_text()) if tp.exists() else []
        except (ValueError, OSError):
            timeline = []
        out[n] = DeliveryEvidence(closed_at=_ts(issue.get("closed_at")),
                                  merges=_merges(timeline))
    return out


def _eod(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def has_evidence(ev: DeliveryEvidence | None, cycle_start: date, release: date,
                 closure_days: int = 90) -> str | None:
    """Which evidence supports delivery at this milestone, if any.

    Returns "closure", "merge", or None. Closure is checked first because it has the
    lower false-positive rate (0.8% vs 6.5%), so when both hold the stronger source
    is the one recorded.
    """
    if ev is None:
        return None
    if ev.closed_at is not None and ev.closed_at <= _eod(release) + timedelta(days=closure_days):
        return "closure"
    lo, hi = _eod(cycle_start), _eod(release)
    if any(lo <= m <= hi for m in ev.merges):
        return "merge"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_delivery.py -v`
Expected: 10 PASS

- [ ] **Step 5: Sanity-check against the real cache**

Run:
```bash
.venv/bin/python -c "
from pathlib import Path
from adapters.k8s.delivery import load_delivery_evidence
d = load_delivery_evidence(Path('cache/k8s/github'))
print(len(d), 'records;', sum(1 for v in d.values() if v.merges), 'with merges;', sum(1 for v in d.values() if v.closed_at), 'closed')"
```
Expected: `644 records; 306 with merges; 458 closed`. Report any deviation rather than adjusting the code to match.

- [ ] **Step 6: Commit**

```bash
git add adapters/k8s/delivery.py tests/k8s/test_delivery.py
git commit -m "feat(k8s): delivery evidence from cached tracking issues and PR merges"
```

---

### Task 2: `shipped` requires evidence; `unresolved` is new

**Files:**
- Modify: `adapters/k8s/outcomes.py`
- Modify: `adapters/k8s/LABELING.md`
- Test: `tests/k8s/test_outcomes.py`

**Interfaces:**
- Consumes: `DeliveryEvidence`, `has_evidence` from Task 1.
- Produces: `outcome_events(events, milestones, exceptions, today, delivery=None)` — the new fifth parameter is `dict[int, DeliveryEvidence] | None`, defaulting to `None` so existing callers keep working. Outcome payloads gain an `evidence` key: `"closure"`, `"merge"`, or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/k8s/test_outcomes.py`:

```python
from adapters.k8s.delivery import DeliveryEvidence


def test_shipped_requires_delivery_evidence():
    """The v1 fallthrough is gone: no evidence means unresolved, not shipped."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    r = results(outcome_events(evs, MS, {}, TODAY, delivery={}))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "unresolved"


def test_closure_evidence_yields_shipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


def test_merge_evidence_yields_shipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=None, merges=(T(2024, 6, 15),))}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"


def test_evidence_kind_is_recorded_on_the_event():
    """Every shipped row must be able to name why it was called shipped."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    out = [e for e in outcome_events(evs, MS, {}, TODAY, delivery=d)
           if e.payload["milestone_id"] == "k8s:v1.31"]
    assert out[0].payload["evidence"] == "closure"


def test_unresolved_rows_carry_no_evidence_key_value():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    out = [e for e in outcome_events(evs, MS, {}, TODAY, delivery={})
           if e.payload["milestone_id"] == "k8s:v1.31"]
    assert out[0].payload["evidence"] is None


def test_evidence_does_not_override_slipped():
    """Precedence is unchanged: a retarget outranks any delivery evidence."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 7, 20), "alpha", "k8s:v1.32")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"


def test_evidence_does_not_override_dropped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "withdrawn")]
    d = {1: DeliveryEvidence(closed_at=T(2024, 9, 1), merges=())}
    r = results(outcome_events(evs, MS, {}, TODAY, delivery=d))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"


def test_omitting_delivery_keeps_the_v1_behaviour():
    """delivery=None is the pre-existing contract: shipped remains the fallthrough."""
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    r = results(outcome_events(evs, MS, {}, TODAY))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_outcomes.py -v -k "evidence or unresolved or v1_behaviour"`
Expected: FAIL — `outcome_events() got an unexpected keyword argument 'delivery'`

- [ ] **Step 3: Add the parameter and split rule 5**

In `adapters/k8s/outcomes.py`, change the signature:

```python
def outcome_events(events: list[Event], milestones: list[Milestone],
                   exceptions: dict[str, list[ExceptionRequest]], today: date,
                   delivery: dict[int, "DeliveryEvidence"] | None = None) -> list[Event]:
```

Add the import at the top of the file:

```python
from adapters.k8s.delivery import DeliveryEvidence, has_evidence
```

Replace the rule-5 fallthrough. The existing tail reads:

```python
                        elif exc:
                            result = "exception_granted"
                        else:
                            result = "shipped"
```

Replace with:

```python
                        elif exc:
                            result = "exception_granted"
                        else:
                            # Rule 5/6. `shipped` is no longer the fallthrough: it
                            # requires positive evidence the code landed. Without it the
                            # outcome is UNKNOWN, not failed -- usually nobody linked the
                            # implementation back to the tracking issue.
                            evidence = None
                            if delivery is not None:
                                start = m.dates.get("start") or m.freeze
                                evidence = has_evidence(
                                    delivery.get(_kep_number(item_id)), start, m.release)
                            result = "shipped" if (delivery is None or evidence) else "unresolved"
```

Then thread `evidence` into the emitted payload. Find the `out.append(...)` call and add the key:

```python
                out.append(Event(_dt(m.release), item_id, K.OUTCOME,
                                 {"milestone_id": m.id, "stage": stage, "result": result,
                                  "evidence": evidence if result == "shipped" else None},
                                 SRC))
```

`evidence` must be initialised to `None` before the precedence chain so the payload key
always exists — set `evidence = None` immediately after `later = ...` is computed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_outcomes.py -v`
Expected: all PASS, including the pre-existing cases.

- [ ] **Step 5: Update LABELING.md**

The doc is normative and must change in this same commit. Replace the rule-5 entry with:

```markdown
5. **shipped** — positive evidence the code landed for this milestone:
   - the tracking issue closed within 90 days of the milestone's release, or
   - a `kubernetes/kubernetes` PR cross-referenced from that issue merged between
     cycle start and release.

   The evidence kind is recorded on the outcome event's `evidence` payload key, so
   every `shipped` row can name why it was called shipped.

6. **unresolved** — none of the above matched and no delivery evidence exists.

   **This is not a synonym for failure.** It means the outcome is unknown to this
   instrument. The usual cause is that nobody linked the implementation back to the
   tracking issue, not that the work stopped. Measured coverage: evidence exists for
   43.4% of rows that v1 called shipped, and for 7.0% of rows it called slipped.
   Coverage is uneven by stage — `alpha` 48.2%, `beta` 22.2%, `stable` 58.5% — because
   closure is evidence about a KEP's final stage and merges about its first.

   `unresolved` is neither positive nor negative. `POSITIVE` remains
   `{slipped, dropped, exception_denied}`.

**Deliberately not used as evidence:** the release team's `tracked/yes` label. It
appears on 51.8% of shipped rows and 40.0% of slipped ones — it records that the team
was tracking the work and is not removed when the work fails.
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -q -m "not integration"`
Expected: all pass. `delivery=None` keeps every existing caller on v1 behaviour, so nothing else should move yet.

- [ ] **Step 7: Commit**

```bash
git add adapters/k8s/outcomes.py adapters/k8s/LABELING.md tests/k8s/test_outcomes.py
git commit -m "feat(k8s): shipped requires delivery evidence; add unresolved"
```

---

### Task 3: Wire evidence into the adapter and measure the real corpus

**Files:**
- Modify: `adapters/k8s/adapter.py`
- Test: `tests/k8s/test_adapter.py`

**Interfaces:**
- Consumes: `load_delivery_evidence` from Task 1, `outcome_events(..., delivery=...)` from Task 2.
- Produces: `K8sAdapter.events()` passes delivery evidence when `cache/k8s/github/issues` exists, and leaves it `None` when it does not — so the adapter still works on a machine that has never run `fetch-issues`.

- [ ] **Step 1: Write the failing test**

Append to `tests/k8s/test_adapter.py`:

```python
def test_adapter_labels_unresolved_without_delivery_evidence(tmp_path):
    """With a github cache present but empty, a committed target with no evidence
    must come back `unresolved` rather than `shipped`."""
    from adapters.k8s.adapter import K8sAdapter
    from core.model import EventKind as K
    repo = _fixture_repo(tmp_path)          # existing helper in this file
    (tmp_path / "k8s" / "github" / "issues").mkdir(parents=True, exist_ok=True)
    (tmp_path / "k8s" / "github" / "timeline").mkdir(parents=True, exist_ok=True)
    a = K8sAdapter(tmp_path, today=date(2026, 1, 1))
    results = {e.payload["result"] for e in a.events() if e.kind == K.OUTCOME}
    assert "shipped" not in results
    assert "unresolved" in results
```

If `_fixture_repo` does not exist under that name in the file, use whatever fixture
helper the existing adapter tests use to build a cache directory, and keep the
assertion identical.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/k8s/test_adapter.py -v -k unresolved`
Expected: FAIL — the adapter still labels it `shipped`.

- [ ] **Step 3: Implement**

In `adapters/k8s/adapter.py`, inside `events()`, before the `outcome_events(...)` call:

```python
        gh = self.cache / "github"
        delivery = load_delivery_evidence(gh) if (gh / "issues").is_dir() else None
```

and pass it through:

```python
        outcomes = outcome_events(base, self.milestones(), exceptions, self.today,
                                  delivery=delivery)
```

Add the import at the top:

```python
from adapters.k8s.delivery import load_delivery_evidence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_adapter.py -v`
Expected: all PASS.

- [ ] **Step 5: Rebuild and report the real label distribution**

Run:
```bash
.venv/bin/python cli.py build
```
Report the new distribution across `shipped`/`unresolved`/`slipped`/`dropped`/`exception_granted`.
Expected shape, from the spec's measurements: roughly 352 `shipped`, roughly 459
`unresolved`, and `slipped`/`dropped`/`exception_granted` unchanged at 370/9/65.
**Report what you actually get; do not tune the window to hit these numbers.**

- [ ] **Step 6: Check the known-error floor**

The sprint-1 notes identified 69 `shipped` rows provably wrong from the corpus. Run:
```bash
.venv/bin/python - <<'EOF'
import re, yaml, collections
from pathlib import Path
from core.store import Store
from adapters.k8s.git_history import list_kep_dirs
s = Store(Path("cache/store.sqlite"))
repo = Path("cache/k8s/enhancements")
head = {}
for d in list_kep_dirs(repo):
    try: y = yaml.safe_load((repo / d / "kep.yaml").read_text()) or {}
    except Exception: continue
    n = y.get("kep-number")
    if isinstance(n, int) and n > 0:
        head[n] = {"status": str(y.get("status") or "").strip().lower(),
                   "latest": str(y.get("latest-milestone") or "")}
def mi(x):
    m = re.search(r"1\.(\d+)", str(x)); return int(m.group(1)) if m else None
IMPL = re.compile(r"^(implemented|imlpemented)\b")
c = collections.Counter()
for e in s.load_events("k8s"):
    if e.kind != "outcome": continue
    n = int(e.item_id.rsplit("-", 1)[1]); h = head.get(n)
    if not h: continue
    l, t = mi(h["latest"]), mi(e.payload["milestone_id"])
    if l is not None and t is not None and l < t and not IMPL.match(h["status"]):
        c[e.payload["result"]] += 1
print("known-wrong rows, by new label:", dict(c))
EOF
```
Success criterion from the spec: those rows should now be `unresolved`, not `shipped`.
**If any remain `shipped`, that is a finding about the evidence model — report it, do
not adjust the rule to hide it.**

- [ ] **Step 7: Commit**

```bash
git add adapters/k8s/adapter.py tests/k8s/test_adapter.py
git commit -m "feat(k8s): adapter supplies delivery evidence to the labeler"
```

---

### Task 4: Two cuts in the metrics

**Files:**
- Modify: `backtest/metrics.py`
- Modify: `backtest/run.py`
- Test: `tests/backtest/test_metrics.py`

**Interfaces:**
- Consumes: rows carrying `outcome == "unresolved"`.
- Produces: `UNRESOLVED = "unresolved"` in `backtest/run.py`; `signal_metrics(rows, milestones_by_id, L, n_boot=1000, seed=0, cut="evidenced")` where `cut` is `"evidenced"` (drop unresolved rows) or `"full"` (treat unresolved as negative), and the returned frame gains a leading `cut` column. `by_org(rows, cut="evidenced")` likewise.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest/test_metrics.py`:

```python
from backtest.run import Row, UNRESOLVED


def _rows():
    """Two rows a signal fired on: one a real positive, one unresolved."""
    return [Row("i1", "alpha", "x:v31", None, "slipped", {"s": T(5, 20)}),
            Row("i2", "alpha", "x:v31", None, "unresolved", {"s": T(5, 20)}),
            Row("i3", "alpha", "x:v31", None, "shipped", {"s": None})]


def test_evidenced_cut_excludes_unresolved_rows():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="evidenced")
    assert int(df["rows"].iloc[0]) == 2, "unresolved row must be dropped"
    assert df["cut"].iloc[0] == "evidenced"


def test_full_cut_counts_unresolved_as_negative():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="full")
    assert int(df["rows"].iloc[0]) == 3, "all rows retained"
    assert df["cut"].iloc[0] == "full"
    # base rate is 1 positive of 3 rows -- unresolved counted as not-positive
    assert abs(float(df["base_rate"].iloc[0]) - 1 / 3) < 1e-9


def test_cut_column_is_first_so_a_csv_always_says_which_it_is():
    df = signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="evidenced")
    assert list(df.columns)[0] == "cut"


def test_unknown_cut_is_rejected_rather_than_silently_defaulting():
    import pytest
    with pytest.raises(ValueError):
        signal_metrics(_rows(), {"x:v31": M31}, L=4, n_boot=10, cut="whatever")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/backtest/test_metrics.py -v -k cut`
Expected: FAIL — `signal_metrics() got an unexpected keyword argument 'cut'`

- [ ] **Step 3: Implement**

In `backtest/run.py`, next to `POSITIVE`:

```python
UNRESOLVED = "unresolved"   # neither positive nor negative; see adapters/k8s/LABELING.md
```

In `backtest/metrics.py`, add a helper and thread `cut` through both public functions:

```python
def _apply_cut(rows, cut: str):
    """Evidenced: drop rows whose outcome is unknown. Full: keep them, counted as
    not-positive. The two are published side by side because their difference is the
    finding -- what the signals are worth where process hygiene held, against where it
    did not."""
    if cut == "evidenced":
        return [r for r in rows if r.outcome != UNRESOLVED]
    if cut == "full":
        return list(rows)
    raise ValueError(f"unknown cut {cut!r}; expected 'evidenced' or 'full'")
```

`signal_metrics` and `by_org` each call `_apply_cut(rows, cut)` first, then proceed
unchanged, and insert `cut` as the first column of the returned frame:

```python
    df.insert(0, "cut", cut)
```

Import `UNRESOLVED` from `backtest.run` at the top of `metrics.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/backtest/test_metrics.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backtest/metrics.py backtest/run.py tests/backtest/test_metrics.py
git commit -m "feat(backtest): evidenced and full cuts in the metrics"
```

---

### Task 5: Emit both cuts, and report the comparison

**Files:**
- Modify: `cli.py`
- Create: `out/k8s/signals_full.csv`, `out/k8s/by_org_full.csv` (generated, committed)
- Modify: `out/k8s/signals.csv`, `out/k8s/rows.csv`, `out/k8s/by_org.csv` (regenerated)

**Interfaces:**
- Consumes: `signal_metrics(..., cut=...)` and `by_org(..., cut=...)` from Task 4.
- Produces: `cli.py backtest` writes `signals.csv`/`by_org.csv` for the evidenced cut and `signals_full.csv`/`by_org_full.csv` for the full cut, prints both tables, and prints the label distribution.

- [ ] **Step 1: Implement**

In `cmd_backtest`, replace the single-table block with:

```python
    out = OUT / "k8s"; out.mkdir(parents=True, exist_ok=True)
    by_id = {m.id: m for m in ms}
    rows_frame(rows).to_csv(out / "rows.csv", index=False)

    import collections
    dist = collections.Counter(r.outcome for r in rows)
    print(f"{len(rows)} rows | " + " ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))

    for cut, sig_name, org_name in (("evidenced", "signals.csv", "by_org.csv"),
                                    ("full", "signals_full.csv", "by_org_full.csv")):
        table = signal_metrics(rows, by_id, L=DEFAULT_PARAMS["L"], cut=cut)
        table.to_csv(out / sig_name, index=False)
        by_org(rows, cut=cut).to_csv(out / org_name, index=False)
        print(f"\n--- {cut} cut ---")
        print(table.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python cli.py backtest`
Expected: the label distribution, then two tables. Record both.

- [ ] **Step 3: Verify determinism**

Run:
```bash
md5 out/k8s/*.csv > /tmp/a && .venv/bin/python cli.py backtest >/dev/null && md5 out/k8s/*.csv > /tmp/b && diff /tmp/a /tmp/b && echo "deterministic"
```
Expected: `deterministic`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass, including the integration conformance test.

- [ ] **Step 5: Commit**

```bash
git add cli.py out/k8s/
git commit -m "feat(cli): publish evidenced and full cuts side by side"
```

---

### Task 6: Sprint-2 notes — the comparison, read honestly

**Files:**
- Modify: `docs/sprint-2-notes.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the two cuts from Task 5.

- [ ] **Step 1: Write the results section**

Append a `## 3. Evidenced outcomes` section to `docs/sprint-2-notes.md` covering:

- The new rule and why `shipped` stopped being the fallthrough.
- The label distribution before and after.
- Both cuts' signal tables, side by side, each labelled.
- **The comparison as the finding**: how the three signals score where evidence exists
  against where it does not. State plainly whether the signals hold up, weaken, or
  change sign between cuts — whatever the numbers show.
- Whether the 69-row known-error floor is now `unresolved` (Task 3 Step 6).
- Coverage by stage, and that `beta` at 22.2% is disproportionately excluded from the
  evidenced cut.
- What this still does not fix, from spec §6: the 306/644 coverage ceiling, closure's
  90-day heuristic, and that a merged PR proves code landed rather than that the feature
  shipped.

Describe only what the numbers show. If a signal looks worse under the evidenced cut,
say so — that is a result, not a problem to explain away.

- [ ] **Step 2: Update the README results section**

The README's results table and its three readings are now the evidenced cut. Update the
figures, label the table with its cut, and add one short paragraph on what the full cut
shows and why both are published. Keep the existing honesty about `late_target` being
negatively predictive and `prior_slip` being non-significant, updated to whatever the new
numbers say.

- [ ] **Step 3: Verify every figure against the artifacts**

Run:
```bash
.venv/bin/python -c "
import csv
for f in ('signals.csv','signals_full.csv'):
    print('---', f)
    for r in csv.DictReader(open('out/k8s/'+f)):
        print(f\"  {r['cut']:9s} {r['signal']:13s} fired={r['fired']:>4} lift={float(r['lift']):.3f} \"
              f\"CI=({float(r['lift_ci_lo']):.3f},{float(r['lift_ci_hi']):.3f})\")"
```
Every number quoted in the notes and README must match this output exactly.

- [ ] **Step 4: Commit**

```bash
git add docs/sprint-2-notes.md README.md
git commit -m "docs: evidenced vs full cut, and what the comparison shows"
```

---

## Not in this plan

**S8 `broken_trail`** (spec §5) is deliberately excluded. It needs tracking labels inside
`snapshot()`, which means a new `tracking-issue` value in `core.model.SOURCES` and a place
in `ItemState` for point-in-time labels — the only part of the design that touches the core
model. It also needs the evidence-backed labels this plan produces in order to be measured
honestly, since its post-hoc lift of 1.378 is partly circular. It gets its own plan once
these labels exist.
