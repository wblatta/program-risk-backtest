"""SQLite persistence for the normalized model. One file, stdlib only."""
from __future__ import annotations
from datetime import date
import json
from pathlib import Path
import sqlite3
from typing import Iterable
from core.model import Event, Milestone, OrgUnit, WorkItem, corpus_of

_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_item (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS org_unit (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS milestone (id TEXT PRIMARY KEY, corpus TEXT NOT NULL, ordinal INTEGER NOT NULL,
    freeze TEXT, release TEXT, dates TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS event (ts TEXT NOT NULL, corpus TEXT NOT NULL, item_id TEXT NOT NULL, kind TEXT NOT NULL,
    payload TEXT NOT NULL, source TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS event_corpus_ts ON event (corpus, ts);
"""


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)

    def replace_corpus(self, corpus: str, items: Iterable[WorkItem], org_units: Iterable[OrgUnit],
                       milestones: Iterable[Milestone], events: Iterable[Event]) -> None:
        # Validation helper: materialize and validate that all ids belong to expected corpus
        def _validate_corpus_match(label: str, entity_iterable: Iterable, id_attr: str = "id") -> list:
            entity_list = list(entity_iterable)
            for entity in entity_list:
                entity_id = getattr(entity, id_attr)
                if corpus_of(entity_id) != corpus:
                    raise ValueError(f"{label} {id_attr} {entity_id!r} does not belong to corpus {corpus!r}")
            return entity_list

        # Materialize and validate all collections BEFORE touching the database
        items_list = _validate_corpus_match("work_item", items, "id")
        org_units_list = _validate_corpus_match("org_unit", org_units, "id")
        milestones_list = _validate_corpus_match("milestone", milestones, "id")
        events_list = _validate_corpus_match("event", events, "item_id")

        # Now do the database operations inside the transaction
        c = self.conn
        with c:
            for t in ("work_item", "org_unit", "milestone", "event"):
                c.execute(f"DELETE FROM {t} WHERE corpus = ?", (corpus,))
            c.executemany("INSERT INTO work_item VALUES (?,?,?,?)", [(i.id, corpus_of(i.id), i.title, i.url) for i in items_list])
            c.executemany("INSERT INTO org_unit VALUES (?,?,?)", [(o.id, corpus_of(o.id), o.name) for o in org_units_list])
            c.executemany("INSERT INTO milestone VALUES (?,?,?,?,?,?)", [
                (m.id, corpus_of(m.id), m.ordinal, m.freeze.isoformat() if m.freeze else None,
                 m.release.isoformat() if m.release else None,
                 json.dumps({k: v.isoformat() for k, v in sorted(m.dates.items())})) for m in milestones_list])
            c.executemany("INSERT INTO event VALUES (:ts,:corpus,:item_id,:kind,:payload,:source)",
                          [e.to_row() for e in sorted(events_list, key=Event.sort_key)])

    def load_items(self, corpus: str) -> list[WorkItem]:
        rows = self.conn.execute("SELECT id,title,url FROM work_item WHERE corpus=? ORDER BY id", (corpus,))
        return [WorkItem(r["id"], r["title"], r["url"]) for r in rows]

    def load_org_units(self, corpus: str) -> list[OrgUnit]:
        rows = self.conn.execute("SELECT id,name FROM org_unit WHERE corpus=? ORDER BY id", (corpus,))
        return [OrgUnit(r["id"], r["name"]) for r in rows]

    def load_milestones(self, corpus: str) -> list[Milestone]:
        rows = self.conn.execute("SELECT * FROM milestone WHERE corpus=? ORDER BY ordinal", (corpus,))
        return [Milestone(r["id"], r["ordinal"], _d(r["freeze"]), _d(r["release"]),
                          {k: date.fromisoformat(v) for k, v in json.loads(r["dates"]).items()}) for r in rows]

    def load_events(self, corpus: str) -> list[Event]:
        rows = self.conn.execute("SELECT * FROM event WHERE corpus=?", (corpus,))
        return sorted((Event.from_row(r) for r in rows), key=Event.sort_key)
