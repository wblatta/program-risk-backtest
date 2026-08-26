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

# Pre-v1.24 exceptions.yaml files predate the enhancementFreeze/codeFreeze schema:
# a bare top-level list, sometimes with outright invalid YAML syntax. Real examples
# on the corpus (release-1.16, release-1.20). Out of schema -- no rows, no crash.

def test_bare_top_level_list_yields_no_rows():
    assert parse_exceptions_yaml("- name: old-format\n  issue: 123\n  status: Denied\n") == []

def test_invalid_yaml_yields_no_rows():
    # Reproduces the real syntax error in release-1.20/exceptions.yaml: an unquoted
    # trailing comma after a quoted scalar inside a block sequence.
    text = '- name: x\n  pull_requests:\n  - "https://a", \n  - "https://b"\n  status: "approved"\n'
    assert parse_exceptions_yaml(text) == []
