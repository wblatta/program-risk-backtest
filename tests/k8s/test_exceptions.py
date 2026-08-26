from datetime import date
from adapters.k8s.exceptions import (
    parse_exceptions_yaml,
    load_exceptions,
    ExceptionRequest,
    SkippedExceptionsFile,
    UNSPECIFIED_PHASE,
)

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

# Pre-v1.24 exceptions.yaml files predate the enhancementFreeze/codeFreeze schema:
# a flat top-level list, phase recorded only in a free-text comment, sometimes also
# containing a U+200B zero-width space or outright invalid YAML syntax. Real shapes
# from the corpus: release-1.21/-1.22 (clean flat list), release-1.23 (flat list +
# ZWSP), release-1.20 (genuinely malformed, unrecoverable even after ZWSP-stripping).

def test_flat_list_schema_is_recovered_with_unspecified_phase():
    text = (
        "# Enhancements Freeze Exceptions requested in 1.21\n"
        "- name: old-format request\n"
        "  issue: 1981\n"
        "  date_requested: 2021-02-10\n"
        "  status: Approved\n"
    )
    assert parse_exceptions_yaml(text) == [
        ExceptionRequest(1981, UNSPECIFIED_PHASE, "approved", date(2021, 2, 10)),
    ]

def test_flat_list_schema_survives_zero_width_space_contamination():
    # Reproduces release-1.23: a ZWSP sits in the header comments, ahead of the
    # first list item, and corrupts the whole document unless stripped first.
    text = (
        "# Release Team Shadows: A\n"
        "​\n"
        "# Enhancements Freeze Exceptions requested in 1.23\n"
        "- name: Ceph RBD migration\n"
        "  issue: 2923\n"
        "  date_requested: 2021-09-15\n"
        "  status: approved\n"
        "​\n"
        "- name: Portworx migration\n"
        "  issue: 2589\n"
        "  status: rejected\n"
    )
    assert parse_exceptions_yaml(text) == [
        ExceptionRequest(2923, UNSPECIFIED_PHASE, "approved", date(2021, 9, 15)),
        ExceptionRequest(2589, UNSPECIFIED_PHASE, "rejected", None),
    ]

def test_invalid_yaml_yields_no_rows():
    # Reproduces the real syntax error in release-1.20/exceptions.yaml (still
    # invalid even after ZWSP-stripping -- genuinely unrecoverable): an unquoted
    # trailing comma after a quoted scalar inside a block sequence.
    text = '- name: x\n  pull_requests:\n  - "https://a", \n  - "https://b"\n  status: "approved"\n'
    assert parse_exceptions_yaml(text) == []


# --- load_exceptions: loud skip reporting ---

def _write(repo, minor, text):
    d = repo / "releases" / f"release-1.{minor}"
    d.mkdir(parents=True)
    (d / "exceptions.yaml").write_text(text)

def test_load_exceptions_reports_unparseable_file_as_skipped(tmp_path):
    repo = tmp_path / "sig-release"
    bad_text = '- name: x\n  pull_requests:\n  - "https://a", \n  status: "approved"\n'
    _write(repo, "20", bad_text)
    _write(repo, "21", "- name: ok\n  issue: 1981\n  status: approved\n")

    skipped: list[SkippedExceptionsFile] = []
    out = load_exceptions(repo, skipped=skipped)

    assert out["k8s:v1.20"] == []
    assert out["k8s:v1.21"] == [ExceptionRequest(1981, UNSPECIFIED_PHASE, "approved", None)]
    assert len(skipped) == 1
    assert skipped[0].milestone_id == "k8s:v1.20"
    assert "invalid YAML" in skipped[0].reason

def test_load_exceptions_skipped_param_is_optional_and_does_not_change_result(tmp_path):
    repo = tmp_path / "sig-release"
    _write(repo, "20", '- name: x\n  pull_requests:\n  - "https://a", \n  status: "approved"\n')
    out = load_exceptions(repo)
    assert out["k8s:v1.20"] == []

def test_load_exceptions_does_not_flag_a_genuinely_empty_file_as_skipped(tmp_path):
    repo = tmp_path / "sig-release"
    _write(repo, "25", "")
    skipped: list[SkippedExceptionsFile] = []
    out = load_exceptions(repo, skipped=skipped)
    assert out["k8s:v1.25"] == []
    assert skipped == []

def test_load_exceptions_does_not_flag_a_recovered_flat_list_file_as_skipped(tmp_path):
    repo = tmp_path / "sig-release"
    _write(repo, "21", "- name: ok\n  issue: 1981\n  status: approved\n")
    skipped: list[SkippedExceptionsFile] = []
    out = load_exceptions(repo, skipped=skipped)
    assert len(out["k8s:v1.21"]) == 1
    assert skipped == []
