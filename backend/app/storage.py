"""SQLite-lagring av snapshots.

Varje gång vi pollar Svenska Spel sparar vi ett "snapshot" per utfall.
Det gör att vi kan rita oddsrörelse och streckrörelse över tid fram till
matchstart — själva kärnan i att upptäcka tecken som stärks sent.

Tabeller
--------
draws       : en rad per (product, draw_number) vi sett
snapshots   : en rad per (draw, event, sign, mättidpunkt)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .svenskaspel import Draw

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "stryktips.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    state         TEXT,
    reg_close_time TEXT,
    PRIMARY KEY (product, draw_number)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    odds          REAL,
    start_odds    REAL,
    streck        INTEGER,
    fetched_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snap_lookup
    ON snapshots (product, draw_number, event_number, sign, fetched_at);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sharp_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    odds          REAL,
    fetched_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sharpsnap_lookup
    ON sharp_snapshots (product, draw_number, event_number, sign, fetched_at);

CREATE TABLE IF NOT EXISTS sharp_odds (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    bookmaker     TEXT,
    one           REAL,
    x             REAL,
    two           REAL,
    confidence    REAL,
    matched       TEXT,
    fetched_at    TEXT,
    PRIMARY KEY (product, draw_number, event_number)
);
"""


class Storage:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def save_snapshot(self, draw: Draw) -> int:
        """Spara hela omgången som ett snapshot. Returnerar antal rader."""
        self.conn.execute(
            "INSERT INTO draws(product, draw_number, state, reg_close_time) "
            "VALUES(?,?,?,?) ON CONFLICT(product, draw_number) "
            "DO UPDATE SET state=excluded.state, reg_close_time=excluded.reg_close_time",
            (draw.product, draw.draw_number, draw.state, draw.reg_close_time),
        )
        rows = 0
        for m in draw.matches:
            for sign, o in m.outcomes.items():
                self.conn.execute(
                    "INSERT INTO snapshots(product, draw_number, event_number, sign, "
                    "odds, start_odds, streck, fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                    (draw.product, draw.draw_number, m.event_number, sign,
                     o.odds, o.start_odds, o.streck, draw.fetched_at),
                )
                rows += 1
        self.conn.commit()
        return rows

    def _latest_values(self, product: str, draw_number: int) -> dict[tuple[int, str], tuple]:
        """Senast lagrade (odds, streck) per (event, sign) för en omgång."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, streck FROM snapshots s "
            "WHERE product=? AND draw_number=? AND fetched_at = ("
            "  SELECT MAX(fetched_at) FROM snapshots WHERE product=s.product "
            "  AND draw_number=s.draw_number AND event_number=s.event_number AND sign=s.sign)",
            (product, draw_number)).fetchall()
        return {(r["event_number"], r["sign"]): (r["odds"], r["streck"]) for r in rows}

    def save_snapshot_if_changed(self, draw: Draw) -> int:
        """Spara bara de utfall som ändrats (odds eller streck) sedan senast.

        Returnerar antal sparade rader (0 = inget nytt). Håller DB:n liten
        även vid tät pollning."""
        prev = self._latest_values(draw.product, draw.draw_number)
        self.conn.execute(
            "INSERT INTO draws(product, draw_number, state, reg_close_time) "
            "VALUES(?,?,?,?) ON CONFLICT(product, draw_number) "
            "DO UPDATE SET state=excluded.state, reg_close_time=excluded.reg_close_time",
            (draw.product, draw.draw_number, draw.state, draw.reg_close_time),
        )
        rows = 0
        for m in draw.matches:
            for sign, o in m.outcomes.items():
                if prev.get((m.event_number, sign)) == (o.odds, o.streck):
                    continue  # oförändrat -> hoppa
                self.conn.execute(
                    "INSERT INTO snapshots(product, draw_number, event_number, sign, "
                    "odds, start_odds, streck, fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                    (draw.product, draw.draw_number, m.event_number, sign,
                     o.odds, o.start_odds, o.streck, draw.fetched_at),
                )
                rows += 1
        self.conn.commit()
        return rows

    def history(self, product: str, draw_number: int,
                event_number: int, sign: Optional[str] = None) -> list[dict]:
        q = ("SELECT event_number, sign, odds, streck, fetched_at FROM snapshots "
             "WHERE product=? AND draw_number=? AND event_number=?")
        args: list = [product, draw_number, event_number]
        if sign:
            q += " AND sign=?"
            args.append(sign)
        q += " ORDER BY fetched_at"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    # --- nyckel/värde-meta ---
    def meta_get(self, key: str) -> Optional[str]:
        r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    # --- sharp-odds (cache från the-odds-api) ---
    def save_sharp(self, product: str, draw_number: int, hits: list[dict]) -> int:
        """Spara/uppdatera sharp-odds per match. `hits` är poster med
        event_number, bookmaker, odds{1,X,2}, confidence, matched."""
        n = 0
        for h in hits:
            o = h.get("odds") or {}
            self.conn.execute(
                "INSERT INTO sharp_odds(product, draw_number, event_number, bookmaker, "
                "one, x, two, confidence, matched, fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(product, draw_number, event_number) DO UPDATE SET "
                "bookmaker=excluded.bookmaker, one=excluded.one, x=excluded.x, "
                "two=excluded.two, confidence=excluded.confidence, "
                "matched=excluded.matched, fetched_at=excluded.fetched_at",
                (product, draw_number, h["event_number"], h.get("bookmaker"),
                 o.get("1"), o.get("X"), o.get("2"), h.get("confidence"),
                 h.get("matched"), h.get("fetched_at")),
            )
            n += 1
        self.conn.commit()
        return n

    def save_sharp_snapshot(self, product: str, draw_number: int, hits: dict[int, dict],
                            fetched_at: str) -> int:
        """Lägg till en tidsserie-punkt för sharp-odds (Pinnacle) per utfall, men
        bara om oddset ändrats sedan senaste punkten (håller serien liten)."""
        prev = {}
        for r in self.conn.execute(
            "SELECT event_number, sign, odds FROM sharp_snapshots s WHERE product=? AND draw_number=? "
            "AND fetched_at=(SELECT MAX(fetched_at) FROM sharp_snapshots WHERE product=s.product "
            "AND draw_number=s.draw_number AND event_number=s.event_number AND sign=s.sign)",
            (product, draw_number)).fetchall():
            prev[(r["event_number"], r["sign"])] = r["odds"]
        n = 0
        for ev, h in hits.items():
            o = h.get("odds") or {}
            for sign in ("1", "X", "2"):
                val = o.get(sign)
                if val is None or prev.get((ev, sign)) == val:
                    continue
                self.conn.execute(
                    "INSERT INTO sharp_snapshots(product, draw_number, event_number, sign, odds, fetched_at) "
                    "VALUES(?,?,?,?,?,?)", (product, draw_number, ev, sign, val, fetched_at))
                n += 1
        self.conn.commit()
        return n

    def sharp_movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"]); a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["odds"], "last": r["odds"], "n": 1,
                          "min": r["odds"], "max": r["odds"]}
            else:
                a["last"], a["n"] = r["odds"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["odds"]), max(a["max"], r["odds"])
        return agg

    def sharp_history(self, product: str, draw_number: int, event_number: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT sign, odds, fetched_at FROM sharp_snapshots WHERE product=? AND draw_number=? "
            "AND event_number=? ORDER BY fetched_at", (product, draw_number, event_number)).fetchall()
        return [dict(r) for r in rows]

    def get_sharp(self, product: str, draw_number: int) -> dict[int, dict]:
        rows = self.conn.execute(
            "SELECT event_number, bookmaker, one, x, two, confidence, matched, fetched_at "
            "FROM sharp_odds WHERE product=? AND draw_number=?",
            (product, draw_number)).fetchall()
        return {r["event_number"]: {
            "odds": {"1": r["one"], "X": r["x"], "2": r["two"]},
            "bookmaker": r["bookmaker"], "confidence": r["confidence"],
            "matched": r["matched"], "fetched_at": r["fetched_at"]}
            for r in rows}

    def movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Per (event, sign): odds vid första vs senaste snapshot, antal punkter,
        samt min/max. Underlag för rörelsesignalen (stärks/försvagas över tid)."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"])
            a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["odds"], "first_t": r["fetched_at"],
                          "last": r["odds"], "last_t": r["fetched_at"],
                          "n": 1, "min": r["odds"], "max": r["odds"]}
            else:
                a["last"], a["last_t"], a["n"] = r["odds"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["odds"]), max(a["max"], r["odds"])
        return agg

    def last_snapshot(self) -> Optional[str]:
        r = self.conn.execute("SELECT MAX(fetched_at) AS m FROM snapshots").fetchone()
        return r["m"]

    def snapshot_count(self) -> int:
        r = self.conn.execute(
            "SELECT COUNT(DISTINCT fetched_at) AS c FROM snapshots").fetchone()
        return r["c"]

    def snapshot_times(self, product: str, draw_number: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT fetched_at FROM snapshots WHERE product=? AND draw_number=? "
            "ORDER BY fetched_at", (product, draw_number)).fetchall()
        return [r["fetched_at"] for r in rows]
