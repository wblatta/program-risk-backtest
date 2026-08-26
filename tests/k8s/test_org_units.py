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
