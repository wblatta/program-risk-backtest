from datetime import date
from pathlib import Path
from adapters.k8s.milestones import parse_timeline, build_milestones, write_calendar, load_calendar

TABLE = """\
| **What** | **Who** | **When** | **Week** |
| Start of Release Cycle | Lead | Monday 19th May 2025 | week 1 |
| **Begin [Production Readiness Freeze]** | Enhancements Lead | Thursday 12th June 2025 | week 4 |
| **Begin [Enhancements Freeze]** | Enhancements Lead | [21:00 UTC Friday 20th June 2025 / 14:00 PST Friday 20th June 2025](https://x) | week 5 |
| v1.34.0-alpha.3 released | Branch Manager | Wednesday 9th July 2025 | week 8 |
| **Begin [Code Freeze] and [Test Freeze]** | Branch Manager | [02:00 UTC Friday 25th July 2025 / 19:00 PDT Thursday 24th July 2025](https://y) | week 10 |
| v1.34.0-rc.0 released | Branch Manager | Wednesday 6th August 2025 | week 12 |
| **v1.34.0 released** | Branch Manager | Wednesday 27th August 2025 | week 15 |
"""

BULLETS_128 = """\
- **[01:00 UTC Friday 16th June 2023 / 18:00 PDT Thursday 15th June 2023](https://a)**: Week 5 — [Enhancements Freeze](../release_phases.md#enhancements-freeze)
- **[01:00 UTC Wednesday 19th July 2023 / 18:00 PDT Tuesday 18th July 2023](https://b)**: Week 10 — [Code Freeze](../release_phases.md#code-freeze)
- **Tuesday 15th August 2023**: Week 14 — Kubernetes v1.28.0 released
| Start of Release Cycle | Lead | Monday 15th May 2023 | week 1 |
"""

def test_parse_table_form():
    d = parse_timeline(TABLE)
    assert d == {"start": date(2025, 5, 19), "enhancements_freeze": date(2025, 6, 20),
                 "code_freeze": date(2025, 7, 25), "release": date(2025, 8, 27)}

def test_parse_bullet_form():
    d = parse_timeline(BULLETS_128)
    assert d["enhancements_freeze"] == date(2023, 6, 16)
    assert d["code_freeze"] == date(2023, 7, 19)
    assert d["release"] == date(2023, 8, 15)
    assert d["start"] == date(2023, 5, 15)

def test_build_from_repo_with_placeholders(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.34").mkdir(parents=True)
    (repo / "releases" / "release-1.34" / "README.md").write_text(TABLE)
    ms = build_milestones(repo, max_minor=36)
    by_id = {m.id: m for m in ms}
    assert by_id["k8s:v1.34"].freeze == date(2025, 7, 25)
    assert by_id["k8s:v1.34"].release == date(2025, 8, 27)
    assert by_id["k8s:v1.34"].dates["enhancements_freeze"] == date(2025, 6, 20)
    assert by_id["k8s:v1.34"].ordinal == 34
    assert by_id["k8s:v1.35"].freeze is None and by_id["k8s:v1.0"].ordinal == 0
    assert len(ms) == 37

def test_calendar_round_trip(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.34").mkdir(parents=True)
    (repo / "releases" / "release-1.34" / "README.md").write_text(TABLE)
    ms = build_milestones(repo, max_minor=36)
    p = tmp_path / "calendar.yaml"
    write_calendar(ms, p)
    assert load_calendar(p) == ms
