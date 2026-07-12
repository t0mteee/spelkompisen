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

import datetime as dt
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
    fetched_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oddset_odds
    ON oddset_odds (match_id, source, market, sign, fetched_at);

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
    closing_note TEXT,
    PRIMARY KEY (match_id, market, sign)
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
        self.conn.commit()

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
        self.conn.commit()

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
        self.conn.commit()
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

    ODDSET_SIGNS = {"1x2": ("1", "X", "2"), "ah": ("H", "A"), "ou": ("O", "U")}

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
        self.conn.commit()

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
                              market: str) -> dict[str, tuple]:
        rows = self.conn.execute(
            "SELECT sign, odds, line FROM oddset_odds s WHERE match_id=? AND source=? "
            "AND market=? AND fetched_at=(SELECT MAX(fetched_at) FROM oddset_odds WHERE "
            "match_id=s.match_id AND source=s.source AND market=s.market AND sign=s.sign)",
            (match_id, source, market)).fetchall()
        return {r["sign"]: (r["odds"], r["line"]) for r in rows}

    def oddset_save_market(self, match_id: str, source: str, market: str,
                           rows: dict, fetched_at: str) -> int:
        """rows: {sign: {'odds': float, 'line': float|None}}. Sparar bara förändring."""
        prev = self._oddset_latest_values(match_id, source, market)
        n = 0
        for sign in self.ODDSET_SIGNS.get(market, ()):
            val = rows.get(sign)
            if not val or val.get("odds") is None:
                continue
            cur = (val.get("odds"), val.get("line"))
            if prev.get(sign) == cur:
                continue
            self.conn.execute(
                "INSERT INTO oddset_odds(match_id, source, market, sign, line, odds, "
                "fetched_at) VALUES(?,?,?,?,?,?,?)",
                (match_id, source, market, sign, val.get("line"), val.get("odds"),
                 fetched_at))
            n += 1
        self.conn.commit()
        return n

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
        """{match_id: {source: {market: {sign: odds, 'line': line, 'fetched_at': ts}}}}
        — 'derived' viks in under 'pinnacle' (samma boks härledda 1X2)."""
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT match_id, source, market, sign, odds, line, fetched_at "
            f"FROM oddset_odds s WHERE {where} AND fetched_at=("
            f"SELECT MAX(fetched_at) FROM oddset_odds WHERE match_id=s.match_id "
            f"AND source=s.source AND market=s.market AND sign=s.sign)", args).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            src = "pinnacle" if r["source"] == "derived" else r["source"]
            m = out.setdefault(r["match_id"], {}).setdefault(src, {}).setdefault(r["market"], {})
            m[r["sign"]] = r["odds"]
            if r["line"] is not None:
                m["line"] = r["line"]
            m["fetched_at"] = r["fetched_at"]
            if r["source"] == "derived":
                m["derived"] = True
        return out

    def oddset_movement(self, ids: list[str]) -> dict[str, dict]:
        """Rörelse (first/last/min/max/n + punktserie) för alla givna matcher i en
        fråga. -> {match_id: {source: {market: {sign: agg}}}}. 'derived' → 'pinnacle'."""
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT match_id, source, market, sign, odds, fetched_at FROM oddset_odds "
            f"WHERE {where} AND odds IS NOT NULL ORDER BY fetched_at", args).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            src = "pinnacle" if r["source"] == "derived" else r["source"]
            agg = out.setdefault(r["match_id"], {}).setdefault(src, {}) \
                     .setdefault(r["market"], {})
            a = agg.get(r["sign"])
            o, t = r["odds"], r["fetched_at"]
            if a is None:
                agg[r["sign"]] = {"first": o, "last": o, "min": o, "max": o, "n": 1,
                                  "first_t": t, "last_t": t, "pts": [{"t": t, "o": o}]}
            else:
                a["last"], a["last_t"], a["n"] = o, t, a["n"] + 1
                a["min"], a["max"] = min(a["min"], o), max(a["max"], o)
                a["pts"].append({"t": t, "o": o})
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
        self.conn.commit()

    def oddset_results(self, league: str, since: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_results WHERE league=? AND hg IS NOT NULL", [league]
        if since:
            q += " AND date >= ?"
            args.append(since)
        q += " ORDER BY date"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def oddset_log_flag(self, r: dict) -> None:
        """First/best per (match, marknad, tecken) — first skrivs aldrig över."""
        self.conn.execute(
            "INSERT INTO oddset_value_log(match_id, market, sign, line, league, "
            "description, match_start, first_at, first_odds, first_fair, first_edge, "
            "best_edge, best_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(match_id, market, sign) DO UPDATE SET "
            "best_edge=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_edge ELSE oddset_value_log.best_edge END, "
            "best_at=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_at ELSE oddset_value_log.best_at END",
            (r["match_id"], r["market"], r["sign"], r.get("line"), r.get("league"),
             r.get("description"), r.get("match_start"), r["at"], r["odds"],
             r["fair"], r["edge"], r["edge"], r["at"]))
        self.conn.commit()

    def oddset_unresolved_closings(self, now_iso: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log WHERE closing_fair IS NULL "
            "AND closing_note IS NULL AND match_start IS NOT NULL AND match_start < ?",
            (now_iso,)).fetchall()]

    def oddset_history_before(self, match_id: str, market: str,
                              before_iso: str) -> list[dict]:
        """Pinnacle-serien (inkl. derived) före en tidpunkt, i tidsordning."""
        return [dict(r) for r in self.conn.execute(
            "SELECT sign, odds, line, fetched_at FROM oddset_odds WHERE match_id=? "
            "AND market=? AND source IN ('pinnacle','derived') AND fetched_at < ? "
            "AND odds IS NOT NULL ORDER BY fetched_at",
            (match_id, market, before_iso)).fetchall()]

    def oddset_set_closing(self, match_id: str, market: str, sign: str,
                           fair: Optional[float], odds: Optional[float],
                           note: Optional[str]) -> None:
        self.conn.execute(
            "UPDATE oddset_value_log SET closing_fair=?, closing_odds=?, closing_note=? "
            "WHERE match_id=? AND market=? AND sign=?",
            (fair, odds, note, match_id, market, sign))
        self.conn.commit()

    def oddset_clv_rows(self, limit: int = 300) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log ORDER BY first_at DESC LIMIT ?",
            (limit,)).fetchall()]
