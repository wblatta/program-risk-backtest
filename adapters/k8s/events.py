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
        # A stage present in the previous version but absent from the current one is a
        # retracted commitment, not a no-op: snapshot() must stop reporting it as targeted
        # rather than leaving the stale milestone in place forever. Keep the milestone_id
        # of the milestone being cleared (not None) so downstream TARGET_SET consumers that
        # key off milestone_id keep working unchanged.
        for stage in sorted(set(prev_ms) - set(cur.milestones)):
            out.append(Event(v.ts, item_id, K.TARGET_SET, {"stage": stage, "milestone_id": milestone_id(prev_ms[stage]), "op": "clear"}, SRC))
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
