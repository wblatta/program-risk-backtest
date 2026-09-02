from datetime import date, datetime, timezone
import pandas as pd
from backtest.register import RegisterLine, build_register, format_register
from core.model import Milestone

UTC = timezone.utc
M = Milestone("x:v31", 31, date(2024, 7, 10), date(2024, 8, 13), {})
METRICS = pd.DataFrame([
    {"cut": "evidenced", "signal": "item_silent", "precision": 0.84, "lift": 2.14, "lead_class": "risk"},
    {"cut": "evidenced", "signal": "gate_unassigned", "precision": 0.73, "lift": 1.87, "lead_class": "status"},
    {"cut": "evidenced", "signal": "cross_org", "precision": 0.41, "lift": 1.05, "lead_class": "risk"},
])


def test_groups_firings_by_lead_class():
    """Spec §9: 'Split into two sections by lead_class: risk and status.' The split is
    the product -- it separates what you can still act on from what only reports."""
    reg = build_register({("x:i", "alpha"): ["item_silent", "gate_unassigned"]}, METRICS, M)
    line = reg[0]
    assert [s.name for s in line.risk] == ["item_silent"]
    assert [s.name for s in line.status] == ["gate_unassigned"]

def test_annotates_each_signal_with_its_backtest_precision():
    reg = build_register({("x:i", "alpha"): ["item_silent"]}, METRICS, M)
    assert reg[0].risk[0].precision == 0.84 and reg[0].risk[0].lift == 2.14

def test_orders_signals_by_precision_within_a_section():
    reg = build_register({("x:i", "alpha"): ["cross_org", "item_silent"]}, METRICS, M)
    assert [s.name for s in reg[0].risk] == ["item_silent", "cross_org"]

def test_orders_rows_by_their_strongest_risk_signal():
    """A register a reader scans top-down has to put the most-precise firing first."""
    firing = {("x:a", "alpha"): ["cross_org"], ("x:b", "alpha"): ["item_silent"]}
    assert [l.item_id for l in build_register(firing, METRICS, M)] == ["x:b", "x:a"]

def test_rows_with_no_firings_are_omitted():
    assert build_register({("x:i", "alpha"): []}, METRICS, M) == []

def test_unbacktested_signal_is_kept_but_unannotated():
    """A signal with no backtest row must not be silently dropped -- it fired. It is
    reported without a precision, which is honest, rather than with a fabricated one."""
    reg = build_register({("x:i", "alpha"): ["brand_new"]}, METRICS, M)
    assert reg[0].status[0].name == "brand_new" and reg[0].status[0].precision is None

def test_format_states_the_milestone_and_both_sections():
    out = format_register(build_register({("x:i", "alpha"): ["item_silent", "gate_unassigned"]}, METRICS, M), M)
    assert "x:v31" in out and "risk" in out and "status" in out and "item_silent" in out
    assert "0.84" in out

def test_format_says_so_when_nothing_fires():
    assert "no signals firing" in format_register([], M).lower()
