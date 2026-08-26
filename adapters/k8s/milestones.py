"""Release calendar from sig-release READMEs. Generated calendar.yaml is committed and human-verified."""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
import re
import yaml
from core.model import Milestone

PREFIX = "k8s:"

# Modern form: full weekday name, day-first with ordinal suffix, explicit year.
# e.g. "Monday 19th May 2025", "Friday 20th June 2025".
_DATE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+(\d{1,2})(?:st|nd|rd|th)\s+([A-Z][a-z]+)\s+(\d{4})")

# Older form used by release-1.19..release-1.23 READMEs: abbreviated weekday
# (sometimes with a trailing comma), month-first, ordinal suffix optional,
# year optional (v1.19-v1.22 omit it everywhere; v1.23 states it explicitly).
# e.g. "Mon, April 13", "Tue October 6", "Thur May 13", "Mon August 23, 2021".
# Only tried when explicitly enabled per release (see _SHORT_FORM_MINORS) --
# this pattern is loose enough that it also matches unrelated older/irregular
# READMEs (e.g. release-1.15, release-1.18), so it must not run unconditionally.
_SHORT_DATE = re.compile(
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
    r"([A-Z][a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?"
)

_KEYS = [  # (key, line must match this regex, case-insensitive)
    ("start", r"start of release cycle"),
    ("enhancements_freeze", r"enhancements freeze"),
    ("code_freeze", r"code freeze"),
    ("release", r"\bv?1\.\d+\.0 released"),
]
_EXCLUDE = re.compile(r"coming|alpha|beta|rc\.", re.I)

# Explicit, hand-verified years for the five release-1.19..release-1.23
# READMEs, which never state a year on most rows (v1.19-v1.22) or state it
# only inconsistently. Per the "no year inference" rule, these are NOT
# derived from git history or by walking the sequence backwards from
# v1.24 -- they are the publicly documented Kubernetes release dates for
# each cycle's final "vX.Y.0 released" milestone (v1.19.0: 2020-08-26,
# v1.20.0: 2020-12-08, v1.21.0: 2021-04-08, v1.22.0: 2021-08-04,
# v1.23.0: 2021-12-07 -- the last of which is also stated explicitly in
# the v1.23 README itself), cross-checked by recomputing the weekday for
# every one of the 20 (start/enhancements_freeze/code_freeze/release)
# dates at this candidate year and confirming it matches the weekday
# name the README states for that row (see task-7-report.md).
#
# These minors are ALSO the only ones for which the short (older) date
# form is attempted at all -- see _SHORT_FORM_MINORS below. Kubernetes
# 1.3-1.18 predate the existence of kep.yaml (first one created
# 2020-03-17) and are unrecoverable for backtest purposes regardless of
# calendar accuracy, so their READMEs are deliberately left unparsed
# rather than swept up by the more permissive short-date regex.
_YEAR_OVERRIDE: dict[int, int] = {
    19: 2020,
    20: 2020,
    21: 2021,
    22: 2021,
    23: 2021,  # unused in practice: this README states its year explicitly
}

# The only minors for which _SHORT_DATE is attempted. Deliberately an
# explicit allow-list, not "does this README happen to match the loose
# short-date regex" -- older/irregular READMEs outside this range (e.g.
# release-1.15, release-1.18) can and do coincidentally match parts of
# _SHORT_DATE and must NOT be picked up as a side effect.
_SHORT_FORM_MINORS = frozenset(_YEAR_OVERRIDE)


def _first_date(line: str, default_year: int | None = None, try_short_form: bool = False) -> date | None:
    m = _DATE.search(line)
    if m:
        day, month, year = m.groups()
        return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    if not try_short_form:
        return None
    m = _SHORT_DATE.search(line)
    if not m:
        return None
    month, day, year = m.groups()
    year = year or default_year
    if year is None:
        return None  # no year in the text and none supplied: do not guess
    try:
        return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
    except ValueError:
        return None


def parse_timeline(readme: str, default_year: int | None = None, try_short_form: bool = False) -> dict[str, date]:
    out: dict[str, date] = {}
    for line in readme.splitlines():
        for key, pat in _KEYS:
            if key in out or not re.search(pat, line, re.I):
                continue
            if key in ("enhancements_freeze", "code_freeze") and _EXCLUDE.search(line):
                continue  # "Code Freeze is Coming", alpha/beta/rc rows
            if key == "release" and re.search(r"alpha|beta|rc\.", line, re.I):
                continue
            d = _first_date(line, default_year, try_short_form)
            if d:
                out[key] = d
    return out


def build_milestones(sig_release_repo: Path, max_minor: int = 60) -> list[Milestone]:
    scheduled: dict[int, dict[str, date]] = {}
    for readme in sorted((sig_release_repo / "releases").glob("release-1.*/README.md")):
        minor = int(readme.parent.name.split(".")[1])
        d = parse_timeline(
            readme.read_text(),
            default_year=_YEAR_OVERRIDE.get(minor),
            try_short_form=minor in _SHORT_FORM_MINORS,
        )
        if "code_freeze" in d and "release" in d:
            scheduled[minor] = d
    out = []
    for minor in range(0, max_minor + 1):
        d = scheduled.get(minor, {})
        out.append(Milestone(f"{PREFIX}v1.{minor}", minor, d.get("code_freeze"), d.get("release"), dict(d)))
    return out


def write_calendar(milestones: list[Milestone], path: Path) -> None:
    rows = [{"id": m.id, "ordinal": m.ordinal, "dates": {k: v.isoformat() for k, v in sorted(m.dates.items())}} for m in milestones]
    path.write_text("# Generated by adapters/k8s/milestones.py from sig-release READMEs. Verify by hand; edit if wrong.\n"
                    + yaml.safe_dump(rows, sort_keys=False))


def load_calendar(path: Path) -> list[Milestone]:
    rows = yaml.safe_load(path.read_text()) or []
    out = []
    for r in rows:
        dates = {k: date.fromisoformat(v) for k, v in (r.get("dates") or {}).items()}
        out.append(Milestone(r["id"], int(r["ordinal"]), dates.get("code_freeze"), dates.get("release"), dates))
    return out
