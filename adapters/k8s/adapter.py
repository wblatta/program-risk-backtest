"""Assembles the K8s adapter from git-history sources. Sprint 2 adds tracking-issue API events."""
from __future__ import annotations
from datetime import date, datetime, timezone
from pathlib import Path
from core.model import Event, EventKind as K, Milestone, OrgUnit, WorkItem
from adapters.k8s import events as ev
from adapters.k8s.config import CONFIG, REPOS
from adapters.k8s.exceptions import SkippedExceptionsFile, load_exceptions
from adapters.k8s.fetch import clone_or_update
from adapters.k8s.git_history import dir_activity, file_versions, list_kep_dirs
from adapters.k8s.kep_yaml import KepParseError, parse_kep_yaml
from adapters.k8s.milestones import build_milestones, load_calendar
from adapters.k8s.org_units import parse_sigs_yaml
from adapters.k8s.outcomes import outcome_events

CALENDAR = Path(__file__).with_name("calendar.yaml")

# A KEP whose kep.yaml declares this status is a dead end that should never win a
# kep-number collision over a sibling directory that is still (or was) live.
_COLLISION_LOSER_STATUSES = {"replaced", "superseded"}


class K8sAdapter:
    config = CONFIG

    def __init__(self, cache_dir: Path, today: date | None = None, calendar_path: Path | None = CALENDAR):
        self.cache = cache_dir / "k8s"
        # UTC, not date.today(): every timestamp in the model is UTC (Event.__post_init__
        # rejects anything else), and `today` gates which milestones are labelable at all
        # (outcomes.outcome_events skips `m.release > today`). Reading the machine's local
        # calendar date would make the corpus depend on the operator's timezone -- west of
        # UTC it lags by a day, so a build run in the evening in California and one run in
        # Berlin can label a different number of milestones from the same clone. `cli.py
        # build` prints the value it used so committed outputs stay attributable.
        self.today = today or datetime.now(timezone.utc).date()
        self.calendar_path = calendar_path
        self._items: list[WorkItem] | None = None
        self._base_events: list[Event] | None = None
        self._milestones: list[Milestone] | None = None
        self._dirs: list[tuple[str, str]] | None = None
        # Diagnostics populated as a side effect of _kep_dirs()/_base()/events();
        # populated exactly once each, since those methods cache their result.
        # See Ruling 2 and Ruling 4 (task-10 brief overrides): count and print
        # everything filtered out so nothing is silently lost.
        self.excluded_zero_dirs: list[str] = []
        self.dropped_collision_dirs: list[tuple[str, str]] = []
        self.unknown_milestone_targets: int = 0
        self.skipped_exceptions: list[SkippedExceptionsFile] = []

    def fetch(self) -> None:
        for name, url in REPOS.items():
            clone_or_update(url, self.cache / name)

    # --- KEP directory / item-id resolution (Ruling 2) ---------------------

    def _resolve_number(self, repo: Path, d: str, fallback: int) -> int:
        """kep.yaml's own kep-number when it parses and is > 0; otherwise fallback
        (the directory's numeric prefix)."""
        try:
            meta = parse_kep_yaml((repo / d / "kep.yaml").read_text())
        except (KepParseError, OSError):
            return fallback
        return meta.number if meta.number and meta.number > 0 else fallback

    def _status_of(self, repo: Path, d: str) -> str:
        try:
            return parse_kep_yaml((repo / d / "kep.yaml").read_text()).status
        except (KepParseError, OSError):
            return ""

    def _last_commit(self, repo: Path, d: str) -> datetime:
        # Directory-wide activity, not just kep.yaml's own history: a touch to any
        # file under the directory (README.md, a PRR doc, etc.) can flip a
        # collision's recency tie-break, not only an edit to kep.yaml itself. That
        # is intentional -- "most recent commit" means the directory is still
        # being maintained -- but it is a subtlety worth calling out explicitly.
        activity = dir_activity(repo, d)
        return activity[-1][0] if activity else datetime.min.replace(tzinfo=timezone.utc)

    def _pick_survivor(self, repo: Path, dirs: list[str]) -> str:
        """Of directories sharing one resolved kep-number: prefer one whose status
        is not replaced/superseded; on a further tie, the one with the most recent
        commit."""
        candidates = [d for d in dirs if self._status_of(repo, d) not in _COLLISION_LOSER_STATUSES] or dirs
        return max(candidates, key=lambda d: self._last_commit(repo, d))

    def _kep_dirs(self) -> list[tuple[str, str]]:
        """(rel_dir, item_id) for every KEP dir, deduped by kep-number.

        item_id is derived from kep.yaml's `kep-number` when the file parses and
        the number is > 0; otherwise from the directory's own numeric prefix.
        Directories resolving to 0 are process docs, not enhancements, and are
        excluded (counted in self.excluded_zero_dirs). A resolved number shared
        by more than one directory (a real anomaly in the k8s corpus: a SIG move,
        or a stale kep-number) is deduped via self._pick_survivor; every dropped
        directory is recorded in self.dropped_collision_dirs as (dropped, kept).
        """
        if self._dirs is not None:
            return self._dirs
        repo = self.cache / "enhancements"
        by_num: dict[int, list[str]] = {}
        for d in list_kep_dirs(repo):
            prefix = d.rsplit("/", 1)[1].split("-", 1)[0]
            if not prefix.isdigit():
                continue
            n = self._resolve_number(repo, d, int(prefix))
            by_num.setdefault(n, []).append(d)

        self.excluded_zero_dirs = sorted(by_num.pop(0, []))
        resolved: list[tuple[str, int]] = []
        for n, dirs in sorted(by_num.items()):
            if len(dirs) == 1:
                resolved.append((dirs[0], n))
                continue
            dirs = sorted(dirs)
            keep = self._pick_survivor(repo, dirs)
            self.dropped_collision_dirs += [(d, keep) for d in dirs if d != keep]
            resolved.append((keep, n))
        self._dirs = sorted((d, f"k8s:kep-{n}") for d, n in resolved)
        return self._dirs

    def work_items(self) -> list[WorkItem]:
        if self._items is None:
            repo = self.cache / "enhancements"
            items = []
            for d, item_id in self._kep_dirs():
                try:
                    title = parse_kep_yaml((repo / d / "kep.yaml").read_text()).title
                except (KepParseError, OSError):
                    title = d
                items.append(WorkItem(item_id, title, f"https://github.com/kubernetes/enhancements/tree/master/{d}"))
            self._items = sorted(items, key=lambda i: i.id)
        return self._items

    def org_units(self) -> list[OrgUnit]:
        return parse_sigs_yaml((self.cache / "community" / "sigs.yaml").read_text())

    def milestones(self) -> list[Milestone]:
        if self._milestones is None:
            if self.calendar_path and self.calendar_path.exists():
                self._milestones = load_calendar(self.calendar_path)
            else:
                self._milestones = build_milestones(self.cache / "sig_release")
        return self._milestones

    def _base(self) -> list[Event]:
        if self._base_events is None:
            repo = self.cache / "enhancements"
            out: list[Event] = []
            for d, item_id in self._kep_dirs():
                sig = d.split("/")[1]
                # PRR files are named after the KEP's *directory* number, not
                # kep.yaml's self-declared kep-number -- these can differ (see
                # test_item_id_uses_kep_number_not_directory_prefix / Ruling 2's
                # sig-node/2043 example, which declares kep-number 1884).
                dir_num = int(d.rsplit("/", 1)[1].split("-", 1)[0])
                out += ev.kep_events(item_id, file_versions(repo, f"{d}/kep.yaml"))
                out += ev.prr_events(item_id, file_versions(repo, f"keps/prod-readiness/{sig}/{dir_num}.yaml"))
                out += ev.activity_events(item_id, dir_activity(repo, d))
            # known-milestone filter: drops a TARGET_SET (including a clear -- see
            # Ruling 5) whose milestone_id is outside the calendar's catalog. On the
            # real corpus this reads 0, not because the filter is dead code, but
            # because the committed calendar.yaml enumerates every k8s:v1.0..v1.60
            # placeholder up front (see milestones.build_milestones's max_minor),
            # so it only fires for a value truly out of that range (e.g. a typo'd
            # "v2.1" in some kep.yaml). Counted and printed by `build` regardless.
            known = {m.id for m in self.milestones()}
            kept: list[Event] = []
            dropped = 0
            for e in out:
                if e.kind == K.TARGET_SET and e.payload["milestone_id"] not in known:
                    dropped += 1
                    continue
                kept.append(e)
            self.unknown_milestone_targets = dropped
            self._base_events = sorted(kept, key=Event.sort_key)
        return self._base_events

    def events(self) -> list[Event]:
        # _base_events is cached (it costs ~84s of rename-following git history
        # on the real corpus); the outcome layer below is cheap (well under
        # 0.1s) and is deliberately recomputed on every call rather than also
        # cached, so the conformance suite's `assert ev == adapter.events()`
        # determinism check exercises real recomputation instead of returning
        # the same cached list object to itself.
        base = self._base()
        skipped: list[SkippedExceptionsFile] = []
        exceptions = load_exceptions(self.cache / "sig_release", skipped=skipped)
        self.skipped_exceptions = skipped
        outcomes = outcome_events(base, self.milestones(), exceptions, self.today)
        return sorted(base + outcomes, key=Event.sort_key)
