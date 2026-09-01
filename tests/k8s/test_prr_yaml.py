from adapters.k8s.prr_yaml import parse_prr_yaml

def test_parses_stage_approvers():
    text = 'kep-number: 2400\nalpha:\n  approver: "@Deads2k"\nbeta:\n  approver: "@deads2k"\nstable:\n  approver: TBD\n'
    assert parse_prr_yaml(text) == {"alpha": "@deads2k", "beta": "@deads2k"}

def test_garbage_is_empty():
    assert parse_prr_yaml("- nope") == {}
    assert parse_prr_yaml(": [") == {}
