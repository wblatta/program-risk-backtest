# Sprint 0–1: Core Model, K8s Adapter, First Backtest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the first (knowingly rough) backtest of program-risk signals against Kubernetes enhancement history, from a local clone, with every number traceable to a timestamped event.

**Architecture:** Adapters turn raw sources into a stream of timestamped events; `core/replay.snapshot()` reconstructs "what the roadmap said on date D"; signals are pure functions over a snapshot; the backtest joins signals-at-D to outcomes-after-D. Sprint 1 covers only git-history sources (kep.yaml, prod-readiness yaml, sig-release schedules, exceptions.yaml, sigs.yaml). Tracking-issue API data is sprint 2.

**Tech Stack:** Python 3.12, stdlib `sqlite3`, `PyYAML`, `pandas` (backtest metrics only), `pytest`. Git via `subprocess`. No LLM calls in this plan.

**Spec:** `docs/superpowers/specs/2026-08-26-program-risk-backtest-design.md`

## Global Constraints

- Python 3.12. Dependencies limited to `pyyaml`, `pandas`, `pytest`.
- All timestamps are timezone-aware UTC `datetime`; all calendar dates are `date`.
- Temporal rule: `Event.ts` is when the fact became true in the source system. Git: the committer time of the first-parent commit on the default branch. Never fetch time.
- Every `Event` has a non-empty `source` ∈ {`git-history`, `calendar`, `exceptions`, `derived`}.
- `snapshot()` never reads `outcome` events. Outcomes join only where `outcome.ts > as_of`.
- `signals/` imports nothing from `adapters/`. Enforced by test.
- `adapters/<corpus>/events()` output is byte-identical across runs.
- IDs are corpus-namespaced: items `k8s:kep-2400`, org units `k8s:sig-node`, milestones `k8s:v1.34`, people `k8s:@handle` (lowercase handle, leading `@` kept).
- `cache/` is gitignored; `out/k8s/*.csv` and `adapters/k8s/calendar.yaml` are committed.
- Commit after every task with a conventional message.

## Corrections to the spec discovered while planning

Real files were fetched from the K8s repos on 2026-08-26. Apply these to the spec's §5 when executing Task 13:

1. `kep.yaml` has **no** `prr-approvers` field. PRR approvers live in `keps/prod-readiness/<sig>/<kep-number>.yaml` as `{alpha: {approver: "@x"}, beta: {...}, stable: {...}}`.
2. `releases/release-1.N/exceptions.yaml` exists in sig-release back to at least 1.26 with `enhancementFreeze:` and `codeFreeze:` lists of `{name, issue, date_requested, date_reviewed, thread, pull_requests, status}`. `issue` is the tracking-issue number, which equals the KEP number. Exception outcomes are derivable.
3. The release schedule is a markdown table in `releases/release-1.N/README.md` with stable row names: `Start of Release Cycle`, `Begin [Enhancements Freeze]`, `Begin [Code Freeze]`, `v1.N.0 released`. Date cells contain `Weekday DDth Month YYYY`, sometimes inside a link with a UTC prefix.
4. Tracking-issue labels confirmed: `tracked/yes`, `tracked/no`, `tracked/out-of-tree`, `stage/alpha|beta|stable`, `lead-opted-in`, `sig/*`. (Sprint 2.)
5. Two freeze dates matter. `Milestone.freeze` = **code freeze** (delivery deadline; lead time is measured against it). `Milestone.dates["enhancements_freeze"]` = commitment point; backtest rows are the targets present in the snapshot at enhancements freeze.

## File structure

```
pyproject.toml
core/
  __init__.py
  model.py          dataclasses WorkItem, OrgUnit, Milestone, Event; EventKind; corpus_of()
  store.py          Store: SQLite schema, replace_corpus(), load_*()
  replay.py         ItemState; snapshot(events, as_of)
adapters/
  __init__.py
  base.py           AdapterConfig, Adapter protocol
  k8s/
    __init__.py
    config.py       repo URLs, REQUIRED_ROLES, CONFIG
    fetch.py        clone_or_update() for the three repos
    kep_yaml.py     parse_kep_yaml(text) -> KepMeta
    prr_yaml.py     parse_prr_yaml(text) -> dict[stage, handle]
    git_history.py  list_kep_dirs(), file_versions(), dir_activity()
    events.py       kep_events(), prr_events(), activity_events()
    milestones.py   parse_timeline(), build_milestones(), calendar.yaml I/O
    org_units.py    parse_sigs_yaml()
    exceptions.py   parse_exceptions_yaml()
    outcomes.py     outcome_events()  — labeling rule v1
    adapter.py      K8sAdapter
    LABELING.md
    calendar.yaml   generated, human-verified, committed
signals/
  __init__.py       SIGNALS registry
  base.py           Context, Signal type
  hollow_owner.py   S1
  prior_slip.py     S5
  late_target.py    S7
backtest/
  __init__.py
  run.py            Row; run_backtest()
  metrics.py        signal_metrics(), by_org()
cli.py              spike | fetch | build | backtest
tests/
  helpers.py        make_git_repo()
  test_model.py test_store.py test_replay.py
  k8s/  test_kep_yaml.py test_prr_yaml.py test_git_history.py test_events.py
        test_milestones.py test_org_units.py test_exceptions.py test_outcomes.py
  conformance/ test_adapter.py  (parametrized over adapters; k8s runs only if cache present)
  signals/ test_agnostic.py test_hollow_owner.py test_prior_slip.py test_late_target.py
  backtest/ test_run.py test_metrics.py
```

---

### Task 1: Scaffold + kep.yaml parser + ingestion spike (sprint 0)

**Files:**
- Create: `pyproject.toml`, `core/__init__.py`, `adapters/__init__.py`, `adapters/k8s/__init__.py`, `tests/__init__.py`, `tests/k8s/__init__.py`
- Create: `adapters/k8s/config.py`, `adapters/k8s/fetch.py`, `adapters/k8s/kep_yaml.py`, `cli.py`
- Test: `tests/k8s/test_kep_yaml.py`

**Interfaces:**
- Produces: `parse_kep_yaml(text: str) -> KepMeta`; `KepMeta` frozen dataclass with fields `number: int | None, title: str, owning_sig: str, participating_sigs: tuple[str, ...], status: str, stage: str | None, latest_milestone: str | None, milestones: dict[str, str], authors: tuple[str, ...], reviewers: tuple[str, ...], approvers: tuple[str, ...]`; `KepParseError(Exception)`.
- Produces: `clone_or_update(url: str, dest: Path) -> None`; `config.REPOS: dict[str, str]` with keys `enhancements`, `community`, `sig_release`.

- [ ] **Step 1: Write pyproject and package inits**

```toml
# pyproject.toml
[project]
name = "program-risk-backtest"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = ["pyyaml>=6", "pandas>=2"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["integration: needs a populated cache/ (deselect with -m 'not integration')"]

[tool.setuptools]
packages = ["core", "adapters", "adapters.k8s", "signals", "backtest"]
```

Create empty `__init__.py` in `core/`, `adapters/`, `adapters/k8s/`, `tests/`, `tests/k8s/`. Then `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

- [ ] **Step 2: Write the failing parser tests**

```python
# tests/k8s/test_kep_yaml.py
import pytest
from adapters.k8s.kep_yaml import parse_kep_yaml, KepParseError

REAL = """\
title: Node system swap support
kep-number: 2400
authors:
  - "@ehashman"
  - "@Ike-Ma"
owning-sig: sig-node
participating-sigs:
  - sig-node
status: implemented
creation-date: 2021-04-06
reviewers:
  - "@anguslees"
approvers:
  - "@derekwaynecarr"
stage: stable
latest-milestone: "v1.34"
milestone:
  alpha: "v1.22"
  beta: "v1.30"
  stable: "v1.34"
feature-gates:
  - name: NodeSwap
"""

def test_parses_real_kep():
    m = parse_kep_yaml(REAL)
    assert m.number == 2400
    assert m.title == "Node system swap support"
    assert m.owning_sig == "sig-node"
    assert m.participating_sigs == ("sig-node",)
    assert m.status == "implemented"
    assert m.stage == "stable"
    assert m.latest_milestone == "v1.34"
    assert m.milestones == {"alpha": "v1.22", "beta": "v1.30", "stable": "v1.34"}
    assert m.authors == ("@ehashman", "@ike-ma")      # lowercased, '@' kept
    assert m.approvers == ("@derekwaynecarr",)

def test_template_placeholders_are_dropped():
    text = """\
title: T
kep-number: NNNN
authors: ["@jane"]
owning-sig: sig-xyz
status: provisional
reviewers: [TBD, "@alice"]
approvers: [TBD]
milestone:
  alpha: "v1.19"
  beta: TBD
"""
    m = parse_kep_yaml(text)
    assert m.number is None
    assert m.reviewers == ("@alice",)
    assert m.approvers == ()
    assert m.milestones == {"alpha": "v1.19"}

def test_missing_optional_fields():
    m = parse_kep_yaml("title: X\nowning-sig: sig-a\nstatus: provisional\n")
    assert m.stage is None and m.latest_milestone is None
    assert m.milestones == {} and m.authors == ()

def test_bad_yaml_raises():
    with pytest.raises(KepParseError):
        parse_kep_yaml("title: [unclosed")

def test_non_mapping_raises():
    with pytest.raises(KepParseError):
        parse_kep_yaml("- just\n- a list\n")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_kep_yaml.py -v`
Expected: FAIL with `ModuleNotFoundError: adapters.k8s.kep_yaml`

- [ ] **Step 4: Implement the parser**

```python
# adapters/k8s/kep_yaml.py
"""Parse a kep.yaml file into a normalized KepMeta. Pure; no I/O."""
from __future__ import annotations
from dataclasses import dataclass
import re
import yaml

_PLACEHOLDERS = {"", "tbd", "nnnn", "n/a", "none", "null"}
_MILESTONE_RE = re.compile(r"^v?\d+\.\d+$")


class KepParseError(Exception):
    pass


@dataclass(frozen=True)
class KepMeta:
    number: int | None
    title: str
    owning_sig: str
    participating_sigs: tuple[str, ...]
    status: str
    stage: str | None
    latest_milestone: str | None
    milestones: dict[str, str]
    authors: tuple[str, ...]
    reviewers: tuple[str, ...]
    approvers: tuple[str, ...]


