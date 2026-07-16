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

import contextlib
import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

from .svenskaspel import Draw

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "stryktips.db"

PREDICTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_prediction_capture (
    match_id       TEXT NOT NULL,
    horizon        TEXT NOT NULL,          -- h24 | h3 | m20
    tier           TEXT NOT NULL,          -- sharp | model
    signal_version TEXT NOT NULL,
    base_version   TEXT NOT NULL,
    match_start    TEXT NOT NULL,
    target_at      TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    offset_minutes REAL NOT NULL,          -- faktisk tid kvar till avspark
    delay_minutes  REAL NOT NULL,          -- hur sent efter nominell horisont
    row_count      INTEGER NOT NULL,
    PRIMARY KEY (match_id, horizon, tier, signal_version)
);

CREATE TABLE IF NOT EXISTS oddset_prediction_log (
    match_id       TEXT NOT NULL,
    horizon        TEXT NOT NULL,
    tier           TEXT NOT NULL,
    market         TEXT NOT NULL,
    sign           TEXT NOT NULL,
    line           REAL,
    line_key       INTEGER NOT NULL,
    league         TEXT,
    description    TEXT,
    match_start    TEXT NOT NULL,
    target_at      TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    offset_minutes REAL NOT NULL,
    fair_prob      REAL NOT NULL,
    fair_source    TEXT NOT NULL,           -- pinnacle | derived | model
    fair_available INTEGER NOT NULL,
    fair_fresh     INTEGER NOT NULL,
    model_anchored INTEGER,
    book           TEXT,
    book_odds      REAL,
    book_available INTEGER NOT NULL,
    book_fresh     INTEGER NOT NULL,
    edge           REAL,
    eligible       INTEGER NOT NULL,        -- får ingå i signalutvärdering
    is_flag        INTEGER NOT NULL,        -- förregistrerad regel vid capture
    signal_version TEXT NOT NULL,
    base_version   TEXT NOT NULL,
    git_hash       TEXT,
    closing_fair   REAL,
    closing_odds   REAL,
    closing_line   REAL,
    line_delta     REAL,
    line_move_score REAL,
    closing_note   TEXT,
    PRIMARY KEY (match_id, horizon, tier, market, sign, signal_version)
);
CREATE INDEX IF NOT EXISTS idx_prediction_open
    ON oddset_prediction_log (match_start, closing_fair, closing_note);
CREATE INDEX IF NOT EXISTS idx_prediction_group
    ON oddset_prediction_log (tier, league, market, signal_version, is_flag);

