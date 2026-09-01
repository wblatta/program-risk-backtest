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

def test_invalid_calendar_date_raises_kep_parse_error():
    # Real-world case found in the ingestion spike: PyYAML's implicit
    # timestamp resolver raises a bare ValueError (not yaml.YAMLError) for
    # a date with an out-of-range month, e.g. kubernetes/enhancements'
    # keps/sig-api-machinery/4355-coordinated-leader-election/kep.yaml has
    # "creation-date: 2023-14-05".
    with pytest.raises(KepParseError):
        parse_kep_yaml("title: X\nowning-sig: sig-a\nstatus: provisional\ncreation-date: 2023-14-05\n")

def test_non_mapping_raises():
    with pytest.raises(KepParseError):
        parse_kep_yaml("- just\n- a list\n")