def _handles(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out = []
    for v in value:
        if not isinstance(v, str):
            continue
        s = v.strip().lower()
        if s in _PLACEHOLDERS:
            continue
        if not s.startswith("@"):
            s = "@" + s
        out.append(s)
    return tuple(out)


def _strs(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value if isinstance(v, str) and str(v).strip().lower() not in _PLACEHOLDERS)


def _milestone(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip().strip('"')
    if s.lower() in _PLACEHOLDERS or not _MILESTONE_RE.match(s):
        return None
    return s if s.startswith("v") else "v" + s


def _number(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_kep_yaml(text: str) -> KepMeta:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise KepParseError(str(e)) from e
    if not isinstance(data, dict):
        raise KepParseError("kep.yaml is not a mapping")
    raw_ms = data.get("milestone") or {}
    milestones = {}
    if isinstance(raw_ms, dict):
        for stage, v in raw_ms.items():
            m = _milestone(v)
            if m:
                milestones[str(stage).strip().lower()] = m
    stage = data.get("stage")
    return KepMeta(
        number=_number(data.get("kep-number")),
        title=str(data.get("title") or "").strip(),
        owning_sig=str(data.get("owning-sig") or "").strip().lower(),
        participating_sigs=tuple(s.lower() for s in _strs(data.get("participating-sigs"))),
        status=str(data.get("status") or "").strip().lower(),
        stage=str(stage).strip().lower() if isinstance(stage, str) and stage.strip() else None,
        latest_milestone=_milestone(data.get("latest-milestone")),
        milestones=milestones,
        authors=_handles(data.get("authors")),
        reviewers=_handles(data.get("reviewers")),
        approvers=_handles(data.get("approvers")),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_kep_yaml.py -v`
Expected: 5 PASS

- [ ] **Step 6: Write config and fetch**

```python
# adapters/k8s/config.py
from adapters.base import AdapterConfig  # created in Task 10; until then keep REPOS only

REPOS = {
    "enhancements": "https://github.com/kubernetes/enhancements.git",
    "community": "https://github.com/kubernetes/community.git",
    "sig_release": "https://github.com/kubernetes/sig-release.git",
}
REQUIRED_ROLES = ["prr_approver"]
```

For Task 1 only, omit the `AdapterConfig` import line; Task 10 adds it.

```python
# adapters/k8s/fetch.py
"""Clone or fast-forward the three K8s repos into cache_dir. Raw only."""
from __future__ import annotations
from pathlib import Path
import subprocess
from adapters.k8s.config import REPOS


def clone_or_update(url: str, dest: Path) -> None:
    if (dest / ".git").exists():
        subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=True)
        subprocess.run(["git", "-C", str(dest), "reset", "--quiet", "--hard", "origin/HEAD"], check=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", url, str(dest)], check=True)


def fetch_all(cache_dir: Path) -> dict[str, Path]:
    paths = {}
    for name, url in REPOS.items():
        dest = cache_dir / "k8s" / name
        clone_or_update(url, dest)
        paths[name] = dest
    return paths
```

- [ ] **Step 7: Write the spike command**

```python
# cli.py
"""Entry point: spike | fetch | build | backtest."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

CACHE = Path("cache")
OUT = Path("out")


def cmd_spike(args) -> None:
    from adapters.k8s.fetch import clone_or_update
    from adapters.k8s.config import REPOS
    from adapters.k8s.kep_yaml import parse_kep_yaml, KepParseError
    repo = CACHE / "k8s" / "enhancements"
    clone_or_update(REPOS["enhancements"], repo)
    rows, errors = [], []
    for path in sorted(repo.glob("keps/sig-*/*/kep.yaml")):
        try:
            m = parse_kep_yaml(path.read_text())
        except KepParseError as e:
            errors.append({"path": str(path.relative_to(repo)), "error": str(e)})
            continue
        rows.append({"dir": path.parent.name, **m.__dict__})
    out = OUT / "k8s" / "spike.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"keps": rows, "errors": errors}, indent=1, default=str))
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"{len(rows)} KEPs parsed, {len(errors)} errors -> {out}")
    print("by status:", dict(sorted(by_status.items(), key=lambda kv: -kv[1])))


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spike").set_defaults(fn=cmd_spike)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the spike**

Run: `.venv/bin/python cli.py spike`
Expected: clone takes a few minutes; then a line like `NNN KEPs parsed, N errors -> out/k8s/spike.json` and a status histogram. Open `out/k8s/spike.json` and read twenty entries. Record surprises in `docs/TPM_StudyGuide.md` §3.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml core adapters tests cli.py out/k8s/spike.json
git commit -m "feat: scaffold, kep.yaml parser, ingestion spike"
```

---

### Task 2: Core model

**Files:**
- Create: `core/model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Produces:
  - `EventKind` with constants `TARGET_SET, STATUS_CHANGED, OWNER_CHANGED, DEPENDENCY_CHANGED, ACTIVITY, OUTCOME` and `ALL: frozenset[str]`
  - `WorkItem(id: str, title: str, url: str)`
  - `OrgUnit(id: str, name: str)`
  - `Milestone(id: str, ordinal: int, freeze: date | None, release: date | None, dates: dict[str, date])`
  - `Event(ts: datetime, item_id: str, kind: str, payload: dict, source: str)` with `sort_key()` and `to_row()/from_row()`
  - `corpus_of(id: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_model.py
from datetime import datetime, timezone, date
import json
import pytest
from core.model import Event, EventKind, Milestone, corpus_of

UTC = timezone.utc

def test_corpus_of():
    assert corpus_of("k8s:kep-2400") == "k8s"
    assert corpus_of("gitlab:issue-1") == "gitlab"

def test_event_requires_utc_and_source():
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1), "k8s:kep-1", EventKind.ACTIVITY, {}, "git-history")
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {}, "")
    with pytest.raises(ValueError):
        Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", "bogus", {}, "x")

def test_event_round_trips_through_row():
    e = Event(datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC), "k8s:kep-1", EventKind.TARGET_SET,
              {"stage": "alpha", "milestone_id": "k8s:v1.30"}, "git-history")
    row = e.to_row()
    assert row["corpus"] == "k8s"
    assert json.loads(row["payload"]) == e.payload
    assert Event.from_row(row) == e

def test_sort_key_is_deterministic():
    a = Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {"b": 1, "a": 2}, "s")
    b = Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.ACTIVITY, {"a": 2, "b": 1}, "s")
    assert a.sort_key() == b.sort_key()

def test_milestone_dates_optional():
    m = Milestone("k8s:v1.99", 99, None, None, {})
    assert m.freeze is None and m.is_scheduled is False
    m2 = Milestone("k8s:v1.34", 34, date(2025, 7, 25), date(2025, 8, 27), {"enhancements_freeze": date(2025, 6, 20)})
    assert m2.is_scheduled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: core.model`

- [ ] **Step 3: Implement**

```python
# core/model.py
"""Normalized model. Three reference entities and one event stream."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import json
from typing import Any


class EventKind:
    TARGET_SET = "target_set"
    STATUS_CHANGED = "status_changed"
    OWNER_CHANGED = "owner_changed"
    DEPENDENCY_CHANGED = "dependency_changed"
    ACTIVITY = "activity"
    OUTCOME = "outcome"
    ALL = frozenset({TARGET_SET, STATUS_CHANGED, OWNER_CHANGED, DEPENDENCY_CHANGED, ACTIVITY, OUTCOME})


def corpus_of(id: str) -> str:
    return id.split(":", 1)[0]


@dataclass(frozen=True)
class WorkItem:
    id: str
    title: str
    url: str


@dataclass(frozen=True)
class OrgUnit:
    id: str
    name: str


@dataclass(frozen=True)
class Milestone:
    id: str
    ordinal: int
    freeze: date | None
    release: date | None
    dates: dict[str, date] = field(default_factory=dict)

    @property
    def is_scheduled(self) -> bool:
        return self.freeze is not None and self.release is not None


@dataclass(frozen=True)
class Event:
    ts: datetime
    item_id: str
    kind: str
    payload: dict[str, Any]
    source: str

    def __post_init__(self):
        if self.ts.tzinfo is None or self.ts.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("Event.ts must be timezone-aware UTC")
        if not self.source:
            raise ValueError("Event.source is required")
        if self.kind not in EventKind.ALL:
            raise ValueError(f"unknown event kind {self.kind!r}")

    def sort_key(self) -> tuple:
        return (self.ts, self.item_id, self.kind, json.dumps(self.payload, sort_keys=True, default=str))

    def to_row(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "corpus": corpus_of(self.item_id),
            "item_id": self.item_id,
            "kind": self.kind,
            "payload": json.dumps(self.payload, sort_keys=True, default=str),
            "source": self.source,
        }

    @classmethod
    def from_row(cls, row) -> "Event":
        return cls(datetime.fromisoformat(row["ts"]), row["item_id"], row["kind"], json.loads(row["payload"]), row["source"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_model.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add core/model.py tests/test_model.py
git commit -m "feat(core): normalized model dataclasses"
```

---

### Task 3: SQLite store

**Files:**
- Create: `core/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `core.model` dataclasses.
- Produces: `Store(path: Path)` with `init_schema()`, `replace_corpus(corpus, items, org_units, milestones, events)`, `load_items(corpus) -> list[WorkItem]`, `load_org_units(corpus) -> list[OrgUnit]`, `load_milestones(corpus) -> list[Milestone]` (sorted by ordinal), `load_events(corpus) -> list[Event]` (sorted by `sort_key()`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_store.py
from datetime import datetime, timezone, date
from core.model import Event, EventKind, Milestone, OrgUnit, WorkItem
from core.store import Store

UTC = timezone.utc

def _sample():
    items = [WorkItem("k8s:kep-1", "One", "https://x/1")]
    orgs = [OrgUnit("k8s:sig-node", "Node")]
    ms = [Milestone("k8s:v1.31", 31, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)}),
          Milestone("k8s:v1.30", 30, None, None, {})]
    ev = [Event(datetime(2024, 2, 1, tzinfo=UTC), "k8s:kep-1", EventKind.STATUS_CHANGED, {"status": "implementable"}, "git-history"),
          Event(datetime(2024, 1, 1, tzinfo=UTC), "k8s:kep-1", EventKind.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"}, "git-history")]
    return items, orgs, ms, ev

def test_round_trip(tmp_path):
    s = Store(tmp_path / "s.sqlite"); s.init_schema()
    items, orgs, ms, ev = _sample()
    s.replace_corpus("k8s", items, orgs, ms, ev)
    assert s.load_items("k8s") == items
    assert s.load_org_units("k8s") == orgs
    assert [m.id for m in s.load_milestones("k8s")] == ["k8s:v1.30", "k8s:v1.31"]
    assert s.load_milestones("k8s")[1].dates == {"enhancements_freeze": date(2024, 6, 7)}
    assert s.load_events("k8s") == sorted(ev, key=Event.sort_key)

def test_replace_is_idempotent_and_scoped(tmp_path):
    s = Store(tmp_path / "s.sqlite"); s.init_schema()
    items, orgs, ms, ev = _sample()
    s.replace_corpus("k8s", items, orgs, ms, ev)
    s.replace_corpus("k8s", items, orgs, ms, ev)
    assert len(s.load_events("k8s")) == 2
    other = [Event(datetime(2024, 1, 1, tzinfo=UTC), "gitlab:issue-9", EventKind.ACTIVITY, {}, "api")]
    s.replace_corpus("gitlab", [WorkItem("gitlab:issue-9", "x", "u")], [], [], other)
    assert len(s.load_events("k8s")) == 2
    assert len(s.load_events("gitlab")) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: core.store`

- [ ] **Step 3: Implement**

```python
# core/store.py
"""SQLite persistence for the normalized model. One file, stdlib only."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Iterable
from core.model import Event, Milestone, OrgUnit, WorkItem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_item (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS org_unit (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS milestone (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, ordinal INTEGER NOT NULL,
    freeze TEXT, release TEXT, dates TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event (ts TEXT NOT NULL, corpus TEXT NOT NULL, item_id TEXT NOT NULL, kind TEXT NOT NULL,
    payload TEXT NOT NULL, source TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS event_corpus_ts ON event (corpus, ts);
"""


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)

    def replace_corpus(self, corpus: str, items: Iterable[WorkItem], org_units: Iterable[OrgUnit],
                       milestones: Iterable[Milestone], events: Iterable[Event]) -> None:
        c = self.conn
        with c:
            for t in ("work_item", "org_unit", "milestone", "event"):
                c.execute(f"DELETE FROM {t} WHERE corpus = ?", (corpus,))
            c.executemany("INSERT INTO work_item VALUES (?,?,?,?)", [(i.id, corpus, i.title, i.url) for i in items])
            c.executemany("INSERT INTO org_unit VALUES (?,?,?)", [(o.id, corpus, o.name) for o in org_units])
            c.executemany("INSERT INTO milestone VALUES (?,?,?,?,?,?)", [
                (m.id, corpus, m.ordinal, m.freeze.isoformat() if m.freeze else None,
                 m.release.isoformat() if m.release else None,
                 json.dumps({k: v.isoformat() for k, v in sorted(m.dates.items())})) for m in milestones])
            c.executemany("INSERT INTO event VALUES (:ts,:corpus,:item_id,:kind,:payload,:source)",
                          [e.to_row() for e in sorted(events, key=Event.sort_key)])

    def load_items(self, corpus: str) -> list[WorkItem]:
        rows = self.conn.execute("SELECT id,title,url FROM work_item WHERE corpus=? ORDER BY id", (corpus,))
        return [WorkItem(r["id"], r["title"], r["url"]) for r in rows]

    def load_org_units(self, corpus: str) -> list[OrgUnit]:
        rows = self.conn.execute("SELECT id,name FROM org_unit WHERE corpus=? ORDER BY id", (corpus,))
        return [OrgUnit(r["id"], r["name"]) for r in rows]

    def load_milestones(self, corpus: str) -> list[Milestone]:
        rows = self.conn.execute("SELECT * FROM milestone WHERE corpus=? ORDER BY ordinal", (corpus,))
        return [Milestone(r["id"], r["ordinal"], _d(r["freeze"]), _d(r["release"]),
                          {k: date.fromisoformat(v) for k, v in json.loads(r["dates"]).items()}) for r in rows]

    def load_events(self, corpus: str) -> list[Event]:
        rows = self.conn.execute("SELECT * FROM event WHERE corpus=?", (corpus,))
        return sorted((Event.from_row(r) for r in rows), key=Event.sort_key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_store.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add core/store.py tests/test_store.py
git commit -m "feat(core): sqlite store with per-corpus replace"
```

---

### Task 4: Replay → snapshot

**Files:**
- Create: `core/replay.py`
- Test: `tests/test_replay.py`

**Interfaces:**
- Consumes: `Event`, `EventKind`.
- Produces: `ItemState` dataclass with fields `item_id: str, created_at: datetime, targets: dict[str, str]` (stage → milestone_id; stageless uses key `""`), `target_set_at: dict[str, datetime]`, `target_history: dict[str, list[str]]`, `status: str | None`, `owners: dict[str, set[str]]` (role → subject ids), `deps: set[str]`, `last_activity: dict[str, datetime]` (actor → ts), `last_activity_any: datetime | None`. And `snapshot(events: Iterable[Event], as_of: datetime) -> dict[str, ItemState]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_replay.py
from datetime import datetime, timezone
from core.model import Event, EventKind as K
from core.replay import snapshot

UTC = timezone.utc
def T(m, d=1): return datetime(2024, m, d, tzinfo=UTC)
def ev(ts, kind, payload, item="k8s:kep-1"): return Event(ts, item, kind, payload, "test")

def test_targets_history_and_timestamps():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(3), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"}),
           ev(T(3, 2), K.TARGET_SET, {"stage": "beta", "milestone_id": "k8s:v1.32"})]
    s = snapshot(evs, T(4))["k8s:kep-1"]
    assert s.targets == {"alpha": "k8s:v1.31", "beta": "k8s:v1.32"}
    assert s.target_history["alpha"] == ["k8s:v1.30", "k8s:v1.31"]
    assert s.target_set_at["alpha"] == T(3)
    assert s.created_at == T(1)

def test_as_of_excludes_future_events():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(3), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.31"})]
    s = snapshot(evs, T(2))["k8s:kep-1"]
    assert s.targets == {"alpha": "k8s:v1.30"}
    assert snapshot(evs, T(1, 1))["k8s:kep-1"].targets == {"alpha": "k8s:v1.30"}  # inclusive

def test_outcomes_never_enter_snapshot():
    evs = [ev(T(1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "k8s:v1.30"}),
           ev(T(2), K.OUTCOME, {"milestone_id": "k8s:v1.30", "stage": "alpha", "result": "slipped"})]
    s = snapshot(evs, T(5))["k8s:kep-1"]
    assert not hasattr(s, "outcome")
    assert s.targets == {"alpha": "k8s:v1.30"}

def test_owners_add_remove_and_status():
    evs = [ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "add"}),
           ev(T(1), K.OWNER_CHANGED, {"subject_id": "k8s:sig-node", "role": "owning", "op": "add"}),
           ev(T(2), K.OWNER_CHANGED, {"subject_id": "k8s:@a", "role": "author", "op": "remove"}),
           ev(T(2), K.STATUS_CHANGED, {"status": "implementable"})]
    s = snapshot(evs, T(3))["k8s:kep-1"]
    assert s.owners == {"author": set(), "owning": {"k8s:sig-node"}}
    assert s.status == "implementable"

def test_deps_and_activity():
    evs = [ev(T(1), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "add"}),
           ev(T(2), K.ACTIVITY, {"actor_id": "k8s:@a", "kind": "commit", "ref": "abc"}),
           ev(T(3), K.ACTIVITY, {"actor_id": "k8s:@b", "kind": "comment", "ref": "1"}),
           ev(T(4), K.DEPENDENCY_CHANGED, {"depends_on_id": "k8s:kep-2", "op": "remove"})]
    s = snapshot(evs, T(3, 15))["k8s:kep-1"]
    assert s.deps == {"k8s:kep-2"}
    assert s.last_activity == {"k8s:@a": T(2), "k8s:@b": T(3)}
    assert s.last_activity_any == T(3)
    assert snapshot(evs, T(5))["k8s:kep-1"].deps == set()

def test_stageless_target_uses_empty_key():
    evs = [ev(T(1), K.TARGET_SET, {"milestone_id": "gitlab:17.3"}, item="gitlab:issue-1")]
    assert snapshot(evs, T(2))["gitlab:issue-1"].targets == {"": "gitlab:17.3"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_replay.py -v`
Expected: FAIL with `ModuleNotFoundError: core.replay`

- [ ] **Step 3: Implement**

```python
# core/replay.py
"""Replay non-outcome events up to as_of into per-item state. The leakage guard lives here."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable
from core.model import Event, EventKind as K


@dataclass
class ItemState:
    item_id: str
    created_at: datetime
    targets: dict[str, str] = field(default_factory=dict)
    target_set_at: dict[str, datetime] = field(default_factory=dict)
    target_history: dict[str, list[str]] = field(default_factory=dict)
    status: str | None = None
    owners: dict[str, set[str]] = field(default_factory=dict)
    deps: set[str] = field(default_factory=set)
    last_activity: dict[str, datetime] = field(default_factory=dict)

    @property
    def last_activity_any(self) -> datetime | None:
        return max(self.last_activity.values()) if self.last_activity else None


def snapshot(events: Iterable[Event], as_of: datetime) -> dict[str, ItemState]:
    states: dict[str, ItemState] = {}
    for e in sorted(events, key=Event.sort_key):
        if e.kind == K.OUTCOME or e.ts > as_of:
            continue
        s = states.get(e.item_id)
        if s is None:
            s = states[e.item_id] = ItemState(e.item_id, e.ts)
        p = e.payload
        if e.kind == K.TARGET_SET:
            stage = p.get("stage") or ""
            s.targets[stage] = p["milestone_id"]
            s.target_set_at[stage] = e.ts
            hist = s.target_history.setdefault(stage, [])
            if not hist or hist[-1] != p["milestone_id"]:
                hist.append(p["milestone_id"])
        elif e.kind == K.STATUS_CHANGED:
            s.status = p["status"]
        elif e.kind == K.OWNER_CHANGED:
            bucket = s.owners.setdefault(p["role"], set())
            (bucket.add if p["op"] == "add" else bucket.discard)(p["subject_id"])
        elif e.kind == K.DEPENDENCY_CHANGED:
            (s.deps.add if p["op"] == "add" else s.deps.discard)(p["depends_on_id"])
        elif e.kind == K.ACTIVITY:
            actor = p["actor_id"]
            if actor not in s.last_activity or s.last_activity[actor] < e.ts:
                s.last_activity[actor] = e.ts
    return states
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_replay.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add core/replay.py tests/test_replay.py
git commit -m "feat(core): event replay to point-in-time snapshot"
```

---

### Task 5: Git history access

**Files:**
- Create: `adapters/k8s/git_history.py`, `tests/helpers.py`
- Test: `tests/k8s/test_git_history.py`

**Interfaces:**
- Produces: `FileVersion(sha: str, ts: datetime, text: str)` frozen dataclass; `list_kep_dirs(repo: Path) -> list[str]` (relative paths like `keps/sig-node/2400-node-swap`, sorted); `file_versions(repo: Path, rel_path: str) -> list[FileVersion]` oldest first, first-parent history; `dir_activity(repo: Path, rel_dir: str) -> list[tuple[datetime, str, str]]` of `(ts, sha, author_email)` for every non-merge commit touching the dir, oldest first.
- Produces test helper: `make_git_repo(root: Path, commits: list[tuple[datetime, dict[str, str | None]]]) -> Path` — each commit is `(committer_ts, {rel_path: content or None to delete})`.

- [ ] **Step 1: Write the test helper**

```python
# tests/helpers.py
from __future__ import annotations
from datetime import datetime
import os
from pathlib import Path
import subprocess


def _git(repo: Path, *args, env=None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def make_git_repo(root: Path, commits: list[tuple[datetime, dict[str, str | None]]]) -> Path:
    """Build a repo where each commit lands at the given UTC timestamp. Returns repo path."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    for i, (ts, files) in enumerate(commits):
        for rel, content in files.items():
            p = root / rel
            if content is None:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
        _git(root, "add", "-A")
        stamp = ts.strftime("%Y-%m-%dT%H:%M:%S+0000")
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        _git(root, "commit", "-q", "--allow-empty", "-m", f"c{i}", env=env)
    return root
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/k8s/test_git_history.py
from datetime import datetime, timezone
from adapters.k8s.git_history import list_kep_dirs, file_versions, dir_activity
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(d): return datetime(2024, 1, d, 12, 0, tzinfo=UTC)

def test_file_versions_oldest_first_with_commit_times(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "status: provisional\n"}),
        (T(2), {"README.md": "unrelated\n"}),
        (T(3), {"keps/sig-a/100-x/kep.yaml": "status: implementable\n"}),
    ])
    vs = file_versions(repo, "keps/sig-a/100-x/kep.yaml")
    assert [v.ts for v in vs] == [T(1), T(3)]
    assert [v.text for v in vs] == ["status: provisional\n", "status: implementable\n"]
    assert all(len(v.sha) == 40 for v in vs)

def test_list_kep_dirs_only_those_with_kep_yaml(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "a", "keps/sig-b/200-y/kep.yaml": "b",
                "keps/sig-b/README.md": "no", "keps/prod-readiness/sig-a/100.yaml": "prr"}),
    ])
    assert list_kep_dirs(repo) == ["keps/sig-a/100-x", "keps/sig-b/200-y"]

