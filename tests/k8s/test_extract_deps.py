from datetime import datetime, timezone
from adapters.k8s.extract_deps import (LINK_CONFIDENCE, PROSE_CONFIDENCE, extract_prose_deps,
                                       link_dep_events, prose_dep_events)

UTC = timezone.utc
T = datetime(2024, 3, 1, tzinfo=UTC)


# --- prose -------------------------------------------------------------------

def test_extracts_an_explicit_dependency_sentence():
    assert extract_prose_deps("This KEP depends on KEP-1234 landing first.", "999") == {"1234": PROSE_CONFIDENCE}

def test_ignores_a_bare_mention_with_no_dependency_language():
    """Most KEP cross-references in this corpus are 'related work', not dependencies.
    Treating a mention as an edge is how a dependency graph becomes a citation graph."""
    assert extract_prose_deps("It also aligns with the extensions outlined in KEP-365.", "999") == {}

def test_ignores_a_reference_to_itself():
    """Every README opens with `# KEP-1234: Title`, so self-reference is the single most
    common match in the corpus and means nothing."""
    assert extract_prose_deps("# KEP-999: Thing\nThis depends on KEP-999 obviously.", "999") == {}

def test_requires_the_cue_and_the_reference_in_the_same_sentence():
    """Across a paragraph boundary the cue does not govern the reference."""
    text = "This work requires careful review. Separately, KEP-1234 exists."
    assert extract_prose_deps(text, "999") == {}

def test_recognises_the_common_cue_vocabulary():
    for cue in ("depends on", "is blocked by", "is a prerequisite for", "requires", "builds on top of"):
        assert extract_prose_deps(f"This {cue} KEP-1234.", "999") == {"1234": PROSE_CONFIDENCE}, cue

def test_multiple_dependencies_in_one_document():
    assert extract_prose_deps("Depends on KEP-1234 and KEP-5678.", "999") == {
        "1234": PROSE_CONFIDENCE, "5678": PROSE_CONFIDENCE}


# --- prose events ------------------------------------------------------------

class V:
    def __init__(self, ts, text): self.ts, self.text = ts, text


def test_prose_events_emit_add_on_first_appearance():
    evs = prose_dep_events("k8s:kep-999", [V(T, "Depends on KEP-1234.")])
    assert len(evs) == 1
    e = evs[0]
    assert e.kind == "dependency_changed" and e.source == "llm"
    assert e.payload == {"depends_on_id": "k8s:kep-1234", "op": "add",
                         "confidence": PROSE_CONFIDENCE, "extractor": "prose-cue-v1"}

def test_prose_events_emit_remove_when_a_dependency_disappears():
    """The graph is point-in-time like everything else: a dependency dropped from a later
    README version must stop being in force, not persist forever."""
    vs = [V(T, "Depends on KEP-1234."), V(datetime(2024, 6, 1, tzinfo=UTC), "No dependencies now.")]
    ops = [(e.payload["op"], e.payload["depends_on_id"]) for e in prose_dep_events("k8s:kep-999", vs)]
    assert ops == [("add", "k8s:kep-1234"), ("remove", "k8s:kep-1234")]

def test_prose_events_do_not_repeat_an_unchanged_dependency():
    vs = [V(T, "Depends on KEP-1234."), V(datetime(2024, 6, 1, tzinfo=UTC), "Still depends on KEP-1234.")]
    assert len(prose_dep_events("k8s:kep-999", vs)) == 1


# --- links -------------------------------------------------------------------

def _xref(number, when="2024-03-01T00:00:00Z", repo="kubernetes/enhancements"):
    return {"event": "cross-referenced", "created_at": when,
            "source": {"issue": {"number": number, "repository": {"full_name": repo}}}}


def test_link_events_use_tracking_issue_cross_references():
    evs = link_dep_events("k8s:kep-999", [_xref(1234)], {1234})
    assert [e.payload["depends_on_id"] for e in evs] == ["k8s:kep-1234"]
    assert evs[0].payload["confidence"] == LINK_CONFIDENCE and evs[0].source == "tracking-issue"

def test_link_events_ignore_references_to_non_keps():
    """Most cross-references point at kubernetes/kubernetes PRs, which are implementation,
    not dependency."""
    assert link_dep_events("k8s:kep-999", [_xref(4567, repo="kubernetes/kubernetes")], {4567}) == []

def test_link_events_ignore_issues_that_are_not_tracking_issues():
    assert link_dep_events("k8s:kep-999", [_xref(1234)], set()) == []

def test_link_events_ignore_self_reference():
    assert link_dep_events("k8s:kep-999", [_xref(999)], {999}) == []

def test_link_confidence_is_below_prose_confidence():
    """A cross-reference proves two enhancements were mentioned together. It does not say
    the relation is a dependency, so it cannot be asserted as strongly as an explicit
    'depends on'."""
    assert LINK_CONFIDENCE < PROSE_CONFIDENCE