CREATE TABLE IF NOT EXISTS oddset_prediction_group_state (
    tier           TEXT NOT NULL,
    league         TEXT NOT NULL,
    market         TEXT NOT NULL,
    signal_version TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'amber',
    candidate_at   TEXT,
    green_at       TEXT,
    PRIMARY KEY (tier, league, market, signal_version)
);
"""

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

-- Flaggade värdetecken (CLV-facit): first/best per selektion + devigad
-- Pinnacle-stängning före avspark + facit. Positiv snitt-CLV = signalen äkta.
CREATE TABLE IF NOT EXISTS value_log (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    description   TEXT,
    match_start   TEXT,
    flag_type     TEXT,
    first_at      TEXT,
    first_odds    REAL,
    first_prob    REAL,
    prob_src      TEXT,
    first_streck  INTEGER,
    first_ratio   REAL,
    best_ratio    REAL,
    best_at       TEXT,
    closing_prob  REAL,
    closing_odds  REAL,
    closing_note  TEXT,
    outcome       INTEGER,
    PRIMARY KEY (product, draw_number, event_number, sign)
);

-- Oddset-delen (enskilda matcher, se app/oddset.py)
CREATE TABLE IF NOT EXISTS oddset_matches (
    id           TEXT PRIMARY KEY,      -- 'pin:<matchupId>' | 'svs:<eventId>'
    league       TEXT NOT NULL,         -- nyckel i oddset.LEAGUES
    home         TEXT NOT NULL,
    away         TEXT NOT NULL,
    start        TEXT,                  -- UTC ISO
    pinnacle_id  TEXT,
    kambi_id     TEXT,
    status       TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_oddset_matches_start ON oddset_matches (start);

CREATE TABLE IF NOT EXISTS oddset_odds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    TEXT NOT NULL,
    source      TEXT NOT NULL,          -- 'pinnacle' | 'derived' | 'svenskaspel'
    market      TEXT NOT NULL,          -- '1x2' | 'ah' | 'ou'
    sign        TEXT NOT NULL,          -- 1x2: 1/X/2 · ah: H/A · ou: O/U
    line        REAL,                   -- handikapp (hemmaperspektiv) / totallinje
    odds        REAL,
    fetched_at  TEXT NOT NULL,          -- när just detta pris/denna linje först sågs
    last_seen_at TEXT NOT NULL,         -- senaste lyckade svar som fortfarande bar priset
    available   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_oddset_odds
    ON oddset_odds (match_id, source, market, sign, fetched_at);

CREATE TABLE IF NOT EXISTS oddset_source_health (
    source       TEXT NOT NULL,
    league       TEXT NOT NULL,
    scope        TEXT NOT NULL,          -- 1x2 | markets | deep
    checked_at   TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    event_count  INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    PRIMARY KEY (source, league, scope)
);

CREATE TABLE IF NOT EXISTS oddset_results (
    league    TEXT NOT NULL,
    date      TEXT NOT NULL,            -- YYYY-MM-DD
    home      TEXT NOT NULL,            -- normaliserat (oddset.norm_team)
    away      TEXT NOT NULL,
    home_raw  TEXT,
    away_raw  TEXT,
    hg INTEGER, ag INTEGER,
    xg_h REAL, xg_a REAL,
    cor_h REAL, cor_a REAL,
    source    TEXT,
    PRIMARY KEY (league, date, home, away)
);

CREATE TABLE IF NOT EXISTS oddset_value_log (
    match_id     TEXT NOT NULL,
    market       TEXT NOT NULL,
    sign         TEXT NOT NULL,
    line         REAL,
    line_key     INTEGER NOT NULL,       -- round(line*1000), sentinel för 1X2
    league       TEXT,
    description  TEXT,
    match_start  TEXT,
    first_at     TEXT,
    first_odds   REAL,
    first_fair   REAL,
    first_edge   REAL,
    best_edge    REAL,
    best_at      TEXT,
    closing_fair REAL,
    closing_odds REAL,
    closing_line REAL,
    line_delta   REAL,
    line_move_score REAL,                -- >0 = linan rörde sig med selektionen
    closing_note TEXT,
    book         TEXT,
    tier         TEXT DEFAULT 'sharp',
    model_version TEXT NOT NULL DEFAULT 'legacy',
    git_hash     TEXT,
    PRIMARY KEY (match_id, market, sign, line_key, model_version)
);
""" + PREDICTION_SCHEMA