def test_dir_activity_lists_every_commit_touching_dir(tmp_path):
    repo = make_git_repo(tmp_path / "r", [
        (T(1), {"keps/sig-a/100-x/kep.yaml": "a"}),
        (T(2), {"keps/sig-a/100-x/README.md": "design"}),
        (T(3), {"keps/sig-b/200-y/kep.yaml": "b"}),
    ])
    acts = dir_activity(repo, "keps/sig-a/100-x")
    assert [a[0] for a in acts] == [T(1), T(2)]
    assert all(a[2] == "t@example.com" for a in acts)

def test_missing_path_gives_empty(tmp_path):
    repo = make_git_repo(tmp_path / "r", [(T(1), {"x": "y"})])
    assert file_versions(repo, "nope/kep.yaml") == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_git_history.py -v`
Expected: FAIL with `ModuleNotFoundError: adapters.k8s.git_history`

- [ ] **Step 4: Implement**

```python
# adapters/k8s/git_history.py
"""Read-only access to a local clone's history. First-parent commit time = when it became true on main."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class FileVersion:
    sha: str
    ts: datetime
    text: str


def _git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout


def _ts(epoch: str) -> datetime:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc)


def list_kep_dirs(repo: Path) -> list[str]:
    out = _git(repo, "ls-files", "keps/*/*/kep.yaml")
    dirs = {line.rsplit("/", 1)[0] for line in out.splitlines() if line.startswith("keps/sig-")}
    return sorted(dirs)


def file_versions(repo: Path, rel_path: str) -> list[FileVersion]:
    log = _git(repo, "log", "--first-parent", "--format=%H %ct", "--", rel_path)
    versions = []
    for line in reversed(log.splitlines()):
        sha, epoch = line.split()
        text = _git(repo, "show", f"{sha}:{rel_path}")
        if text == "":
            continue  # deleted in this commit
        versions.append(FileVersion(sha, _ts(epoch), text))
    return versions


def dir_activity(repo: Path, rel_dir: str) -> list[tuple[datetime, str, str]]:
    log = _git(repo, "log", "--no-merges", "--format=%H %ct %ae", "--", rel_dir)
    out = []
    for line in reversed(log.splitlines()):
        sha, epoch, email = line.split(" ", 2)
        out.append((_ts(epoch), sha, email))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_git_history.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add adapters/k8s/git_history.py tests/helpers.py tests/k8s/test_git_history.py
git commit -m "feat(k8s): git history access with first-parent timestamps"
```

---

### Task 6: KEP and PRR diffs → events

**Files:**
- Create: `adapters/k8s/prr_yaml.py`, `adapters/k8s/events.py`
- Test: `tests/k8s/test_prr_yaml.py`, `tests/k8s/test_events.py`

**Interfaces:**
- Consumes: `KepMeta`, `parse_kep_yaml`, `FileVersion`, `Event`, `EventKind`.
- Produces: `parse_prr_yaml(text) -> dict[str, str]` (stage → lowercase handle with `@`); `kep_events(item_id, versions: list[FileVersion]) -> list[Event]`; `prr_events(item_id, versions: list[FileVersion]) -> list[Event]`; `activity_events(item_id, activity: list[tuple[datetime, str, str]]) -> list[Event]`; `MILESTONE_PREFIX = "k8s:"`, `SIG_PREFIX = "k8s:"`, `person_id(handle) -> str`.

- [ ] **Step 1: Write failing PRR tests**

```python
# tests/k8s/test_prr_yaml.py
from adapters.k8s.prr_yaml import parse_prr_yaml

def test_parses_stage_approvers():
    text = 'kep-number: 2400\nalpha:\n  approver: "@Deads2k"\nbeta:\n  approver: "@deads2k"\nstable:\n  approver: TBD\n'
    assert parse_prr_yaml(text) == {"alpha": "@deads2k", "beta": "@deads2k"}

def test_garbage_is_empty():
    assert parse_prr_yaml("- nope") == {}
    assert parse_prr_yaml(": [") == {}
```

- [ ] **Step 2: Implement PRR parser**

```python
# adapters/k8s/prr_yaml.py
"""Parse keps/prod-readiness/<sig>/<num>.yaml → {stage: approver handle}."""
from __future__ import annotations
import yaml

_PLACEHOLDERS = {"", "tbd", "none", "null", "n/a"}


def parse_prr_yaml(text: str) -> dict[str, str]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for stage in ("alpha", "beta", "stable"):
        block = data.get(stage)
        if not isinstance(block, dict):
            continue
        h = str(block.get("approver") or "").strip().lower()
        if h in _PLACEHOLDERS:
            continue
        out[stage] = h if h.startswith("@") else "@" + h
    return out
```

Run: `.venv/bin/pytest tests/k8s/test_prr_yaml.py -v` → 2 PASS.

- [ ] **Step 3: Write failing event tests**

```python
# tests/k8s/test_events.py
from datetime import datetime, timezone
from adapters.k8s.git_history import FileVersion
from adapters.k8s.events import kep_events, prr_events, activity_events
from core.model import EventKind as K

UTC = timezone.utc
def T(d): return datetime(2024, 1, d, tzinfo=UTC)
V1 = 'title: X\nkep-number: 100\nowning-sig: sig-a\nparticipating-sigs: [sig-b]\nstatus: provisional\nauthors: ["@ann"]\napprovers: ["@bob"]\nmilestone:\n  alpha: "v1.30"\n'
V2 = 'title: X\nkep-number: 100\nowning-sig: sig-a\nparticipating-sigs: [sig-b, sig-c]\nstatus: implementable\nauthors: ["@ann", "@cat"]\napprovers: []\nmilestone:\n  alpha: "v1.31"\n  beta: "v1.32"\n'

def by_kind(evs, kind): return [e for e in evs if e.kind == kind]

def test_first_version_emits_full_state():
    evs = kep_events("k8s:kep-100", [FileVersion("a"*40, T(1), V1)])
    assert all(e.ts == T(1) and e.source == "git-history" for e in evs)
    assert by_kind(evs, K.TARGET_SET)[0].payload == {"stage": "alpha", "milestone_id": "k8s:v1.30"}
    assert by_kind(evs, K.STATUS_CHANGED)[0].payload == {"status": "provisional"}
    owners = {(e.payload["role"], e.payload["subject_id"], e.payload["op"]) for e in by_kind(evs, K.OWNER_CHANGED)}
    assert owners == {("owning", "k8s:sig-a", "add"), ("participating", "k8s:sig-b", "add"),
                      ("author", "k8s:@ann", "add"), ("approver", "k8s:@bob", "add")}

def test_second_version_emits_only_diffs():
    evs = kep_events("k8s:kep-100", [FileVersion("a"*40, T(1), V1), FileVersion("b"*40, T(5), V2)])
    later = [e for e in evs if e.ts == T(5)]
    targets = {(e.payload["stage"], e.payload["milestone_id"]) for e in by_kind(later, K.TARGET_SET)}
    assert targets == {("alpha", "k8s:v1.31"), ("beta", "k8s:v1.32")}
    assert by_kind(later, K.STATUS_CHANGED)[0].payload == {"status": "implementable"}
    owners = {(e.payload["role"], e.payload["subject_id"], e.payload["op"]) for e in by_kind(later, K.OWNER_CHANGED)}
    assert owners == {("participating", "k8s:sig-c", "add"), ("author", "k8s:@cat", "add"), ("approver", "k8s:@bob", "remove")}

def test_unparseable_version_is_skipped():
    evs = kep_events("k8s:kep-100", [FileVersion("a"*40, T(1), "title: [bad"), FileVersion("b"*40, T(2), V1)])
    assert min(e.ts for e in evs) == T(2)

def test_identical_versions_emit_nothing_new():
    evs = kep_events("k8s:kep-100", [FileVersion("a"*40, T(1), V1), FileVersion("b"*40, T(2), V1)])
    assert all(e.ts == T(1) for e in evs)

def test_prr_events_add_and_change():
    p1 = 'alpha:\n  approver: "@x"\n'
    p2 = 'alpha:\n  approver: "@y"\nbeta:\n  approver: "@y"\n'
    evs = prr_events("k8s:kep-100", [FileVersion("a"*40, T(1), p1), FileVersion("b"*40, T(2), p2)])
    got = {(e.ts.day, e.payload["op"], e.payload["subject_id"], e.payload["stage"]) for e in evs}
    assert got == {(1, "add", "k8s:@x", "alpha"), (2, "remove", "k8s:@x", "alpha"),
                   (2, "add", "k8s:@y", "alpha"), (2, "add", "k8s:@y", "beta")}
    assert all(e.payload["role"] == "prr_approver" for e in evs)

def test_activity_events_use_unknown_actor_in_sprint_1():
    evs = activity_events("k8s:kep-100", [(T(1), "a"*40, "ann@example.com")])
    assert evs[0].kind == K.ACTIVITY
    assert evs[0].payload == {"actor_id": "k8s:unknown", "kind": "commit", "ref": "a"*40, "author_email": "ann@example.com"}
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: adapters.k8s.events`

- [ ] **Step 5: Implement**

```python
# adapters/k8s/events.py
"""Turn version histories into normalized events. Pure; no I/O."""
from __future__ import annotations
from datetime import datetime
from core.model import Event, EventKind as K
from adapters.k8s.git_history import FileVersion
from adapters.k8s.kep_yaml import KepMeta, KepParseError, parse_kep_yaml
from adapters.k8s.prr_yaml import parse_prr_yaml

SRC = "git-history"
PREFIX = "k8s:"


def person_id(handle: str) -> str:
    return PREFIX + handle.lower()


def sig_id(sig: str) -> str:
    return PREFIX + sig.lower()


def milestone_id(v: str) -> str:
    return PREFIX + v


def _owner_sets(m: KepMeta) -> dict[str, set[str]]:
    return {
        "owning": {sig_id(m.owning_sig)} if m.owning_sig else set(),
        "participating": {sig_id(s) for s in m.participating_sigs},
        "author": {person_id(h) for h in m.authors},
        "approver": {person_id(h) for h in m.approvers},
    }


def _diff_owners(item_id: str, ts: datetime, before: dict[str, set[str]], after: dict[str, set[str]], extra: dict | None = None) -> list[Event]:
    out = []
    for role in sorted(set(before) | set(after)):
        b, a = before.get(role, set()), after.get(role, set())
        for s in sorted(a - b):
            out.append(Event(ts, item_id, K.OWNER_CHANGED, {"subject_id": s, "role": role, "op": "add", **(extra or {})}, SRC))
        for s in sorted(b - a):
            out.append(Event(ts, item_id, K.OWNER_CHANGED, {"subject_id": s, "role": role, "op": "remove", **(extra or {})}, SRC))
    return out


def kep_events(item_id: str, versions: list[FileVersion]) -> list[Event]:
    out: list[Event] = []
    prev: KepMeta | None = None
    for v in versions:
        try:
            cur = parse_kep_yaml(v.text)
        except KepParseError:
            continue
        prev_ms = prev.milestones if prev else {}
        for stage, ms in sorted(cur.milestones.items()):
            if prev_ms.get(stage) != ms:
                out.append(Event(v.ts, item_id, K.TARGET_SET, {"stage": stage, "milestone_id": milestone_id(ms)}, SRC))
        if cur.status and (prev is None or prev.status != cur.status):
            out.append(Event(v.ts, item_id, K.STATUS_CHANGED, {"status": cur.status}, SRC))
        out.extend(_diff_owners(item_id, v.ts, _owner_sets(prev) if prev else {}, _owner_sets(cur)))
        prev = cur
    return out


def prr_events(item_id: str, versions: list[FileVersion]) -> list[Event]:
    out: list[Event] = []
    prev: dict[str, str] = {}
    for v in versions:
        cur = parse_prr_yaml(v.text)
        for stage in sorted(set(prev) | set(cur)):
            b, a = prev.get(stage), cur.get(stage)
            if b == a:
                continue
            if b:
                out.append(Event(v.ts, item_id, K.OWNER_CHANGED, {"subject_id": person_id(b), "role": "prr_approver", "op": "remove", "stage": stage}, SRC))
            if a:
                out.append(Event(v.ts, item_id, K.OWNER_CHANGED, {"subject_id": person_id(a), "role": "prr_approver", "op": "add", "stage": stage}, SRC))
        prev = cur
    return out


def activity_events(item_id: str, activity: list[tuple[datetime, str, str]]) -> list[Event]:
    # Sprint 1: git author emails cannot be mapped to GitHub handles reliably; actor is unknown.
    # Sprint 2 replaces this with tracking-issue commenters and PR authors from the API.
    return [Event(ts, item_id, K.ACTIVITY, {"actor_id": PREFIX + "unknown", "kind": "commit", "ref": sha, "author_email": email}, SRC)
            for ts, sha, email in activity]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_events.py tests/k8s/test_prr_yaml.py -v`
Expected: 8 PASS

- [ ] **Step 7: Commit**

```bash
git add adapters/k8s/prr_yaml.py adapters/k8s/events.py tests/k8s/test_prr_yaml.py tests/k8s/test_events.py
git commit -m "feat(k8s): kep.yaml and PRR diffs to events"
```

---

### Task 7: Release calendar → milestones

**Files:**
- Create: `adapters/k8s/milestones.py`, `adapters/k8s/calendar.yaml` (generated)
- Test: `tests/k8s/test_milestones.py`

**Interfaces:**
- Consumes: `Milestone`.
- Produces: `parse_timeline(readme: str) -> dict[str, date]` with keys among `start`, `enhancements_freeze`, `code_freeze`, `release`; `build_milestones(sig_release_repo: Path, max_minor: int = 60) -> list[Milestone]`; `write_calendar(milestones, path: Path)`; `load_calendar(path: Path) -> list[Milestone]`.
- `Milestone.freeze` = code freeze. `Milestone.dates` carries `start`, `enhancements_freeze`, `code_freeze`, `release`. Unscheduled placeholders `k8s:v1.0..v1.<max_minor>` have `freeze=release=None` so every `target_set` can reference a known milestone.

- [ ] **Step 1: Write the failing tests**

```python
# tests/k8s/test_milestones.py
from datetime import date
from pathlib import Path
from adapters.k8s.milestones import parse_timeline, build_milestones, write_calendar, load_calendar

TABLE = """\
| **What** | **Who** | **When** | **Week** |
| Start of Release Cycle | Lead | Monday 19th May 2025 | week 1 |
| **Begin [Production Readiness Freeze]** | Enhancements Lead | Thursday 12th June 2025 | week 4 |
| **Begin [Enhancements Freeze]** | Enhancements Lead | [21:00 UTC Friday 20th June 2025 / 14:00 PST Friday 20th June 2025](https://x) | week 5 |
| v1.34.0-alpha.3 released | Branch Manager | Wednesday 9th July 2025 | week 8 |
| **Begin [Code Freeze] and [Test Freeze]** | Branch Manager | [02:00 UTC Friday 25th July 2025 / 19:00 PDT Thursday 24th July 2025](https://y) | week 10 |
| v1.34.0-rc.0 released | Branch Manager | Wednesday 6th August 2025 | week 12 |
| **v1.34.0 released** | Branch Manager | Wednesday 27th August 2025 | week 15 |
"""

BULLETS_128 = """\
- **[01:00 UTC Friday 16th June 2023 / 18:00 PDT Thursday 15th June 2023](https://a)**: Week 5 — [Enhancements Freeze](../release_phases.md#enhancements-freeze)
- **[01:00 UTC Wednesday 19th July 2023 / 18:00 PDT Tuesday 18th July 2023](https://b)**: Week 10 — [Code Freeze](../release_phases.md#code-freeze)
- **Tuesday 15th August 2023**: Week 14 — Kubernetes v1.28.0 released
| Start of Release Cycle | Lead | Monday 15th May 2023 | week 1 |
"""

def test_parse_table_form():
    d = parse_timeline(TABLE)
    assert d == {"start": date(2025, 5, 19), "enhancements_freeze": date(2025, 6, 20),
                 "code_freeze": date(2025, 7, 25), "release": date(2025, 8, 27)}

def test_parse_bullet_form():
    d = parse_timeline(BULLETS_128)
    assert d["enhancements_freeze"] == date(2023, 6, 16)
    assert d["code_freeze"] == date(2023, 7, 19)
    assert d["release"] == date(2023, 8, 15)
    assert d["start"] == date(2023, 5, 15)

def test_build_from_repo_with_placeholders(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.34").mkdir(parents=True)
    (repo / "releases" / "release-1.34" / "README.md").write_text(TABLE)
    ms = build_milestones(repo, max_minor=36)
    by_id = {m.id: m for m in ms}
    assert by_id["k8s:v1.34"].freeze == date(2025, 7, 25)
    assert by_id["k8s:v1.34"].release == date(2025, 8, 27)
    assert by_id["k8s:v1.34"].dates["enhancements_freeze"] == date(2025, 6, 20)
    assert by_id["k8s:v1.34"].ordinal == 34
    assert by_id["k8s:v1.35"].freeze is None and by_id["k8s:v1.0"].ordinal == 0
    assert len(ms) == 37

def test_calendar_round_trip(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.34").mkdir(parents=True)
    (repo / "releases" / "release-1.34" / "README.md").write_text(TABLE)
    ms = build_milestones(repo, max_minor=36)
    p = tmp_path / "calendar.yaml"
    write_calendar(ms, p)
    assert load_calendar(p) == ms
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/k8s/test_milestones.py -v`
Expected: FAIL with `ModuleNotFoundError: adapters.k8s.milestones`

- [ ] **Step 3: Implement**

```python
# adapters/k8s/milestones.py
"""Release calendar from sig-release READMEs. Generated calendar.yaml is committed and human-verified."""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
import re
import yaml
from core.model import Milestone

PREFIX = "k8s:"
_DATE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+(\d{1,2})(?:st|nd|rd|th)\s+([A-Z][a-z]+)\s+(\d{4})")
_KEYS = [  # (key, line must match this regex, case-insensitive)
    ("start", r"start of release cycle"),
    ("enhancements_freeze", r"enhancements freeze"),
    ("code_freeze", r"code freeze"),
    ("release", r"\bv?1\.\d+\.0 released"),
]
_EXCLUDE = re.compile(r"coming|alpha|beta|rc\.", re.I)


def _first_date(line: str) -> date | None:
    m = _DATE.search(line)
    if not m:
        return None
    day, month, year = m.groups()
    return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()


def parse_timeline(readme: str) -> dict[str, date]:
    out: dict[str, date] = {}
    for line in readme.splitlines():
        for key, pat in _KEYS:
            if key in out or not re.search(pat, line, re.I):
                continue
            if key in ("enhancements_freeze", "code_freeze") and _EXCLUDE.search(line):
                continue  # "Code Freeze is Coming", alpha/beta/rc rows
            if key == "release" and re.search(r"alpha|beta|rc\.", line, re.I):
                continue
            d = _first_date(line)
            if d:
                out[key] = d
    return out


def build_milestones(sig_release_repo: Path, max_minor: int = 60) -> list[Milestone]:
    scheduled: dict[int, dict[str, date]] = {}
    for readme in sorted((sig_release_repo / "releases").glob("release-1.*/README.md")):
        minor = int(readme.parent.name.split(".")[1])
        d = parse_timeline(readme.read_text())
        if "code_freeze" in d and "release" in d:
            scheduled[minor] = d
    out = []
    for minor in range(0, max_minor + 1):
        d = scheduled.get(minor, {})
        out.append(Milestone(f"{PREFIX}v1.{minor}", minor, d.get("code_freeze"), d.get("release"), dict(d)))
    return out


def write_calendar(milestones: list[Milestone], path: Path) -> None:
    rows = [{"id": m.id, "ordinal": m.ordinal, "dates": {k: v.isoformat() for k, v in sorted(m.dates.items())}} for m in milestones]
    path.write_text("# Generated by adapters/k8s/milestones.py from sig-release READMEs. Verify by hand; edit if wrong.\n"
                    + yaml.safe_dump(rows, sort_keys=False))


def load_calendar(path: Path) -> list[Milestone]:
    rows = yaml.safe_load(path.read_text()) or []
    out = []
    for r in rows:
        dates = {k: date.fromisoformat(v) for k, v in (r.get("dates") or {}).items()}
        out.append(Milestone(r["id"], int(r["ordinal"]), dates.get("code_freeze"), dates.get("release"), dates))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_milestones.py -v`
Expected: 4 PASS. If `test_parse_table_form` fails on the "Brace Yourself, Code Freeze is Coming" style row, the `_EXCLUDE` guard is what handles it — check the regex before changing the parser structure.

- [ ] **Step 5: Generate the real calendar and eyeball it**

Run: `.venv/bin/python -c "from pathlib import Path; from adapters.k8s.fetch import clone_or_update; from adapters.k8s.config import REPOS; from adapters.k8s.milestones import *; p=Path('cache/k8s/sig_release'); clone_or_update(REPOS['sig_release'], p); ms=build_milestones(p); write_calendar(ms, Path('adapters/k8s/calendar.yaml')); print(sum(m.is_scheduled for m in ms), 'scheduled')"`

Open `adapters/k8s/calendar.yaml`. For each of v1.26–v1.37, confirm all four dates against the README by eye. Fix by hand where the parser missed; the committed file is the source of truth, the parser is just the first draft.

- [ ] **Step 6: Commit**

```bash
git add adapters/k8s/milestones.py adapters/k8s/calendar.yaml tests/k8s/test_milestones.py
git commit -m "feat(k8s): release calendar parser and verified calendar.yaml"
```

---

### Task 8: Org chart

**Files:**
- Create: `adapters/k8s/org_units.py`
- Test: `tests/k8s/test_org_units.py`

**Interfaces:**
- Produces: `parse_sigs_yaml(text: str) -> list[OrgUnit]` — ids `k8s:sig-<dir>` from the `dir` field, names from `name`; SIGs only (ignore `workinggroups`, `usergroups`, `committees`), sorted by id.

- [ ] **Step 1: Write the failing test**

```python
# tests/k8s/test_org_units.py
from adapters.k8s.org_units import parse_sigs_yaml
from core.model import OrgUnit

TEXT = """\
sigs:
  - dir: sig-node
    name: Node
    label: node
  - dir: sig-api-machinery
    name: API Machinery
workinggroups:
  - dir: wg-batch
    name: Batch
"""

def test_sigs_only_sorted():
    assert parse_sigs_yaml(TEXT) == [OrgUnit("k8s:sig-api-machinery", "API Machinery"), OrgUnit("k8s:sig-node", "Node")]

def test_empty():
    assert parse_sigs_yaml("") == []
```

- [ ] **Step 2: Run to verify it fails, then implement**

```python
# adapters/k8s/org_units.py
"""kubernetes/community sigs.yaml → OrgUnit list."""
from __future__ import annotations
import yaml
from core.model import OrgUnit

PREFIX = "k8s:"


def parse_sigs_yaml(text: str) -> list[OrgUnit]:
    data = yaml.safe_load(text) or {}
    out = []
    for s in data.get("sigs") or []:
        d = str(s.get("dir") or "").strip().lower()
        if d:
            out.append(OrgUnit(PREFIX + d, str(s.get("name") or d)))
    return sorted(out, key=lambda o: o.id)
```

Run: `.venv/bin/pytest tests/k8s/test_org_units.py -v` → 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add adapters/k8s/org_units.py tests/k8s/test_org_units.py
git commit -m "feat(k8s): org units from sigs.yaml"
```

---

### Task 9: Exceptions + labeling rule v1 → outcome events

**Files:**
- Create: `adapters/k8s/exceptions.py`, `adapters/k8s/outcomes.py`, `adapters/k8s/LABELING.md`
- Test: `tests/k8s/test_exceptions.py`, `tests/k8s/test_outcomes.py`

**Interfaces:**
- Consumes: `Event`, `EventKind`, `Milestone`, `snapshot`.
- Produces: `parse_exceptions_yaml(text: str) -> list[ExceptionRequest]` with `ExceptionRequest(issue: int, phase: str, status: str, date_requested: date | None)` where `phase ∈ {"enhancements_freeze", "code_freeze"}` and `status` lowercased; `load_exceptions(sig_release_repo: Path) -> dict[str, list[ExceptionRequest]]` keyed by milestone id; `outcome_events(events: list[Event], milestones: list[Milestone], exceptions: dict[str, list[ExceptionRequest]], today: date) -> list[Event]`.

- [ ] **Step 1: Write failing exception tests**

```python
# tests/k8s/test_exceptions.py
from datetime import date
from adapters.k8s.exceptions import parse_exceptions_yaml, ExceptionRequest

TEXT = """\
# Exception requests in v1.34
enhancementFreeze:
- name: "In-Place Update"
  issue: 1287
  date_requested: 2025-06-20
  status: "approved"
codeFreeze:
- name: "DRA"
  issue: 5004
  date_requested: 2025-07-23
  status: "Denied"
"""

def test_parse():
    assert parse_exceptions_yaml(TEXT) == [
        ExceptionRequest(1287, "enhancements_freeze", "approved", date(2025, 6, 20)),
        ExceptionRequest(5004, "code_freeze", "denied", date(2025, 7, 23)),
    ]

def test_empty_sections():
    assert parse_exceptions_yaml("enhancementFreeze:\ncodeFreeze:\n") == []
```

- [ ] **Step 2: Implement exceptions parser**

```python
# adapters/k8s/exceptions.py
"""sig-release releases/release-1.N/exceptions.yaml → ExceptionRequest list."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import yaml

_PHASES = {"enhancementFreeze": "enhancements_freeze", "codeFreeze": "code_freeze"}


@dataclass(frozen=True)
class ExceptionRequest:
    issue: int
    phase: str
    status: str
    date_requested: date | None


def _date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def parse_exceptions_yaml(text: str) -> list[ExceptionRequest]:
    data = yaml.safe_load(text) or {}
    out = []
    for key, phase in _PHASES.items():
        for r in data.get(key) or []:
            try:
                issue = int(r.get("issue"))
            except (TypeError, ValueError):
                continue
            out.append(ExceptionRequest(issue, phase, str(r.get("status") or "").strip().lower(), _date(r.get("date_requested"))))
    return out


def load_exceptions(sig_release_repo: Path) -> dict[str, list[ExceptionRequest]]:
    out = {}
    for p in sorted((sig_release_repo / "releases").glob("release-1.*/exceptions.yaml")):
        minor = p.parent.name.split(".")[1]
        out[f"k8s:v1.{minor}"] = parse_exceptions_yaml(p.read_text())
    return out
```

Run: `.venv/bin/pytest tests/k8s/test_exceptions.py -v` → 2 PASS.

- [ ] **Step 3: Write LABELING.md**

```markdown
# K8s outcome labeling rule — v1 (git history + exceptions.yaml only)

Unit: one `(item, stage, milestone M)` target present in `snapshot(M.enhancements_freeze)`.
Evaluated only for milestones whose `release` date is on or before today.

Precedence (first match wins):

1. **slipped** — after `M.enhancements_freeze`, a `target_set` for the same stage moved
   the target to a milestone with a higher ordinal.
2. **dropped** — after `M.enhancements_freeze` and before the next milestone's
   enhancements freeze, status changed to one of `withdrawn`, `rejected`, `deferred`,
   `replaced`, with no retarget.
3. **exception_denied** — `exceptions.yaml` for M lists this KEP with status not
   `approved`.
4. **exception_granted** — `exceptions.yaml` for M lists this KEP with status `approved`.
5. **shipped** — none of the above. **In v1 this means "not observed to slip", not
   "verified shipped".** Sprint 2 adds `tracked/yes` at release and code-merge
   evidence and reverses the precedence to verify shipping first.

Outcome `ts` = `M.release`. Source = `derived`.

Known blind spots in v1: a KEP that silently stops (no retarget, no status change)
is labeled shipped. A KEP whose yaml was updated only after the next cycle started
is still caught by rule 1 because the rule looks at all later events, not just
the next cycle.
```

- [ ] **Step 4: Write failing outcome tests**

```python
# tests/k8s/test_outcomes.py
from datetime import date, datetime, timezone
from adapters.k8s.exceptions import ExceptionRequest
from adapters.k8s.outcomes import outcome_events
from core.model import Event, EventKind as K, Milestone

UTC = timezone.utc
def T(y, m, d): return datetime(y, m, d, tzinfo=UTC)
M31 = Milestone("k8s:v1.31", 31, date(2024, 7, 10), date(2024, 8, 13),
                {"start": date(2024, 5, 13), "enhancements_freeze": date(2024, 6, 7), "code_freeze": date(2024, 7, 10), "release": date(2024, 8, 13)})
M32 = Milestone("k8s:v1.32", 32, date(2024, 11, 8), date(2024, 12, 11),
                {"start": date(2024, 9, 9), "enhancements_freeze": date(2024, 10, 4), "code_freeze": date(2024, 11, 8), "release": date(2024, 12, 11)})
M33 = Milestone("k8s:v1.33", 33, None, None, {})
MS = [M31, M32, M33]
TODAY = date(2025, 1, 1)

def tgt(ts, stage, ms, item="k8s:kep-1"): return Event(ts, item, K.TARGET_SET, {"stage": stage, "milestone_id": ms}, "git-history")
def st(ts, s, item="k8s:kep-1"): return Event(ts, item, K.STATUS_CHANGED, {"status": s}, "git-history")
def results(evs): return {(e.item_id, e.payload["stage"], e.payload["milestone_id"]): e.payload["result"] for e in evs}

def test_slipped_when_retargeted_later():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 7, 20), "alpha", "k8s:v1.32")]
    out = outcome_events(evs, MS, {}, TODAY)
    assert results(out)[("k8s:kep-1", "alpha", "k8s:v1.31")] == "slipped"
    assert all(e.ts.date() == date(2024, 8, 13) and e.source == "derived" for e in out if e.payload["milestone_id"] == "k8s:v1.31")

def test_shipped_when_nothing_changes():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "shipped"

def test_dropped_on_withdrawal():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), st(T(2024, 6, 20), "withdrawn")]
    assert results(outcome_events(evs, MS, {}, TODAY))[("k8s:kep-1", "alpha", "k8s:v1.31")] == "dropped"

