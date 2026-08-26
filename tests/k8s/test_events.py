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
