"""Dependency extraction — spec §14 open question 4, answered against the corpus.

*"How KEP READMEs phrase dependencies — pattern or LLM."* This was a sprint-0 question
that sprint 0 never answered. Measured now, over 617 enhancement READMEs:

- **109 (18%) reference another KEP at all.** The other 82% name no sibling anywhere in
  their prose, so no extractor of any kind has an edge to find.
- Of the references that exist, the largest single context is the document's own title
  (`# KEP-1234: Title`), and most of the rest read as related work — *"it also aligns
  with the extensions outlined in KEP-365"*, *"closely related KEP-3329"*. These are
  citations, not dependencies.
- The tracking issues carry 164 KEP-to-KEP cross-references across 125 issues, which is
  slightly better coverage than prose and typed by construction as *a link* — but GitHub
  cross-references have no relation type either.

**So the answer is neither.** The choice between pattern and LLM is not what limits this:
the corpus does not record dependencies in a recoverable form, and an LLM cannot extract a
relation the source never states. What an LLM would buy over the patterns here is better
discrimination between "depends on" and "related to" *within the 18%* — a real gain on a
small base, not a way past the base. That is the coverage ceiling, and it is the same
ceiling the finding names as this project's actual bottleneck.

Both extractors are built anyway, because a low-coverage graph still lets H2 be tested
rather than left open, and because a measured ceiling is a result. Every edge carries a
`confidence` and the `extractor` that produced it, per the event schema in spec §3, so a
consumer can weigh them and a later LLM extractor can be compared against these directly.

`source = llm` on prose events is the spec's vocabulary for extracted-from-prose, kept so
that swapping this extractor for a model changes the extractor, not the schema.
"""
from __future__ import annotations

import re

# Explicit dependency language. Deliberately narrow: the corpus's characteristic failure
# is a bare mention being read as an edge, so the cue must be present and must govern the
# reference. Precision over recall -- a citation graph mislabeled as a dependency graph
# would make S4a/S4b measure something other than H2.
CUES = re.compile(
    r"\b(depends?\s+(?:up)?on|depend(?:ent|ing)\s+(?:up)?on|blocked\s+by|blocks\b"
    r"|requires?|required\s+by|prerequisite|pre-requisite|builds?\s+on(?:\s+top\s+of)?"
    r"|needs?\b|waiting\s+(?:on|for)|gated\s+(?:on|by)|contingent\s+(?:on|upon))",
    re.I)

KEP_REF = re.compile(r"\bkep[-\s]?(\d{3,4})\b", re.I)

# A cue governs a reference only inside one sentence. Splitting on sentence enders and on
# markdown structure (list items, headings, table rows) stops a cue from reaching across a
# bullet list, which is where most false edges came from.
_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n\s*[-*+|#>]+\s*|\n{2,}")

# An explicit "depends on KEP-N" is a strong claim about a relation. A cross-reference is
# evidence only that two enhancements were mentioned together -- the relation type is
# unknown, and it might be "duplicate of" or "see also". They must not be asserted equally.
PROSE_CONFIDENCE = 0.7
LINK_CONFIDENCE = 0.3

PREFIX = "k8s:kep-"


def extract_prose_deps(text: str, own_number: str) -> dict[str, float]:
    """KEP numbers this document claims to depend on, mapped to a confidence.

    A reference counts only when a dependency cue appears in the same sentence. Self-
    references are dropped: every README opens with its own `# KEP-N: Title`, making self
    the single most common match in the corpus and the least informative.
    """
    found: dict[str, float] = {}
    for chunk in _SPLIT.split(text or ""):
        if not CUES.search(chunk):
            continue
        for number in KEP_REF.findall(chunk):
            if number.lstrip("0") != str(own_number).lstrip("0"):
                found[number] = PROSE_CONFIDENCE
    return found


def _diff_events(item_id: str, ts, before: dict[str, float], after: dict[str, float],
                 confidence: float, extractor: str, source: str) -> list:
    from core.model import Event, EventKind as K
    out = []
    for n in sorted(set(after) - set(before)):
        out.append(Event(ts, item_id, K.DEPENDENCY_CHANGED,
                         {"depends_on_id": PREFIX + n, "op": "add",
                          "confidence": confidence, "extractor": extractor}, source))
    for n in sorted(set(before) - set(after)):
        out.append(Event(ts, item_id, K.DEPENDENCY_CHANGED,
                         {"depends_on_id": PREFIX + n, "op": "remove",
                          "confidence": confidence, "extractor": extractor}, source))
    return out


def prose_dep_events(item_id: str, versions) -> list:
    """Dependency add/remove events across a README's version history.

    Diffed version to version rather than emitted per version: the graph is point-in-time
    like every other fact here, so a dependency dropped from a later revision has to stop
    being in force. Emitting an `add` per version instead would make every edge permanent
    and let a resolved dependency keep firing S4 for years.
    """
    own = _kep_number(item_id)
    out, prev = [], {}
    for v in versions:
        cur = extract_prose_deps(getattr(v, "text", "") or "", own)
        out.extend(_diff_events(item_id, v.ts, prev, cur, PROSE_CONFIDENCE, "prose-cue-v1", "llm"))
        prev = cur
    return out


def link_dep_events(item_id: str, timeline, tracking_numbers: set[int], repo: str = "kubernetes/enhancements") -> list:
    """Tracking-issue cross-references to other tracking issues, as low-confidence edges.

    Restricted to issues that are themselves KEP tracking issues: the overwhelming
    majority of cross-references point at `kubernetes/kubernetes` PRs, which are this
    enhancement's own implementation rather than a relation to another enhancement.
    """
    from core.model import Event, EventKind as K
    from adapters.k8s.tracking import _ts
    own = int(_kep_number(item_id))
    out, seen = [], set()
    for e in timeline or []:
        if not isinstance(e, dict) or e.get("event") != "cross-referenced":
            continue
        issue = (e.get("source") or {}).get("issue") or {}
        number = issue.get("number")
        if (issue.get("repository") or {}).get("full_name") != repo:
            continue
        if not isinstance(number, int) or number == own or number not in tracking_numbers:
            continue
        ts = _ts(e.get("created_at"))
        if ts is None or number in seen:
            continue
        seen.add(number)
        out.append(Event(ts, item_id, K.DEPENDENCY_CHANGED,
                         {"depends_on_id": f"{PREFIX}{number}", "op": "add",
                          "confidence": LINK_CONFIDENCE, "extractor": "issue-xref-v1"},
                         "tracking-issue"))
    return sorted(out, key=lambda x: (x.ts, x.payload["depends_on_id"]))


def _kep_number(item_id: str) -> str:
    return item_id.rsplit("-", 1)[-1]