def test_exception_granted_and_denied():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.31"), tgt(T(2024, 5, 1), "beta", "k8s:v1.31", item="k8s:kep-2")]
    exc = {"k8s:v1.31": [ExceptionRequest(1, "code_freeze", "approved", None), ExceptionRequest(2, "code_freeze", "denied", None)]}
    r = results(outcome_events(evs, MS, exc, TODAY))
    assert r[("k8s:kep-1", "alpha", "k8s:v1.31")] == "exception_granted"
    assert r[("k8s:kep-2", "beta", "k8s:v1.31")] == "exception_denied"

def test_target_added_after_enhancements_freeze_is_not_a_row():
    evs = [tgt(T(2024, 6, 20), "alpha", "k8s:v1.31")]
    assert results(outcome_events(evs, MS, {}, TODAY)) == {}

def test_unreleased_and_unscheduled_milestones_skipped():
    evs = [tgt(T(2024, 5, 1), "alpha", "k8s:v1.33"), tgt(T(2024, 5, 1), "beta", "k8s:v1.32")]
    assert results(outcome_events(evs, MS, {}, date(2024, 11, 1))) == {}
```

- [ ] **Step 5: Implement**

```python
# adapters/k8s/outcomes.py
"""Labeling rule v1. See LABELING.md — the doc is normative, this is its implementation."""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from core.model import Event, EventKind as K, Milestone
from core.replay import snapshot
from adapters.k8s.exceptions import ExceptionRequest