class Storage:
    ODDSET_NO_LINE_KEY = 2_147_483_647

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._bulk = False
        # WP0 (granskningen): WAL = läsare blockeras inte av skrivare (API:t +
        # 25-min-smartpasset kör parallellt); busy_timeout i stället för
        # "database is locked" vid krock.
        self.conn = sqlite3.connect(self.db_path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA)
        for mig in ("ALTER TABLE oddset_value_log ADD COLUMN book TEXT",
                    "ALTER TABLE oddset_value_log ADD COLUMN tier TEXT DEFAULT 'sharp'",
                    "ALTER TABLE oddset_value_log ADD COLUMN model_version TEXT",
                    "ALTER TABLE oddset_value_log ADD COLUMN git_hash TEXT",
                    "ALTER TABLE oddset_odds ADD COLUMN last_seen_at TEXT",
                    "ALTER TABLE oddset_odds ADD COLUMN available INTEGER NOT NULL DEFAULT 1"):
            try:   # migreringar för befintliga DB:er
                self.conn.execute(mig)
            except sqlite3.OperationalError:
                pass
        # Befintliga prisrader saknar observationsklocka. Första migreringen
        # utgår konservativt från prisets egen tid; nästa lyckade poll flyttar
        # last_seen_at utan att skapa en falsk rörelsepunkt.
        self.conn.execute(
            "UPDATE oddset_odds SET last_seen_at=fetched_at WHERE last_seen_at IS NULL")
        self._commit()

    def close(self) -> None:
        self.conn.close()

    def _commit(self) -> None:
        """Commit per operation — utom inne i bulk(), då committas allt på slutet."""
        if not self._bulk:
            self.conn.commit()

    @contextlib.contextmanager
    def bulk(self):
        """Batcha många skrivningar i EN transaktion (WP0) — commit per rad gav
        ~1 700 commits per football-data-refresh. Rollback vid fel."""
        self._bulk = True
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self._bulk = False

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
        self._commit()
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
        self._commit()
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
        self._commit()

    def meta_delete(self, key: str) -> None:
        self.conn.execute("DELETE FROM meta WHERE key=?", (key,))
        self._commit()

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
        self._commit()
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
        self._commit()
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
                agg[k] = {"first": r["odds"], "first_t": r["fetched_at"],
                          "last": r["odds"], "last_t": r["fetched_at"], "n": 1,
                          "min": r["odds"], "max": r["odds"]}
            else:
                a["last"], a["last_t"], a["n"] = r["odds"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["odds"]), max(a["max"], r["odds"])
        return agg

    def sharp_history_all(self, product: str, draw_number: int) -> list[dict]:
        """Hela sharp-serien för en omgång (alla matcher/tecken, tidsordnad) —
        underlag för steam-beräkningen (devigade skift över tidsfönster)."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        return [dict(r) for r in rows]

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

    def streck_movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Per (event, sign): folkets streck vid första vs senaste snapshot.
        Underlag för att flagga matcher där folket svängt markant."""
        rows = self.conn.execute(
            "SELECT event_number, sign, streck, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND streck IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"]); a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["streck"], "first_t": r["fetched_at"],
                          "last": r["streck"], "last_t": r["fetched_at"],
                          "n": 1, "min": r["streck"], "max": r["streck"]}
            else:
                a["last"], a["last_t"], a["n"] = r["streck"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["streck"]), max(a["max"], r["streck"])
        return agg

    def odds_series(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Hela oddsserien per (event, sign) för både SvS och Pinnacle —
        underlag för rörelse-tooltipen (alla mätpunkter + min/max)."""
        out: dict[tuple[int, str], dict] = {}
        for r in self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall():
            out.setdefault((r["event_number"], r["sign"]),
                           {"svs": [], "pinnacle": []})["svs"].append(
                {"t": r["fetched_at"], "odds": r["odds"]})
        for r in self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall():
            out.setdefault((r["event_number"], r["sign"]),
                           {"svs": [], "pinnacle": []})["pinnacle"].append(
                {"t": r["fetched_at"], "odds": r["odds"]})
        return out

    # --- CLV-facit: flaggade värdetecken vs devigad stängningslinje ---
    def log_value_flag(self, r: dict, at: str) -> None:
        """first/best per selektion: insert vid ny flagga, uppdatera best om
        värde-kvoten är bättre än tidigare bästa."""
        cur = self.conn.execute(
            "SELECT best_ratio FROM value_log WHERE product=? AND draw_number=? "
            "AND event_number=? AND sign=?",
            (r["product"], r["draw_number"], r["event_number"], r["sign"])).fetchone()
        if cur is None:
            self.conn.execute(
                "INSERT INTO value_log(product, draw_number, event_number, sign, "
                "description, match_start, flag_type, first_at, first_odds, first_prob, "
                "prob_src, first_streck, first_ratio, best_ratio, best_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["product"], r["draw_number"], r["event_number"], r["sign"],
                 r.get("description"), r.get("match_start"), r.get("flag_type"),
                 at, r.get("odds"), r.get("prob"), r.get("prob_src"),
                 r.get("streck"), r.get("ratio"), r.get("ratio"), at))
        elif (r.get("ratio") or 0) > (cur["best_ratio"] or 0):
            self.conn.execute(
                "UPDATE value_log SET best_ratio=?, best_at=? WHERE product=? "
                "AND draw_number=? AND event_number=? AND sign=?",
                (r.get("ratio"), at, r["product"], r["draw_number"],
                 r["event_number"], r["sign"]))
        self._commit()

    def unresolved_closings(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM value_log WHERE closing_prob IS NULL AND closing_note IS NULL "
            "AND match_start IS NOT NULL").fetchall()
        return [dict(r) for r in rows]

    def set_closing(self, product: str, draw_number: int, event_number: int, sign: str,
                    prob: Optional[float] = None, odds: Optional[float] = None,
                    note: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE value_log SET closing_prob=?, closing_odds=?, closing_note=? "
            "WHERE product=? AND draw_number=? AND event_number=? AND sign=?",
            (prob, odds, note, product, draw_number, event_number, sign))
        self._commit()

    def draws_missing_outcome(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT DISTINCT product, draw_number FROM value_log WHERE outcome IS NULL").fetchall()
        return [(r["product"], r["draw_number"]) for r in rows]

    def set_outcomes(self, product: str, draw_number: int, facit: dict[int, str]) -> int:
        n = 0
        for r in self.conn.execute(
                "SELECT event_number, sign FROM value_log WHERE product=? AND draw_number=? "
                "AND outcome IS NULL", (product, draw_number)).fetchall():
            f = facit.get(r["event_number"])
            if f:
                self.conn.execute(
                    "UPDATE value_log SET outcome=? WHERE product=? AND draw_number=? "
                    "AND event_number=? AND sign=?",
                    (1 if r["sign"] == f else 0, product, draw_number,
                     r["event_number"], r["sign"]))
                n += 1
        self._commit()
        return n

    def clv_rows(self, product: Optional[str] = None, limit: int = 300) -> list[dict]:
        q, args = "SELECT * FROM value_log", []
        if product:
            q += " WHERE product=?"
            args.append(product)
        q += " ORDER BY first_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

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

    # ---------------- Oddset (enskilda matcher, app/oddset.py) ----------------

    ODDSET_SIGNS = {"1x2": ("1", "X", "2"), "ah": ("H", "A"), "ou": ("O", "U"),
                    "cor": ("O", "U")}

    def oddset_upsert_match(self, m: dict, prefer_names: bool = False) -> None:
        """Inkrementell upsert: None skriver aldrig över. prefer_names=True låter
        källans namn (Kambis svenska) ersätta befintliga visningsnamn."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.conn.execute(
            "INSERT INTO oddset_matches(id, league, home, away, start, pinnacle_id, "
            "kambi_id, status, updated_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            + ("home=excluded.home, away=excluded.away, "
               if prefer_names else
               "home=COALESCE(oddset_matches.home, excluded.home), "
               "away=COALESCE(oddset_matches.away, excluded.away), ")
            + "start=COALESCE(excluded.start, oddset_matches.start), "
              "pinnacle_id=COALESCE(excluded.pinnacle_id, oddset_matches.pinnacle_id), "
              "kambi_id=COALESCE(excluded.kambi_id, oddset_matches.kambi_id), "
              "status=COALESCE(excluded.status, oddset_matches.status), "
              "updated_at=excluded.updated_at",
            (m["id"], m["league"], m.get("home"), m.get("away"), m.get("start"),
             m.get("pinnacle_id"), m.get("kambi_id"), m.get("status"), now))
        self._commit()

    def oddset_matches(self, since: Optional[str] = None,
                       until: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_matches WHERE 1=1", []
        if since:
            q += " AND start >= ?"
            args.append(since)
        if until:
            q += " AND start <= ?"
            args.append(until)
        q += " ORDER BY start"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def _oddset_latest_values(self, match_id: str, source: str,
                              market: str) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT id, sign, odds, line, fetched_at, last_seen_at, available "
            "FROM oddset_odds s WHERE match_id=? AND source=? AND market=? "
            "AND id=(SELECT id FROM oddset_odds WHERE match_id=s.match_id "
            "AND source=s.source AND market=s.market AND sign=s.sign "
            "ORDER BY fetched_at DESC, id DESC LIMIT 1)",
            (match_id, source, market)).fetchall()
        return {r["sign"]: dict(r) for r in rows}

    def oddset_save_market(self, match_id: str, source: str, market: str,
                           rows: dict, fetched_at: str) -> int:
        """Registrera ett lyckat marknadssvar.

        rows = {sign: {'odds': float, 'line': float|None}}. Ett oförändrat pris
        flyttar last_seen_at utan ny historikpunkt. Saknade tecken markeras som
        unavailable; metoden ska därför bara anropas när källsvaret lyckades.
        """
        prev = self._oddset_latest_values(match_id, source, market)
        n = 0
        for sign in self.ODDSET_SIGNS.get(market, ()):
            val = rows.get(sign)
            if not val or val.get("odds") is None:
                if sign in prev:
                    self.conn.execute(
                        "UPDATE oddset_odds SET available=0 WHERE id=?",
                        (prev[sign]["id"],))
                continue
            cur = (val.get("odds"), val.get("line"))
            old = prev.get(sign)
            if old and (old["odds"], old["line"]) == cur:
                self.conn.execute(
                    "UPDATE oddset_odds SET last_seen_at=?, available=1 WHERE id=?",
                    (fetched_at, old["id"]))
                continue
            self.conn.execute(
                "INSERT INTO oddset_odds(match_id, source, market, sign, line, odds, "
                "fetched_at, last_seen_at, available) VALUES(?,?,?,?,?,?,?,?,1)",
                (match_id, source, market, sign, val.get("line"), val.get("odds"),
                 fetched_at, fetched_at))
            n += 1
        self._commit()
        return n

    def oddset_mark_market_unavailable(self, match_id: str, source: str,
                                       market: str) -> None:
        """Markera senaste raderna som plockade/suspenderade efter ett lyckat svar."""
        prev = self._oddset_latest_values(match_id, source, market)
        if prev:
            self.conn.executemany(
                "UPDATE oddset_odds SET available=0 WHERE id=?",
                [(r["id"],) for r in prev.values()])
            self._commit()

    def oddset_save_odds(self, match_id: str, source: str,
                         odds: dict, fetched_at: str) -> int:
        """Bekvämlighet för 1X2."""
        rows = {s: {"odds": odds.get(s), "line": None} for s in ("1", "X", "2")}
        return self.oddset_save_market(match_id, source, "1x2", rows, fetched_at)

    @staticmethod
    def _oddset_ids_clause(ids: list[str]) -> tuple[str, list]:
        if not ids:
            return "1=0", []
        return f"match_id IN ({','.join('?' * len(ids))})", list(ids)

    def oddset_latest(self, ids: list[str]) -> dict[str, dict]:
        """Senaste pris + observationsstatus per marknad.

        fetched_at är senaste prisförändringen, last_seen_at den äldsta senaste
        bekräftelsen bland marknadens obligatoriska tecken. derived viks in
        under Pinnacle men vinner bara när den direkta 1X2-marknaden inte är
        tillgänglig.
        """
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT id, match_id, source, market, sign, odds, line, fetched_at, "
            f"last_seen_at, available FROM oddset_odds s WHERE {where} AND id=("
            f"SELECT id FROM oddset_odds WHERE match_id=s.match_id "
            f"AND source=s.source AND market=s.market AND sign=s.sign "
            f"ORDER BY fetched_at DESC, id DESC LIMIT 1)", args).fetchall()
        raw: dict[str, dict] = {}
        for r in rows:
            m = raw.setdefault(r["match_id"], {}).setdefault(r["source"], {}) \
                   .setdefault(r["market"], {"_selections": {}})
            m[r["sign"]] = r["odds"]
            if r["line"] is not None:
                m["line"] = r["line"]
            m["_selections"][r["sign"]] = {
                "available": bool(r["available"]),
                "last_seen_at": r["last_seen_at"],
                "fetched_at": r["fetched_at"],
                "line": r["line"],
            }

        def finalize(market: str, m: dict) -> dict:
            signs = self.ODDSET_SIGNS.get(market, ())
            states = m.pop("_selections", {})
            complete = all(s in states for s in signs)
            lines = {states[s]["line"] for s in signs if s in states}
            line_ok = market == "1x2" or (complete and len(lines) == 1 and None not in lines)
            m["available"] = bool(
                complete and line_ok and all(states[s]["available"] for s in signs))
            seen = [states[s]["last_seen_at"] for s in signs
                    if s in states and states[s]["last_seen_at"]]
            changed = [states[s]["fetched_at"] for s in signs
                       if s in states and states[s]["fetched_at"]]
            m["last_seen_at"] = min(seen) if seen else None
            m["fetched_at"] = max(changed) if changed else None
            m["selections"] = states
            return m

        for sources in raw.values():
            for markets in sources.values():
                for market, m in list(markets.items()):
                    markets[market] = finalize(market, m)

        out: dict[str, dict] = {}
        for mid, sources in raw.items():
            target = out.setdefault(mid, {})
            for source, markets in sources.items():
                if source == "derived":
                    continue
                target[source] = markets
            derived = sources.get("derived", {}).get("1x2")
            if derived:
                direct = target.setdefault("pinnacle", {}).get("1x2")
                if direct is None or (not direct.get("available") and derived.get("available")):
                    target["pinnacle"]["1x2"] = {**derived, "derived": True}
        return out

    def oddset_record_source_health(self, source: str, league: str, scope: str,
                                    checked_at: str, ok: bool, event_count: int = 0,
                                    error: Optional[str] = None) -> None:
        self.conn.execute(
            "INSERT INTO oddset_source_health(source, league, scope, checked_at, ok, "
            "event_count, error) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,league,scope) "
            "DO UPDATE SET checked_at=excluded.checked_at, ok=excluded.ok, "
            "event_count=excluded.event_count, error=excluded.error",
            (source, league, scope, checked_at, int(ok), event_count,
             (error or "")[:240] or None))
        self._commit()

    def oddset_source_health(self) -> list[dict]:
        return [dict(r) | {"ok": bool(r["ok"])} for r in self.conn.execute(
            "SELECT source, league, scope, checked_at, ok, event_count, error "
            "FROM oddset_source_health ORDER BY source, league, scope").fetchall()]

    def oddset_movement(self, ids: list[str]) -> dict[str, dict]:
        """Rörelse (first/last/min/max/n + punktserie) för alla givna matcher i en
        fråga. -> {match_id: {source: {market: {sign: agg}}}}. 'derived' → 'pinnacle'.
        Punkterna bär linjen (AH/ÖU/hörnor) — first_l/last_l visar linjeflytt."""
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT match_id, source, market, sign, odds, line, fetched_at "
            f"FROM oddset_odds "
            f"WHERE {where} AND odds IS NOT NULL ORDER BY fetched_at", args).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            src = "pinnacle" if r["source"] == "derived" else r["source"]
            agg = out.setdefault(r["match_id"], {}).setdefault(src, {}) \
                     .setdefault(r["market"], {})
            a = agg.get(r["sign"])
            o, t, ln = r["odds"], r["fetched_at"], r["line"]
            if a is None:
                agg[r["sign"]] = {"first": o, "last": o, "min": o, "max": o, "n": 1,
                                  "first_t": t, "last_t": t, "first_l": ln, "last_l": ln,
                                  "pts": [{"t": t, "o": o, "l": ln}]}
            else:
                a["last"], a["last_t"], a["n"] = o, t, a["n"] + 1
                a["last_l"] = ln
                a["min"], a["max"] = min(a["min"], o), max(a["max"], o)
                a["pts"].append({"t": t, "o": o, "l": ln})
        return out

    def oddset_save_result(self, r: dict) -> None:
        """COALESCE-upsert: xG från Sofascore fyller på football-data-rader
        (samma PK tack vare normaliserade namn) utan att skriva över mål."""
        self.conn.execute(
            "INSERT INTO oddset_results(league, date, home, away, home_raw, away_raw, "
            "hg, ag, xg_h, xg_a, cor_h, cor_a, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(league, date, home, away) DO UPDATE SET "
            "hg=COALESCE(oddset_results.hg, excluded.hg), "
            "ag=COALESCE(oddset_results.ag, excluded.ag), "
            "xg_h=COALESCE(excluded.xg_h, oddset_results.xg_h), "
            "xg_a=COALESCE(excluded.xg_a, oddset_results.xg_a), "
            "cor_h=COALESCE(excluded.cor_h, oddset_results.cor_h), "
            "cor_a=COALESCE(excluded.cor_a, oddset_results.cor_a)",
            (r["league"], r["date"], r["home"], r["away"], r.get("home_raw"),
             r.get("away_raw"), r.get("hg"), r.get("ag"), r.get("xg_h"),
             r.get("xg_a"), r.get("cor_h"), r.get("cor_a"), r.get("source")))
        self._commit()

    def oddset_results(self, league: str, since: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_results WHERE league=? AND hg IS NOT NULL", [league]
        if since:
            q += " AND date >= ?"
            args.append(since)
        q += " ORDER BY date"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def meta_like(self, prefix: str) -> list[tuple[str, str]]:
        return [(r["key"], r["value"]) for r in self.conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE ?", (prefix + "%",)).fetchall()]

    def oddset_log_flag(self, r: dict) -> None:
        """First/best per (match, marknad, tecken, lina, signalversion).

        First skrivs aldrig över. Lina och version ingår i identiteten så en
        edge på ny lina eller under ny algoritmregim inte blandas med den gamla.
        model_version = semantiskt signal-fingeravtryck (facitet delas på den);
        git_hash = exakt kodversion vid first (reproducerbarhet). Granskningen
        punkt 5: docs-commits får inte fragmentera facitet."""
        line = r.get("line")
        line_key = (self.ODDSET_NO_LINE_KEY if line is None
                    else int(round(float(line) * 1000)))
        version = r.get("model_version") or "legacy"
        self.conn.execute(
            "INSERT INTO oddset_value_log(match_id, market, sign, line, line_key, league, "
            "description, match_start, first_at, first_odds, first_fair, first_edge, "
            "best_edge, best_at, book, tier, model_version, git_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(match_id, market, sign, line_key, model_version) DO UPDATE SET "
            "best_edge=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_edge ELSE oddset_value_log.best_edge END, "
            "best_at=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_at ELSE oddset_value_log.best_at END",
            (r["match_id"], r["market"], r["sign"], line, line_key, r.get("league"),
             r.get("description"), r.get("match_start"), r["at"], r["odds"],
             r["fair"], r["edge"], r["edge"], r["at"], r.get("book"),
             r.get("tier", "sharp"), version, r.get("git_hash")))
        self._commit()

    def oddset_unresolved_closings(self, now_iso: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log WHERE closing_fair IS NULL "
            "AND closing_note IS NULL AND match_start IS NOT NULL AND match_start < ?",
            (now_iso,)).fetchall()]

    def oddset_history_before(self, match_id: str, market: str,
                              before_iso: str) -> list[dict]:
        """Pinnacle-serien (inkl. derived) före en tidpunkt, i tidsordning."""
        return [dict(r) for r in self.conn.execute(
            "SELECT sign, odds, line, fetched_at, last_seen_at, available "
            "FROM oddset_odds WHERE match_id=? "
            "AND market=? AND source IN ('pinnacle','derived') AND fetched_at < ? "
            "AND odds IS NOT NULL ORDER BY fetched_at, id",
            (match_id, market, before_iso)).fetchall()]

    def oddset_set_closing(self, flag: dict, fair: Optional[float],
                           odds: Optional[float], note: Optional[str],
                           closing_line: Optional[float] = None,
                           line_delta: Optional[float] = None,
                           line_move_score: Optional[float] = None) -> None:
        self.conn.execute(
            "UPDATE oddset_value_log SET closing_fair=?, closing_odds=?, closing_note=?, "
            "closing_line=?, line_delta=?, line_move_score=? WHERE match_id=? "
            "AND market=? AND sign=? AND line_key=? AND model_version=?",
            (fair, odds, note, closing_line, line_delta, line_move_score,
             flag["match_id"], flag["market"], flag["sign"], flag["line_key"],
             flag.get("model_version") or "legacy"))
        self._commit()

    def oddset_clv_rows(self, limit: int = 300) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log ORDER BY first_at DESC LIMIT ?",
            (limit,)).fetchall()]

    # --- WP5 prediction ledger -------------------------------------------------

    def oddset_prediction_captured(self, match_id: str, horizon: str, tier: str,
                                   signal_version: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM oddset_prediction_capture WHERE match_id=? AND horizon=? "
            "AND tier=? AND signal_version=?",
            (match_id, horizon, tier, signal_version)).fetchone() is not None

    def oddset_capture_predictions(self, capture: dict, rows: list[dict]) -> int:
        """Spara en horisont atomärt och exakt en gång.

        Capture-raden skrivs även när rows är tom: källfrånvaro får inte
        senare maskeras som en skenbart exakt horisont. Returnerar antal nya
        prediktionsrader; 0 om horisonten redan var fångad.
        """
        with self.bulk():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO oddset_prediction_capture(match_id, horizon, "
                "tier, signal_version, base_version, match_start, target_at, "
                "captured_at, offset_minutes, delay_minutes, row_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (capture["match_id"], capture["horizon"], capture["tier"],
                 capture["signal_version"], capture["base_version"],
                 capture["match_start"], capture["target_at"],
                 capture["captured_at"], capture["offset_minutes"],
                 capture["delay_minutes"], len(rows)))
            if cur.rowcount == 0:
                return 0
            for r in rows:
                self.conn.execute(
                    "INSERT INTO oddset_prediction_log(match_id, horizon, tier, market, "
                    "sign, line, line_key, league, description, match_start, target_at, "
                    "captured_at, offset_minutes, fair_prob, fair_source, fair_available, "
                    "fair_fresh, model_anchored, book, book_odds, book_available, "
                    "book_fresh, edge, eligible, is_flag, signal_version, base_version, "
                    "git_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (capture["match_id"], capture["horizon"], capture["tier"],
                     r["market"], r["sign"], r.get("line"), r["line_key"],
                     capture.get("league"), capture.get("description"),
                     capture["match_start"], capture["target_at"],
                     capture["captured_at"], capture["offset_minutes"],
                     r["fair_prob"], r["fair_source"], int(r["fair_available"]),
                     int(r["fair_fresh"]), r.get("model_anchored"), r.get("book"),
                     r.get("book_odds"), int(r["book_available"]),
                     int(r["book_fresh"]), r.get("edge"), int(r["eligible"]),
                     int(r["is_flag"]), capture["signal_version"],
                     capture["base_version"], capture.get("git_hash")))
        return len(rows)

    def oddset_unresolved_predictions(self, now_iso: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_prediction_log WHERE closing_fair IS NULL "
            "AND closing_note IS NULL AND match_start < ?",
            (now_iso,)).fetchall()]

    def oddset_set_prediction_closing(
            self, row: dict, fair: Optional[float], odds: Optional[float],
            note: Optional[str], closing_line: Optional[float] = None,
            line_delta: Optional[float] = None,
            line_move_score: Optional[float] = None) -> None:
        self.conn.execute(
            "UPDATE oddset_prediction_log SET closing_fair=?, closing_odds=?, "
            "closing_note=?, closing_line=?, line_delta=?, line_move_score=? "
            "WHERE match_id=? AND horizon=? AND tier=? AND market=? AND sign=? "
            "AND signal_version=?",
            (fair, odds, note, closing_line, line_delta, line_move_score,
             row["match_id"], row["horizon"], row["tier"], row["market"],
             row["sign"], row["signal_version"]))
        self._commit()

    def oddset_prediction_rows(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, c.delay_minutes FROM oddset_prediction_log p "
            "JOIN oddset_prediction_capture c ON c.match_id=p.match_id "
            "AND c.horizon=p.horizon AND c.tier=p.tier "
            "AND c.signal_version=p.signal_version "
            "ORDER BY p.captured_at, p.match_id, p.tier, p.market, p.sign").fetchall()]

    def oddset_prediction_captures(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_prediction_capture ORDER BY captured_at, match_id, tier"
        ).fetchall()]

    def oddset_prediction_states(self) -> dict[tuple, dict]:
        rows = self.conn.execute("SELECT * FROM oddset_prediction_group_state").fetchall()
        return {(r["tier"], r["league"], r["market"], r["signal_version"]): dict(r)
                for r in rows}

    def oddset_set_prediction_state(self, key: tuple, status: str, at: str) -> None:
        tier, league, market, version = key
        candidate = at if status == "candidate" else None
        green = at if status == "green" else None
        self.conn.execute(
            "INSERT INTO oddset_prediction_group_state(tier, league, market, "
            "signal_version, status, candidate_at, green_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(tier,league,market,signal_version) DO UPDATE SET "
            "status=excluded.status, "
            "candidate_at=COALESCE(oddset_prediction_group_state.candidate_at, "
            "excluded.candidate_at), green_at=COALESCE(oddset_prediction_group_state.green_at, "
            "excluded.green_at)",
            (tier, league, market, version, status, candidate, green))
        self._commit()
