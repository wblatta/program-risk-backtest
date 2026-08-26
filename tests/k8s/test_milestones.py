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

# release-1.19..release-1.23 style: abbreviated weekday, month-first, ordinal
# suffix optional, year usually absent (present only in the v1.23 rows).
SHORT_TABLE_119 = """\
| Start of Release Cycle | Lead | Mon, April 13 | week 1 | [master-blocking] |
| **Begin [Enhancements Freeze]** (EOD PST) | Enhancements Lead | Tue, May 19 | week 6 |
| **Begin [Code Freeze]** (EOD PST) | Branch Manager | Thu, July 9 | week 13 | |
| **v1.19.0 released** | Branch Manager | Wed, August 26 | week 20 | |
"""

SHORT_TABLE_121 = """\
| Start of Release Cycle | Lead | Mon January 11 | week 1 | [master-blocking] |
| **Begin [Enhancements Freeze]** (EOD PST) | Enhancements Lead | Tue February 9th | week 5 | [master-blocking], [master-informing] |
| **Begin [Code Freeze]** (EOD PST) | Branch Manager | Tue March 9 | week 9 | |
| **v1.21.0 released** | Branch Manager | Thu April 8 | week 13 | |
"""

SHORT_TABLE_122 = """\
| Start of Release Cycle | Lead | Mon April 26 | week 1 | [master-blocking] |
| **Begin [Enhancements Freeze]** (23:59 PDT) | Enhancements Lead | Thur May 13 | week 3 | [master-blocking], [master-informing] |
| **Begin [Code Freeze]** (18:00 PDT) | Branch Manager | Thur July 8 | week 11 | |
| **v1.22.0 released** | Branch Manager | Wed August 4 | week 15 | |
"""

SHORT_TABLE_123_WITH_YEAR = """\
| Start of Release Cycle | Lead | Mon August 23, 2021 | week 1 | [master-blocking] |
| **Begin [Enhancements Freeze]** (23:59 PDT) | Enhancements Lead | Thu September 9, 2021 | week 3 | [master-blocking], [master-informing] |
| **Begin [Code Freeze]** (18:00 PST) | Branch Manager | Tue November 16, 2021 | week 13 | |
| **v1.23.0 released** | Branch Manager | Tue December 7, 2021 | week 16 | |
"""


def test_parse_short_date_form_with_default_year():
    d = parse_timeline(SHORT_TABLE_119, default_year=2020, try_short_form=True)
    assert d == {"start": date(2020, 4, 13), "enhancements_freeze": date(2020, 5, 19),
                 "code_freeze": date(2020, 7, 9), "release": date(2020, 8, 26)}


def test_parse_short_date_form_ordinal_sometimes_present():
    d = parse_timeline(SHORT_TABLE_121, default_year=2021, try_short_form=True)
    assert d == {"start": date(2021, 1, 11), "enhancements_freeze": date(2021, 2, 9),
                 "code_freeze": date(2021, 3, 9), "release": date(2021, 4, 8)}


def test_parse_short_date_form_four_letter_thur():
    d = parse_timeline(SHORT_TABLE_122, default_year=2021, try_short_form=True)
    assert d == {"start": date(2021, 4, 26), "enhancements_freeze": date(2021, 5, 13),
                 "code_freeze": date(2021, 7, 8), "release": date(2021, 8, 4)}


def test_parse_short_date_form_explicit_year_needs_no_override():
    d = parse_timeline(SHORT_TABLE_123_WITH_YEAR, try_short_form=True)
    assert d == {"start": date(2021, 8, 23), "enhancements_freeze": date(2021, 9, 9),
                 "code_freeze": date(2021, 11, 16), "release": date(2021, 12, 7)}


def test_parse_short_date_form_without_default_year_does_not_guess():
    # No year anywhere in the text and none supplied: fields with no year
    # must stay unresolved rather than silently assuming one, even with
    # short-form parsing enabled.
    d = parse_timeline(SHORT_TABLE_119, try_short_form=True)
    assert d == {}


def test_parse_short_date_form_requires_explicit_opt_in():
    # Even though SHORT_TABLE_123_WITH_YEAR has explicit years in the text,
    # short-form parsing must not run unless the caller opts in -- this is
    # the mechanism that keeps _SHORT_DATE from sweeping up unrelated older
    # READMEs (e.g. release-1.15, release-1.18) that happen to contain
    # dates in a similar shape.
    d = parse_timeline(SHORT_TABLE_123_WITH_YEAR)
    assert d == {}


def test_build_milestones_resolves_short_date_releases_via_year_override(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.19").mkdir(parents=True)
    (repo / "releases" / "release-1.19" / "README.md").write_text(SHORT_TABLE_119)
    (repo / "releases" / "release-1.21").mkdir(parents=True)
    (repo / "releases" / "release-1.21" / "README.md").write_text(SHORT_TABLE_121)
    ms = build_milestones(repo, max_minor=22)
    by_id = {m.id: m for m in ms}
    assert by_id["k8s:v1.19"].freeze == date(2020, 7, 9)
    assert by_id["k8s:v1.19"].release == date(2020, 8, 26)
    assert by_id["k8s:v1.19"].dates["start"] == date(2020, 4, 13)
    assert by_id["k8s:v1.21"].freeze == date(2021, 3, 9)
    assert by_id["k8s:v1.21"].release == date(2021, 4, 8)


# Mimics the real bug found in release-1.15/release-1.18: an older README
# using the short (older) date form but WITH an explicit year in the text,
# for a minor that is not in the release-1.19..release-1.23 allow-list.
SHORT_TABLE_WITH_YEAR_OUT_OF_SCOPE = """\
| Start of Release Cycle | Lead | Mon January 1, 2019 | week 1 | |
| **Begin [Enhancements Freeze]** (EOD PST) | Enhancements Lead | Tue January 15, 2019 | week 2 | |
| **Begin [Code Freeze]** (EOD PST) | Branch Manager | Wed February 1, 2019 | week 4 | |
| **v1.14.0 released** | Branch Manager | Thu March 1, 2019 | week 8 | |
"""


def test_build_milestones_does_not_sweep_short_form_outside_named_minors(tmp_path):
    repo = tmp_path / "sig-release"
    (repo / "releases" / "release-1.14").mkdir(parents=True)
    (repo / "releases" / "release-1.14" / "README.md").write_text(SHORT_TABLE_WITH_YEAR_OUT_OF_SCOPE)
    ms = build_milestones(repo, max_minor=20)
    by_id = {m.id: m for m in ms}
    # v1.14 is outside the release-1.19..release-1.23 short-form allow-list;
    # even though this fixture's dates include an explicit year, they must
    # NOT be picked up -- short-form parsing is opt-in per named minor only.
    assert by_id["k8s:v1.14"].freeze is None
    assert by_id["k8s:v1.14"].release is None