DROP_STATUSES = {"withdrawn", "rejected", "deferred", "replaced"}
SRC = "derived"


def _dt(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def _kep_number(item_id: str) -> int | None:
    try:
        return int(item_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


def outcome_events(events: list[Event], milestones: list[Milestone], exceptions: dict[str, list[ExceptionRequest]], today: date) -> list[Event]:
    by_ord = {m.ordinal: m for m in milestones}
    by_id = {m.id: m for m in milestones}
    out: list[Event] = []
    events = sorted(events, key=Event.sort_key)
    for m in sorted(milestones, key=lambda x: x.ordinal):
        ef = m.dates.get("enhancements_freeze")
        if not m.is_scheduled or ef is None or m.release > today:
            continue
        ef_dt = _dt(ef)
        nxt = next((x for x in milestones if x.ordinal > m.ordinal and x.dates.get("enhancements_freeze")), None)
        window_end = _dt(nxt.dates["enhancements_freeze"]) if nxt else _dt(today)
        exc_by_issue = {e.issue: e for e in exceptions.get(m.id, [])}
        for item_id, state in snapshot(events, ef_dt).items():
            for stage, target in state.targets.items():
                if target != m.id:
                    continue
                later = [e for e in events if e.item_id == item_id and e.ts > ef_dt]
                retargeted = any(e.kind == K.TARGET_SET and (e.payload.get("stage") or "") == stage
                                 and by_id.get(e.payload["milestone_id"], m).ordinal > m.ordinal for e in later)
                if retargeted:
                    result = "slipped"
                elif any(e.kind == K.STATUS_CHANGED and e.payload["status"] in DROP_STATUSES and e.ts <= window_end for e in later):
                    result = "dropped"
                else:
                    exc = exc_by_issue.get(_kep_number(item_id))
                    if exc and exc.status != "approved":
                        result = "exception_denied"
                    elif exc:
                        result = "exception_granted"
                    else:
                        result = "shipped"
                out.append(Event(_dt(m.release), item_id, K.OUTCOME, {"milestone_id": m.id, "stage": stage, "result": result}, SRC))
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/k8s/test_outcomes.py -v`
Expected: 6 PASS

- [ ] **Step 7: Commit**

```bash
git add adapters/k8s/exceptions.py adapters/k8s/outcomes.py adapters/k8s/LABELING.md tests/k8s/test_exceptions.py tests/k8s/test_outcomes.py
git commit -m "feat(k8s): exceptions parser and labeling rule v1"
```

---

### Task 10: Adapter protocol, K8sAdapter, conformance suite, `build`

**Files:**
- Create: `adapters/base.py`, `adapters/k8s/adapter.py`, `tests/conformance/__init__.py`, `tests/conformance/test_adapter.py`
- Modify: `adapters/k8s/config.py` (add `CONFIG`), `cli.py` (add `fetch`, `build`)

**Interfaces:**
- Produces: `AdapterConfig(name: str, required_roles: tuple[str, ...])`; `Adapter` Protocol with `config: AdapterConfig`, `fetch() -> None`, `work_items() -> list[WorkItem]`, `org_units() -> list[OrgUnit]`, `milestones() -> list[Milestone]`, `events() -> list[Event]`.
- Produces: `K8sAdapter(cache_dir: Path, today: date | None = None)`; `events()` = kep + prr + activity + outcome events, sorted by `sort_key()`.
- Produces: `tests/conformance/test_adapter.py::conformance(adapter)` — a plain function run against any adapter; parametrized over a fixture adapter (built from `make_git_repo`) and the real K8sAdapter (marked `integration`, skipped unless `cache/k8s/enhancements` exists).

- [ ] **Step 1: Write base protocol and config**

```python
# adapters/base.py
"""What every corpus adapter must provide. See spec §4."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from core.model import Event, Milestone, OrgUnit, WorkItem


@dataclass(frozen=True)
class AdapterConfig:
    name: str
    required_roles: tuple[str, ...]


class Adapter(Protocol):
    config: AdapterConfig

    def fetch(self) -> None: ...
    def work_items(self) -> list[WorkItem]: ...
    def org_units(self) -> list[OrgUnit]: ...
    def milestones(self) -> list[Milestone]: ...
    def events(self) -> list[Event]: ...
```

Replace `adapters/k8s/config.py` with:

```python
# adapters/k8s/config.py
from adapters.base import AdapterConfig

REPOS = {
    "enhancements": "https://github.com/kubernetes/enhancements.git",
    "community": "https://github.com/kubernetes/community.git",
    "sig_release": "https://github.com/kubernetes/sig-release.git",
}
CONFIG = AdapterConfig(name="k8s", required_roles=("prr_approver",))
```

- [ ] **Step 2: Write the conformance suite (fails: no K8sAdapter yet)**

```python
# tests/conformance/test_adapter.py
"""Corpus-agnostic adapter contract. Every adapter must pass every check."""
from __future__ import annotations
from datetime import datetime, time, timezone
from pathlib import Path
import pytest
from core.model import EventKind as K
from core.replay import snapshot
from tests.helpers import make_git_repo

UTC = timezone.utc
def T(m, d): return datetime(2024, m, d, 12, tzinfo=UTC)

KEP = 'title: Fixture\nkep-number: 100\nowning-sig: sig-a\nstatus: implementable\nauthors: ["@ann"]\nmilestone:\n  alpha: "v1.31"\n'
README_131 = ("| Start of Release Cycle | Lead | Monday 13th May 2024 | week 1 |\n"
              "| **Begin [Enhancements Freeze]** | Enhancements Lead | Friday 7th June 2024 | week 4 |\n"
              "| **Begin [Code Freeze]** | Branch Manager | Wednesday 10th July 2024 | week 9 |\n"
              "| **v1.31.0 released** | Branch Manager | Tuesday 13th August 2024 | week 14 |\n")
SIGS = "sigs:\n  - dir: sig-a\n    name: A\n"


@pytest.fixture
def fixture_adapter(tmp_path):
    from adapters.k8s.adapter import K8sAdapter
    cache = tmp_path / "cache"
    make_git_repo(cache / "k8s" / "enhancements", [
        (T(3, 1), {"keps/sig-a/100-fixture/kep.yaml": KEP, "keps/sig-a/100-fixture/README.md": "Depends on nothing.\n"}),
        (T(4, 1), {"keps/prod-readiness/sig-a/100.yaml": 'alpha:\n  approver: "@prr"\n'}),
    ])
    make_git_repo(cache / "k8s" / "community", [(T(1, 1), {"sigs.yaml": SIGS})])
    make_git_repo(cache / "k8s" / "sig_release", [(T(1, 1), {"releases/release-1.31/README.md": README_131,
                                                               "releases/release-1.31/exceptions.yaml": "enhancementFreeze:\ncodeFreeze:\n"})])
    return K8sAdapter(cache, today=datetime(2025, 1, 1).date(), calendar_path=None)


def _real_adapter():
    from adapters.k8s.adapter import K8sAdapter
    return K8sAdapter(Path("cache"))


def conformance(adapter):
    items = {i.id for i in adapter.work_items()}
    ms = {m.id: m for m in adapter.milestones()}
    ev = adapter.events()
    assert ev == sorted(ev, key=lambda e: e.sort_key())
    assert all(e.source for e in ev)
    assert all(e.item_id in items for e in ev), "event references unknown item"
    assert all(e.payload["milestone_id"] in ms for e in ev if e.kind == K.TARGET_SET), "target_set references unknown milestone"
    first_ts = {}
    for e in ev:
        first_ts.setdefault(e.item_id, e.ts)
    for e in ev:
        if e.kind == K.OUTCOME:
            m = ms[e.payload["milestone_id"]]
            assert m.is_scheduled
            assert e.ts >= first_ts[e.item_id]
            assert e.ts.date() > m.freeze
    for m in ms.values():
        if not m.is_scheduled or not m.dates.get("enhancements_freeze"):
            continue
        as_of = datetime.combine(m.dates["enhancements_freeze"], time(23, 59, 59), tzinfo=UTC)
        targeted = [s for s in snapshot(ev, as_of).values() if m.id in s.targets.values()]
        if any(e.kind == K.OUTCOME and e.payload["milestone_id"] == m.id for e in ev):
            assert targeted, f"{m.id} has outcomes but nothing targeted at enhancements freeze"
    assert ev == adapter.events(), "events() is not deterministic"
    labeling = Path(__file__).resolve().parents[2] / "adapters" / adapter.config.name / "LABELING.md"
    assert labeling.exists() and labeling.read_text().strip()


def test_fixture_adapter_conforms(fixture_adapter):
    conformance(fixture_adapter)
    ev = fixture_adapter.events()
    kinds = {e.kind for e in ev}
    assert {K.TARGET_SET, K.STATUS_CHANGED, K.OWNER_CHANGED, K.ACTIVITY, K.OUTCOME} <= kinds
    prr = [e for e in ev if e.kind == K.OWNER_CHANGED and e.payload["role"] == "prr_approver"]
    assert prr and prr[0].ts == T(4, 1)
    outcome = [e for e in ev if e.kind == K.OUTCOME][0]
    assert outcome.payload == {"milestone_id": "k8s:v1.31", "stage": "alpha", "result": "shipped"}


@pytest.mark.integration
@pytest.mark.skipif(not Path("cache/k8s/enhancements/.git").exists(), reason="no cache")
def test_real_k8s_adapter_conforms():
    conformance(_real_adapter())
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/conformance -v -m 'not integration'`
Expected: FAIL with `ModuleNotFoundError: adapters.k8s.adapter`

- [ ] **Step 4: Implement K8sAdapter**

```python
# adapters/k8s/adapter.py
"""Assembles the K8s adapter from git-history sources. Sprint 2 adds tracking-issue API events."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from core.model import Event, Milestone, OrgUnit, WorkItem
from adapters.k8s import events as ev
from adapters.k8s.config import CONFIG, REPOS
from adapters.k8s.exceptions import load_exceptions
from adapters.k8s.fetch import clone_or_update
from adapters.k8s.git_history import dir_activity, file_versions, list_kep_dirs
from adapters.k8s.kep_yaml import KepParseError, parse_kep_yaml
from adapters.k8s.milestones import build_milestones, load_calendar
from adapters.k8s.org_units import parse_sigs_yaml
from adapters.k8s.outcomes import outcome_events

CALENDAR = Path(__file__).with_name("calendar.yaml")


class K8sAdapter:
    config = CONFIG

    def __init__(self, cache_dir: Path, today: date | None = None, calendar_path: Path | None = CALENDAR):
        self.cache = cache_dir / "k8s"
        self.today = today or date.today()
        self.calendar_path = calendar_path
        self._items: list[WorkItem] | None = None
        self._base_events: list[Event] | None = None

    def fetch(self) -> None:
        for name, url in REPOS.items():
            clone_or_update(url, self.cache / name)

    def _kep_dirs(self) -> list[tuple[str, str]]:
        """(rel_dir, item_id) for every KEP dir with a numeric prefix."""
        out = []
        for d in list_kep_dirs(self.cache / "enhancements"):
            prefix = d.rsplit("/", 1)[1].split("-", 1)[0]
            if prefix.isdigit():
                out.append((d, f"k8s:kep-{int(prefix)}"))
        return out

    def work_items(self) -> list[WorkItem]:
        if self._items is None:
            repo = self.cache / "enhancements"
            items = []
            for d, item_id in self._kep_dirs():
                try:
                    title = parse_kep_yaml((repo / d / "kep.yaml").read_text()).title
                except (KepParseError, OSError):
                    title = d
                items.append(WorkItem(item_id, title, f"https://github.com/kubernetes/enhancements/tree/master/{d}"))
            self._items = sorted(items, key=lambda i: i.id)
        return self._items

    def org_units(self) -> list[OrgUnit]:
        return parse_sigs_yaml((self.cache / "community" / "sigs.yaml").read_text())

    def milestones(self) -> list[Milestone]:
        if self.calendar_path and self.calendar_path.exists():
            return load_calendar(self.calendar_path)
        return build_milestones(self.cache / "sig_release")

    def _base(self) -> list[Event]:
        if self._base_events is None:
            repo = self.cache / "enhancements"
            out: list[Event] = []
            for d, item_id in self._kep_dirs():
                sig = d.split("/")[1]
                num = item_id.rsplit("-", 1)[1]
                out += ev.kep_events(item_id, file_versions(repo, f"{d}/kep.yaml"))
                out += ev.prr_events(item_id, file_versions(repo, f"keps/prod-readiness/{sig}/{num}.yaml"))
                out += ev.activity_events(item_id, dir_activity(repo, d))
            known = {m.id for m in self.milestones()}
            out = [e for e in out if e.kind != "target_set" or e.payload["milestone_id"] in known]
            self._base_events = sorted(out, key=Event.sort_key)
        return self._base_events

    def events(self) -> list[Event]:
        base = self._base()
        outcomes = outcome_events(base, self.milestones(), load_exceptions(self.cache / "sig_release"), self.today)
        return sorted(base + outcomes, key=Event.sort_key)
```

Note the `known` filter: targets like `v1.99` or malformed values are dropped so conformance holds; count them and print in `build` (Step 6) so nothing is silently lost.

- [ ] **Step 5: Run conformance**

Run: `.venv/bin/pytest tests/conformance -v -m 'not integration'`
Expected: 1 PASS, 1 skipped/deselected. The fixture passes `calendar_path=None` so the committed real `calendar.yaml` does not shadow the fixture's README.

- [ ] **Step 6: Add `fetch` and `build` to cli.py**

Add to `cli.py`:

```python
def cmd_fetch(args) -> None:
    from adapters.k8s.adapter import K8sAdapter
    K8sAdapter(CACHE).fetch()
    print("fetched into", CACHE / "k8s")


def cmd_build(args) -> None:
    from adapters.k8s.adapter import K8sAdapter
    from core.store import Store
    a = K8sAdapter(CACHE)
    s = Store(CACHE / "store.sqlite"); s.init_schema()
    items, orgs, ms, evs = a.work_items(), a.org_units(), a.milestones(), a.events()
    s.replace_corpus("k8s", items, orgs, ms, evs)
    kinds: dict[str, int] = {}
    for e in evs:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    print(f"{len(items)} items, {len(orgs)} org units, {sum(m.is_scheduled for m in ms)} scheduled milestones, {len(evs)} events")
    print("by kind:", kinds)
```

and register them in `main()`:

```python
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    sub.add_parser("build").set_defaults(fn=cmd_build)
```

- [ ] **Step 7: Run the real thing**

Run: `.venv/bin/python cli.py fetch && .venv/bin/python cli.py build && .venv/bin/pytest tests/conformance -v -m integration`
Expected: build prints counts (expect a few hundred items, tens of thousands of events; `file_versions` shells out per version, so allow ~10–20 minutes on first run). Integration conformance PASS. If it fails, the failure message names the broken invariant — fix the adapter, not the test.

- [ ] **Step 8: Commit**

```bash
git add adapters/base.py adapters/k8s/config.py adapters/k8s/adapter.py tests/conformance cli.py
git commit -m "feat(k8s): adapter assembly, conformance suite, build command"
```

---

### Task 11: Signals S1, S5, S7 + agnosticism test

**Files:**
- Create: `signals/__init__.py`, `signals/base.py`, `signals/hollow_owner.py`, `signals/prior_slip.py`, `signals/late_target.py`
- Test: `tests/signals/__init__.py`, `tests/signals/test_agnostic.py`, `tests/signals/test_hollow_owner.py`, `tests/signals/test_prior_slip.py`, `tests/signals/test_late_target.py`

**Interfaces:**
- Consumes: `ItemState`, `Milestone`, `OrgUnit`, `AdapterConfig`, `Event`.
- Produces: `Context(as_of: datetime, milestone: Milestone, milestones_by_id: dict[str, Milestone], org_units: list[OrgUnit], config: AdapterConfig, params: dict, prior_outcomes: list[Event])`; `Signal = Callable[[dict[str, ItemState], Context], set[str]]` returning the set of firing item ids; `DEFAULT_PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}` (weeks); `SIGNALS: dict[str, Signal]` registry; `targets_at(state, milestone_id) -> list[str]` helper returning the stages targeting that milestone.

- [ ] **Step 1: Write the agnosticism test**

```python
# tests/signals/test_agnostic.py
"""signals/ must not know any corpus. This is the portability guarantee."""
from pathlib import Path
import re

def test_signals_import_no_adapters():
    root = Path(__file__).resolve().parents[2] / "signals"
    for p in root.glob("*.py"):
        src = p.read_text()
        assert not re.search(r"^\s*(from|import)\s+adapters", src, re.M), f"{p.name} imports adapters"
        assert "k8s" not in src.lower(), f"{p.name} mentions k8s"
```

- [ ] **Step 2: Write base + registry**

```python
# signals/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from adapters.base import AdapterConfig  # noqa: F401  (type only; see note)
```

**Stop** — that import violates the agnosticism test. `AdapterConfig` must move to `core`. Create `core/config.py`:

```python
# core/config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AdapterConfig:
    name: str
    required_roles: tuple[str, ...]
```

and change `adapters/base.py` to `from core.config import AdapterConfig` (re-export it there so `adapters.k8s.config` keeps working). Then:

```python
# signals/base.py
"""Signal interface. A signal is a pure function over a snapshot."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
from core.config import AdapterConfig
from core.model import Event, Milestone, OrgUnit
from core.replay import ItemState

DEFAULT_PARAMS = {"N": 8, "M": 4, "K": 3, "L": 4}


@dataclass
class Context:
    as_of: datetime
    milestone: Milestone
    milestones_by_id: dict[str, Milestone]
    org_units: list[OrgUnit]
    config: AdapterConfig
    params: dict = field(default_factory=lambda: dict(DEFAULT_PARAMS))
    prior_outcomes: list[Event] = field(default_factory=list)

    def weeks(self, key: str) -> timedelta:
        return timedelta(weeks=self.params[key])


Signal = Callable[[dict[str, ItemState], Context], set[str]]


def targets_at(state: ItemState, milestone_id: str) -> list[str]:
    return [stage for stage, m in state.targets.items() if m == milestone_id]
```

```python
# signals/__init__.py
from signals.hollow_owner import hollow_owner
from signals.prior_slip import prior_slip
from signals.late_target import late_target

SIGNALS = {"hollow_owner": hollow_owner, "prior_slip": prior_slip, "late_target": late_target}
```

- [ ] **Step 3: Write failing signal tests**

```python
# tests/signals/test_hollow_owner.py
from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.hollow_owner import hollow_owner

UTC = timezone.utc
M = Milestone("x:v1", 1, date(2024, 7, 10), date(2024, 8, 13), {})
def ctx(as_of): return Context(as_of, M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})

def item(last_activity=None, target=True):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    if target:
        s.targets["alpha"] = "x:v1"
    if last_activity:
        s.last_activity["x:unknown"] = last_activity
    return s

def test_fires_when_no_activity_in_N_weeks():
    s = item(last_activity=datetime(2024, 3, 1, tzinfo=UTC))
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == {"x:i"}

def test_quiet_when_recent_activity():
    s = item(last_activity=datetime(2024, 5, 20, tzinfo=UTC))
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == set()

def test_fires_when_never_active():
    assert hollow_owner({"x:i": item()}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == {"x:i"}

def test_ignores_items_not_targeting_milestone():
    s = item(target=False)
    assert hollow_owner({"x:i": s}, ctx(datetime(2024, 6, 1, tzinfo=UTC))) == set()
```

```python
# tests/signals/test_prior_slip.py
from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.prior_slip import prior_slip

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {})
CTX = Context(datetime(2024, 6, 1, tzinfo=UTC), M, {M.id: M}, [], AdapterConfig("x", ()))

def test_fires_when_stage_was_retargeted_before():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_history["alpha"] = ["x:v1", "x:v2"]
    assert prior_slip({"x:i": s}, CTX) == {"x:i"}

def test_quiet_on_first_target():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_history["alpha"] = ["x:v2"]
    assert prior_slip({"x:i": s}, CTX) == set()

def test_other_stage_history_does_not_count():
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["beta"] = "x:v2"; s.target_history["beta"] = ["x:v2"]; s.target_history["alpha"] = ["x:v0", "x:v1"]
    assert prior_slip({"x:i": s}, CTX) == set()
```

```python
# tests/signals/test_late_target.py
from datetime import date, datetime, timezone
from core.config import AdapterConfig
from core.model import Milestone
from core.replay import ItemState
from signals.base import Context
from signals.late_target import late_target

UTC = timezone.utc
M = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {"enhancements_freeze": date(2024, 6, 7)})
CTX = Context(datetime(2024, 6, 8, tzinfo=UTC), M, {M.id: M}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})

def _item(set_at):
    s = ItemState("x:i", datetime(2024, 1, 1, tzinfo=UTC))
    s.targets["alpha"] = "x:v2"; s.target_set_at["alpha"] = set_at
    return s

def test_fires_when_target_set_within_K_weeks_of_commitment():
    assert late_target({"x:i": _item(datetime(2024, 5, 25, tzinfo=UTC))}, CTX) == {"x:i"}

def test_quiet_when_set_early():
    assert late_target({"x:i": _item(datetime(2024, 4, 1, tzinfo=UTC))}, CTX) == set()

def test_falls_back_to_freeze_without_enhancements_freeze():
    m = Milestone("x:v2", 2, date(2024, 7, 10), date(2024, 8, 13), {})
    c = Context(datetime(2024, 7, 1, tzinfo=UTC), m, {m.id: m}, [], AdapterConfig("x", ()), {"N": 8, "M": 4, "K": 3, "L": 4})
    assert late_target({"x:i": _item(datetime(2024, 6, 25, tzinfo=UTC))}, c) == {"x:i"}
```

- [ ] **Step 4: Run to verify failures**

Run: `.venv/bin/pytest tests/signals -v`
Expected: FAIL with `ModuleNotFoundError` for each signal module.

- [ ] **Step 5: Implement the three signals**

```python
# signals/hollow_owner.py
"""S1. Hypothesis: nominal ownership without activity predicts slips.
Fires when an item targeting the milestone has had no activity from anyone in the last N weeks.
(v1 uses any actor; when actor ids are real, restrict to listed owners.)"""
from __future__ import annotations
from core.replay import ItemState
from signals.base import Context, targets_at


def hollow_owner(states: dict[str, ItemState], ctx: Context) -> set[str]:
    cutoff = ctx.as_of - ctx.weeks("N")
    out = set()
    for item_id, s in states.items():
        if not targets_at(s, ctx.milestone.id):
            continue
        last = s.last_activity_any
        if last is None or last < cutoff:
            out.add(item_id)
    return out
```

```python
# signals/prior_slip.py
"""S5. Baseline: a stage that has already been retargeted once slips again."""
from __future__ import annotations
from core.replay import ItemState
from signals.base import Context, targets_at


def prior_slip(states: dict[str, ItemState], ctx: Context) -> set[str]:
    return {item_id for item_id, s in states.items()
            if any(len(s.target_history.get(stage, [])) > 1 for stage in targets_at(s, ctx.milestone.id))}
```

```python
# signals/late_target.py
"""S7. Items whose target for this milestone was set within K weeks of the commitment point
(enhancements freeze when the milestone has one, else the delivery freeze)."""
from __future__ import annotations
from datetime import datetime, time, timezone
from core.replay import ItemState
from signals.base import Context, targets_at


def late_target(states: dict[str, ItemState], ctx: Context) -> set[str]:
    m = ctx.milestone
    commit_date = m.dates.get("enhancements_freeze") or m.freeze
    if commit_date is None:
        return set()
    cutoff = datetime.combine(commit_date, time(0, 0), tzinfo=timezone.utc) - ctx.weeks("K")
    return {item_id for item_id, s in states.items()
            if any(s.target_set_at.get(stage) is not None and s.target_set_at[stage] >= cutoff
                   for stage in targets_at(s, m.id))}
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest -m 'not integration' -v`
Expected: all PASS, including `test_agnostic`.

- [ ] **Step 7: Commit**

```bash
git add core/config.py adapters/base.py signals tests/signals
git commit -m "feat(signals): S1 hollow_owner, S5 prior_slip, S7 late_target; agnosticism test"
```

---

### Task 12: Backtest runner, metrics, CSV outputs

**Files:**
- Create: `backtest/__init__.py`, `backtest/run.py`, `backtest/metrics.py`
- Modify: `cli.py` (add `backtest`)
- Test: `tests/backtest/__init__.py`, `tests/backtest/test_run.py`, `tests/backtest/test_metrics.py`

**Interfaces:**
- Consumes: `Event`, `Milestone`, `OrgUnit`, `AdapterConfig`, `snapshot`, `SIGNALS`, `Context`, `DEFAULT_PARAMS`.
- Produces: `Row(item_id, stage, milestone_id, org_id: str | None, outcome: str | None, first_fired: dict[str, datetime | None])`; `POSITIVE = {"slipped", "dropped", "exception_denied"}`; `run_backtest(events, milestones, org_units, config, signals: dict[str, Signal], params: dict) -> list[Row]`; `signal_metrics(rows, milestones_by_id, L: int, n_boot=1000, seed=0) -> pandas.DataFrame`; `by_org(rows) -> pandas.DataFrame`; `rows_frame(rows) -> pandas.DataFrame`.

- [ ] **Step 1: Write failing runner tests**

```python
# tests/backtest/test_run.py
from datetime import date, datetime, timezone
from backtest.run import run_backtest, Row
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone

UTC = timezone.utc
def T(m, d): return datetime(2024, m, d, tzinfo=UTC)
M31 = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13),
                {"start": date(2024, 5, 13), "enhancements_freeze": date(2024, 6, 7), "code_freeze": date(2024, 7, 10), "release": date(2024, 8, 13)})
CFG = AdapterConfig("x", ())

def ev(ts, kind, payload, item="x:i1"): return Event(ts, item, kind, payload, "t")

def always(states, ctx): return set(states)
def never(states, ctx): return set()
def after_june(states, ctx): return set(states) if ctx.as_of >= T(6, 1) else set()

def base_events():
    return [ev(T(5, 1), K.TARGET_SET, {"stage": "alpha", "milestone_id": "x:v31"}),
            ev(T(5, 1), K.OWNER_CHANGED, {"subject_id": "x:org-a", "role": "owning", "op": "add"}),
            ev(T(8, 13), K.OUTCOME, {"milestone_id": "x:v31", "stage": "alpha", "result": "slipped"})]

def test_rows_and_outcomes_join():
    rows = run_backtest(base_events(), [M31], [], CFG, {"always": always, "never": never}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert len(rows) == 1
    r = rows[0]
    assert (r.item_id, r.stage, r.milestone_id, r.org_id, r.outcome) == ("x:i1", "alpha", "x:v31", "x:org-a", "slipped")
    assert r.first_fired["never"] is None
    assert r.first_fired["always"] is not None and r.first_fired["always"].date() <= date(2024, 5, 20)

def test_first_fired_is_earliest_weekly_snapshot():
    rows = run_backtest(base_events(), [M31], [], CFG, {"aj": after_june}, {"N": 8, "M": 4, "K": 3, "L": 4})
    ff = rows[0].first_fired["aj"]
    assert ff is not None and T(6, 1) <= ff < T(6, 8)

def test_outcome_before_as_of_is_not_leaked():
    evs = base_events()
    def sees_outcome(states, ctx):
        return {i for i, s in states.items() if hasattr(s, "outcome")}
    rows = run_backtest(evs, [M31], [], CFG, {"leak": sees_outcome}, {"N": 8, "M": 4, "K": 3, "L": 4})
    assert rows[0].first_fired["leak"] is None

def test_unscheduled_milestones_ignored():
    m = Milestone("x:v32", 32, None, None, {})
    assert run_backtest(base_events(), [M31, m], [], CFG, {}, {"N": 8, "M": 4, "K": 3, "L": 4})[0].milestone_id == "x:v31"
```

- [ ] **Step 2: Implement the runner**

```python
# backtest/run.py
"""Weekly snapshots per cycle → first-fired per signal → join to held-out outcomes."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from core.config import AdapterConfig
from core.model import Event, EventKind as K, Milestone, OrgUnit
from core.replay import snapshot
from signals.base import Context, Signal

POSITIVE = {"slipped", "dropped", "exception_denied"}


@dataclass
class Row:
    item_id: str
    stage: str
    milestone_id: str
    org_id: str | None
    outcome: str | None
    first_fired: dict[str, datetime | None] = field(default_factory=dict)


def _eod(d) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def run_backtest(events: list[Event], milestones: list[Milestone], org_units: list[OrgUnit], config: AdapterConfig,
                 signals: dict[str, Signal], params: dict) -> list[Row]:
    events = sorted(events, key=Event.sort_key)
    by_id = {m.id: m for m in milestones}
    outcomes = {(e.item_id, e.payload.get("stage") or "", e.payload["milestone_id"]): e for e in events if e.kind == K.OUTCOME}
    rows: list[Row] = []
    for m in sorted(milestones, key=lambda x: x.ordinal):
        ef = m.dates.get("enhancements_freeze")
        if not m.is_scheduled or ef is None:
            continue
        start = m.dates.get("start") or (m.freeze - timedelta(weeks=15))
        commit_dt, freeze_dt = _eod(ef), _eod(m.freeze)
        committed = {(iid, st) for iid, s in snapshot(events, commit_dt).items() for st, tgt in s.targets.items() if tgt == m.id}
        first: dict[tuple[str, str], dict[str, datetime | None]] = {key: {n: None for n in signals} for key in committed}
        as_of = _eod(start)
        while as_of <= freeze_dt:
            states = snapshot(events, as_of)
            prior = [e for e in events if e.kind == K.OUTCOME and e.ts <= as_of]
            ctx = Context(as_of, m, by_id, org_units, config, dict(params), prior)
            for name, fn in signals.items():
                fired = fn(states, ctx)
                for (iid, st) in committed:
                    if iid in fired and first[(iid, st)][name] is None:
                        first[(iid, st)][name] = as_of
            as_of += timedelta(weeks=1)
        final = snapshot(events, commit_dt)
        for (iid, st) in sorted(committed):
            owning = sorted(final[iid].owners.get("owning", ()))
            oc = outcomes.get((iid, st, m.id))
            rows.append(Row(iid, st, m.id, owning[0] if owning else None,
                            oc.payload["result"] if oc and oc.ts > freeze_dt else None, first[(iid, st)]))
    return rows
```

- [ ] **Step 3: Run runner tests**

Run: `.venv/bin/pytest tests/backtest/test_run.py -v`
Expected: 4 PASS

- [ ] **Step 4: Write failing metrics tests**

```python
# tests/backtest/test_metrics.py
from datetime import date, datetime, timezone
from backtest.run import Row
from backtest.metrics import signal_metrics, by_org, rows_frame
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
MS = {M.id: M}
def T(m, d): return datetime(2024, m, d, tzinfo=UTC)

def rows():
    # 4 rows: 2 slipped, 2 shipped. sig "good" fires on both slips 6 weeks early; "bad" fires on one shipped 1 week early.
    return [Row("x:a", "alpha", M.id, "x:o1", "slipped", {"good": T(5, 29), "bad": None}),
            Row("x:b", "alpha", M.id, "x:o1", "slipped", {"good": T(5, 29), "bad": None}),
            Row("x:c", "alpha", M.id, "x:o2", "shipped", {"good": None, "bad": T(7, 3)}),
            Row("x:d", "beta", M.id, "x:o2", "shipped", {"good": None, "bad": None})]

def test_metrics_table():
    df = signal_metrics(rows(), MS, L=4, n_boot=200).set_index("signal")
    g = df.loc["good"]
    assert g["fired"] == 2 and g["precision"] == 1.0 and g["recall"] == 1.0 and g["lift"] == 2.0
    assert g["median_lead_weeks"] == 6.0 and g["class"] == "risk"
    b = df.loc["bad"]
    assert b["fired"] == 1 and b["precision"] == 0.0 and b["class"] == "status"
    assert "precision_ci_lo" in df.columns and 0 <= g["precision_ci_lo"] <= g["precision_ci_hi"] <= 1

def test_by_org_counts():
    df = by_org(rows()).set_index("org_id")
    assert df.loc["x:o1", "rows"] == 2 and df.loc["x:o1", "slip_rate"] == 1.0
    assert df.loc["x:o2", "slip_rate"] == 0.0

def test_rows_frame_has_one_col_per_signal():
    df = rows_frame(rows())
    assert set(df.columns) >= {"item_id", "stage", "milestone_id", "org_id", "outcome", "first_fired.good", "first_fired.bad"}
```

- [ ] **Step 5: Implement metrics**

```python
# backtest/metrics.py
"""Per-signal precision/recall/lift/lead with bootstrap CIs. Rows without an outcome are excluded."""
from __future__ import annotations
from datetime import datetime
import numpy as np
import pandas as pd
from backtest.run import POSITIVE, Row
from core.model import Milestone


def rows_frame(rows: list[Row]) -> pd.DataFrame:
    recs = []
    for r in rows:
        d = {"item_id": r.item_id, "stage": r.stage, "milestone_id": r.milestone_id, "org_id": r.org_id, "outcome": r.outcome}
        for k, v in r.first_fired.items():
            d[f"first_fired.{k}"] = v.isoformat() if v else None
        recs.append(d)
    return pd.DataFrame(recs)


def _lead_weeks(fired: datetime, m: Milestone) -> float:
    return (m.freeze - fired.date()).days / 7


def signal_metrics(rows: list[Row], milestones_by_id: dict[str, Milestone], L: int, n_boot: int = 1000, seed: int = 0) -> pd.DataFrame:
    labeled = [r for r in rows if r.outcome is not None]
    y = np.array([r.outcome in POSITIVE for r in labeled])
    base = y.mean() if len(y) else float("nan")
    rng = np.random.default_rng(seed)
    names = sorted({k for r in labeled for k in r.first_fired})
    out = []
    for n in names:
        f = np.array([r.first_fired.get(n) is not None for r in labeled])
        fired, tp = int(f.sum()), int((f & y).sum())
        prec = tp / fired if fired else float("nan")
        rec = tp / int(y.sum()) if y.sum() else float("nan")
        lift = prec / base if fired and base else float("nan")
        leads = [_lead_weeks(r.first_fired[n], milestones_by_id[r.milestone_id]) for r in labeled if r.first_fired.get(n)]
        med = float(np.median(leads)) if leads else float("nan")
        q1, q3 = (float(np.percentile(leads, 25)), float(np.percentile(leads, 75))) if leads else (float("nan"),) * 2
        boots_p, boots_l = [], []
        for _ in range(n_boot if len(y) else 0):
            idx = rng.integers(0, len(y), len(y))
            fb, yb = f[idx], y[idx]
            if fb.sum() and yb.mean():
                pb = (fb & yb).sum() / fb.sum()
                boots_p.append(pb); boots_l.append(pb / yb.mean())
        ci = lambda xs: (float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))) if xs else (float("nan"),) * 2
        plo, phi = ci(boots_p); llo, lhi = ci(boots_l)
        out.append({"signal": n, "rows": len(labeled), "base_rate": base, "fired": fired, "precision": prec, "recall": rec,
                    "lift": lift, "median_lead_weeks": med, "lead_q1": q1, "lead_q3": q3,
                    "class": ("risk" if med >= L else "status") if leads else "n/a",
                    "precision_ci_lo": plo, "precision_ci_hi": phi, "lift_ci_lo": llo, "lift_ci_hi": lhi})
    return pd.DataFrame(out)


def by_org(rows: list[Row]) -> pd.DataFrame:
    df = rows_frame([r for r in rows if r.outcome is not None])
    if df.empty:
        return pd.DataFrame(columns=["org_id", "rows", "slips", "slip_rate"])
    df["slip"] = df["outcome"].isin(POSITIVE)
    g = df.groupby("org_id", dropna=False).agg(rows=("slip", "size"), slips=("slip", "sum")).reset_index()
    g["slip_rate"] = g["slips"] / g["rows"]
    return g.sort_values("slip_rate", ascending=False)
```

`numpy` arrives with pandas; no new dependency.

- [ ] **Step 6: Run metrics tests**

Run: `.venv/bin/pytest tests/backtest -v`
Expected: 7 PASS

- [ ] **Step 7: Add `backtest` to cli.py**

```python
def cmd_backtest(args) -> None:
    from adapters.k8s.config import CONFIG
    from backtest.metrics import by_org, rows_frame, signal_metrics
    from backtest.run import run_backtest
    from core.store import Store
    from signals import SIGNALS
    from signals.base import DEFAULT_PARAMS
    s = Store(CACHE / "store.sqlite")
    ms, orgs, evs = s.load_milestones("k8s"), s.load_org_units("k8s"), s.load_events("k8s")
    if args.min_minor:
        ms = [m for m in ms if m.ordinal >= args.min_minor or not m.is_scheduled]
    rows = run_backtest(evs, ms, orgs, CONFIG, SIGNALS, dict(DEFAULT_PARAMS))
    out = OUT / "k8s"; out.mkdir(parents=True, exist_ok=True)
    table = signal_metrics(rows, {m.id: m for m in ms}, L=DEFAULT_PARAMS["L"])
    table.to_csv(out / "signals.csv", index=False)
    rows_frame(rows).to_csv(out / "rows.csv", index=False)
    by_org(rows).to_csv(out / "by_org.csv", index=False)
    print(f"{len(rows)} rows, {sum(r.outcome is not None for r in rows)} labeled")
    print(table.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
```

Register: `bp = sub.add_parser("backtest"); bp.add_argument("--min-minor", type=int, default=26); bp.set_defaults(fn=cmd_backtest)`.

- [ ] **Step 8: Commit**

```bash
git add backtest tests/backtest cli.py
git commit -m "feat(backtest): weekly-snapshot runner, metrics with bootstrap CIs, csv outputs"
```

---

### Task 13: First real run, spec amendments, sprint-1 notes

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-program-risk-backtest-design.md` (§5 amendments), `docs/TPM_StudyGuide.md` (§3 table)
- Create: `docs/sprint-1-notes.md`, `out/k8s/signals.csv`, `out/k8s/rows.csv`, `out/k8s/by_org.csv`

- [ ] **Step 1: Run the full pipeline**

Run: `.venv/bin/python cli.py build && .venv/bin/python cli.py backtest --min-minor 26`
Expected: a rows count in the hundreds and a printed signal table. If `rows` is zero, the enhancements-freeze snapshots see no targets — check `calendar.yaml` first, then that `target_set` milestone ids match `k8s:v1.N` exactly.

- [ ] **Step 2: Sanity checks a reader will do**

Run these and paste the output into `docs/sprint-1-notes.md`:

```bash
.venv/bin/python - <<'PY'
import pandas as pd
r = pd.read_csv("out/k8s/rows.csv")
print(r.groupby("milestone_id")["outcome"].value_counts().unstack(fill_value=0))
print("base slip rate:", r["outcome"].isin(["slipped","dropped","exception_denied"]).mean())
print(r.sample(10, random_state=0)[["item_id","stage","milestone_id","outcome"]])
PY
```

For the 10 sampled rows, open the KEP on GitHub and write one line each: does the label match what actually happened? This is the first human check of the labeling rule.

- [ ] **Step 3: Write sprint-1 notes**

`docs/sprint-1-notes.md` must contain: the printed signal table; the per-milestone outcome histogram; the 10 manual label checks with a verdict each; a list titled "What v1 gets wrong" (at minimum: activity actor is unknown; shipped = not-observed-to-slip; targets dropped by the `known` filter — print the count); and the three a priori `params` values with one sentence each on why.

- [ ] **Step 4: Amend the spec**

The spec already carries an `## Amendments (planning, 2026-08-26)` section with the five corrections from the top of this plan. Add a `## Amendments (sprint 1)` section for anything the real run contradicted, and update `docs/TPM_StudyGuide.md` §3 rows for PRR, exceptions, and the calendar to "Confirmed" with the real path.

- [ ] **Step 5: Commit**

```bash
git add out/k8s/*.csv docs/sprint-1-notes.md docs/superpowers/specs docs/TPM_StudyGuide.md
git commit -m "docs: first backtest run, sprint-1 notes, spec amendments"
```

---

## Self-review against the spec

- **§3 model** → Tasks 2–4. `snapshot` returns a dict of `ItemState`, not a DataFrame (amended in Task 13).
- **§4 contract** → Task 10. `work_items()` added to the four calls (the spec omitted it; needed for conformance check 1). Conformance checks 1–6 all present in `conformance()`.
- **§5 K8s adapter** → Tasks 1, 5–10. PRR from prod-readiness files; exceptions from `exceptions.yaml`; calendar from README tables, committed and hand-verified. Tracking-issue events and dependency extraction are sprint 2–3 by design.
- **§7 signals** → Task 11 (S1, S5, S7). Agnosticism enforced by test. `AdapterConfig` moved to `core/config.py` so `signals/` never imports `adapters/`.
- **§8 backtest** → Task 12. Rows at enhancements freeze; weekly snapshots to code freeze; outcomes joined only when `ts > freeze`; bootstrap CIs; cuts by org. By-stage cut is a one-line `groupby` on `rows.csv` — deferred to sprint 2 with sensitivity grid.
- **§12 sprint 0** → Task 1 Step 8 plus the study guide reading.
- Type consistency checked: `Milestone.dates` keys `start`, `enhancements_freeze`, `code_freeze`, `release` used identically in Tasks 7, 9, 10, 11, 12. `first_fired` keyed by signal name everywhere. `Context.params` keys `N M K L`.
