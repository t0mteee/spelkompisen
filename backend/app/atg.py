"""ATG:s sportpoolspel: Big 9 (BIG9) och Nya Big 9 (SP96), insamling.

Beslut driften-2026-10-24-big9-atg (val 0): samla in Big 9 från ATG och lägg
Big 9 som produkt på facitsidan. Beslut 2026-10-24-sp96-ar-big9 (val 0): SP96
("Premiär!" 2026-10-24) ÄR nya Big 9 och är den som mäts (`MEASURED`); gamla
BIG9 samlas in om den dyker upp igen men mäts inte.

Källan (källgränsen: publikt JSON-API utan inloggning, cookies eller utmaning):
`GET https://www.atg.se/services/sports-info-offering/api/v1/offering` — EN
lista med alla ATG:s sportspel (≈ 6 MB okomprimerat, `no-store`). Poster med
`gameType` BIG9/SP96 sparas; övriga (SP5) ignoreras. Ingen inloggad väg rörs.

Listan visar bara SENASTE läget. Odds och streck vid T−6 h och T−30 min finns
därför bara om vi läser medan omgången är `SELL_OPEN` — inget bakfylls.

Tabellerna (append-only via triggrar, skapas BARA av scripts/migrera_atg.py):
* `atg_offering_capture` — EN rad per hämtning, även misslyckad
  (observationstidsregeln 7: bara en append-only-logg bevisar att vi frågade).
* `atg_round_observation` — rå omgångspost per observation. `SELL_OPEN` skrivs
  vid VARJE lyckad hämtning (presence); andra lägen bara när (omgång, läge,
  innehåll) är nytt. `observed_at` = tiden EFTER anropet minus HTTP `Age`.

Kadens (`fetch_due`): basvarv var 6:e timme; från T−7 h före spelstopp var
30:e minut och varje pool-tick (5 min) inne i facitsidans horisontfönster;
efter spelstopp var 30:e minut tills omgången är FINALIZED/CANCELED (högst
48 h). Ett anrop ger alla omgångar.

Regler ur ATG:s publika regler och svaret (ommätt mot 101 avgjorda BIG9-omgångar
2025-02-01–2026-10-17, noll avvikelser):
* BIG9: 9 matcher, en rad = 1X2 + Över/Under 2,5 per match och ett Wild Card
  (matchen räknas som rätt). Vinstgrupper 7/8/9 rätt = 40/20/40 % av 65 %
  (uttag 35 %). Radpris 0,50 kr = `unitStake` 50 öre = 1 enhet.
* Utdelning per enhet = potten / vinnande enheter, avrundat NEDÅT till hela
  kronor; under `minUnitDividend` (15 kr) betalas 0 och potten rullar.
* SP96 = "Nya Big 9" (ATG:s nyhet 2026-10-24): Wild Card borttaget, 6–9 rätt
  35/15/15/35 %, `takeoutPercentage` 25, radpris 0,50 kr (`unitStake` 50),
  minsta utdelning 10 kr (`minUnitDividend` 1000). Första observationen (omgång
  517) hade potterna för 6–8 rätt = 72,75 % (75 % × 0,97) av omsättningen ×
  andelen, så byggaren läser återbetalningsandelen ur potterna
  (`spelai.big9.payout_ratio`), inte ur uttaget. Struken/uppskjuten match
  rättas som rätt för alla.
* `result`/`score` finns även på ospelade matcher (platshållare 0–0 "tie/
  under"): bara `status == DECIDED` är ett resultat.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from typing import Callable, Optional

import httpx

OFFERING_URL = "https://www.atg.se/services/sports-info-offering/api/v1/offering"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
           "Accept-Encoding": "gzip"}
TIMEOUT_S = 30.0

# Produkt (Spelkompisens slug) → ATG:s spelform. `wildcard` = en rad bär ett
# Wild Card; `splits` = vinstgrupp → andel av återbetalningen (1 − uttag).
PRODUCTS = {
    "big9": {"game_type": "BIG9", "name": "Gamla Big 9 (BIG9)", "matches": 9,
             "row_price": 0.5, "wildcard": True,
             "splits": {7: 0.40, 8: 0.20, 9: 0.40}},
    "sp96": {"game_type": "SP96", "name": "Big 9", "matches": 9,
             "row_price": 0.5, "wildcard": False,
             "splits": {6: 0.35, 7: 0.15, 8: 0.15, 9: 0.35}},
}
GAME_TYPES = {cfg["game_type"]: slug for slug, cfg in PRODUCTS.items()}
# Mäts på facitsidan. SP96 är Big 9 sedan 2026-10-24 (beslut
# 2026-10-24-sp96-ar-big9, val 0); gamla BIG9 samlas bara in.
MEASURED = ("sp96",)

OPEN = "SELL_OPEN"
DONE_STATES = ("FINALIZED", "CANCELED")

BASE_INTERVAL = dt.timedelta(hours=6)
DENSE_BEFORE = dt.timedelta(hours=7)
DENSE_INTERVAL = dt.timedelta(minutes=30)
WINDOW_MIN_GAP = dt.timedelta(minutes=4)
AFTER_CLOSE_MAX = dt.timedelta(hours=48)

TABLES = ("atg_offering_capture", "atg_round_observation")

ATG_SCHEMA = """
CREATE TABLE IF NOT EXISTS atg_offering_capture (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at   TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    http_status  INTEGER,
    age_s        REAL,
    encoding     TEXT,
    n_records    INTEGER,
    n_rounds     INTEGER,
    n_open       INTEGER,
    n_written    INTEGER,
    reason       TEXT,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_atg_capture_at ON atg_offering_capture (fetched_at);

CREATE TABLE IF NOT EXISTS atg_round_observation (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id    INTEGER NOT NULL REFERENCES atg_offering_capture(id),
    product       TEXT NOT NULL,
    game_type     TEXT NOT NULL,
    round_id      TEXT NOT NULL,
    serial_number INTEGER NOT NULL,
    status        TEXT NOT NULL,
    start_time    TEXT NOT NULL,
    observed_at   TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    payload_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atg_obs_round
    ON atg_round_observation (product, serial_number, id);
CREATE INDEX IF NOT EXISTS idx_atg_obs_status
    ON atg_round_observation (round_id, status, payload_hash);
"""


def _triggers() -> str:
    return "\n".join(
        f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{op.lower()} BEFORE {op} "
        f"ON {table} BEGIN SELECT RAISE(ABORT, 'atg: {table} är append-only'); END;"
        for table in TABLES for op in ("UPDATE", "DELETE"))


FULL_SCHEMA = ATG_SCHEMA + "\n" + _triggers()


def tables_exist(conn: sqlite3.Connection) -> bool:
    names = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'atg_%'")}
    return all(table in names for table in TABLES)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Skapa tabellerna. ENBART för migreringsskriptet och testerna."""
    conn.executescript("BEGIN IMMEDIATE;\n" + FULL_SCHEMA + "\nCOMMIT;")


def namn(product: str) -> Optional[str]:
    cfg = PRODUCTS.get(product)
    return cfg["name"] if cfg else None


def utc(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── hämtning ─────────────────────────────────────────────────────────────

class FetchError(RuntimeError):
    def __init__(self, message: str, http_status: Optional[int] = None,
                 encoding: Optional[str] = None):
        super().__init__(message)
        self.http_status = http_status
        self.encoding = encoding


def fetch_offering(client: Optional[httpx.Client] = None) -> tuple[list, dict]:
    """Hämta listan. Returnerar (poster, meta{http_status, age_s, encoding}).

    En parse som misslyckas på 200 är ett transportfel (transportregeln):
    `content-encoding` följer med i felet."""
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT_S, headers=HEADERS)
    try:
        resp = client.get(OFFERING_URL)
    except httpx.HTTPError as exc:
        raise FetchError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        if own:
            client.close()
    encoding = resp.headers.get("content-encoding")
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}", resp.status_code, encoding)
    try:
        data = resp.json()
    except ValueError as exc:
        raise FetchError(f"kroppen gick inte att läsa som JSON "
                         f"(content-encoding={encoding!r})", 200, encoding) from exc
    if not isinstance(data, list):
        raise FetchError(f"oväntad form: {type(data).__name__}, inte en lista",
                         200, encoding)
    try:
        age = float(resp.headers.get("age")) if resp.headers.get("age") else None
    except ValueError:
        age = None
    return data, {"http_status": resp.status_code, "age_s": age, "encoding": encoding}


# ── lagring ──────────────────────────────────────────────────────────────

def _round_ok(record) -> bool:
    return (isinstance(record, dict) and record.get("gameType") in GAME_TYPES
            and isinstance(record.get("id"), str)
            and isinstance(record.get("serialNumber"), int)
            and utc(record.get("startTime")) is not None
            and isinstance(record.get("matches"), list))


def store_offering(conn, records: list, meta: dict, *, fetched_at: dt.datetime,
                   reason: str) -> dict:
    """Skriv hämtningens loggrad och omgångsobservationerna (en transaktion)."""
    observed = fetched_at - dt.timedelta(seconds=float(meta.get("age_s") or 0.0))
    rounds = [r for r in records if _round_ok(r)]
    n_open = sum(1 for r in rounds if r.get("status") == OPEN)
    todo = []
    for record in rounds:
        text = json.dumps(record, ensure_ascii=False, sort_keys=True)
        digest = payload_hash(text)
        status = str(record.get("status") or "")
        if status != OPEN and conn.execute(
                "SELECT 1 FROM atg_round_observation WHERE round_id=? AND status=? "
                "AND payload_hash=? LIMIT 1",
                (record["id"], status, digest)).fetchone():
            continue
        todo.append((record, status, text, digest))
    cur = conn.execute(
        "INSERT INTO atg_offering_capture (fetched_at, ok, http_status, age_s, "
        "encoding, n_records, n_rounds, n_open, n_written, reason) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (iso(fetched_at), 1, meta.get("http_status"), meta.get("age_s"),
         meta.get("encoding"), len(records), len(rounds), n_open, len(todo), reason))
    capture_id = cur.lastrowid
    written = []
    for record, status, text, digest in todo:
        product = GAME_TYPES[record["gameType"]]
        conn.execute(
            "INSERT INTO atg_round_observation (capture_id, product, game_type, "
            "round_id, serial_number, status, start_time, observed_at, "
            "payload_hash, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (capture_id, product, record["gameType"], record["id"],
             record["serialNumber"], status, iso(utc(record["startTime"])),
             iso(observed), digest, text))
        written.append({"product": product, "serial": record["serialNumber"],
                        "status": status})
    conn.commit()
    return {"capture_id": capture_id, "observed_at": iso(observed),
            "rounds": len(rounds), "open": n_open, "written": written}


def store_failure(conn, error: FetchError | Exception, *, fetched_at: dt.datetime,
                  reason: str) -> None:
    conn.execute(
        "INSERT INTO atg_offering_capture (fetched_at, ok, http_status, encoding, "
        "reason, error) VALUES (?,?,?,?,?,?)",
        (iso(fetched_at), 0, getattr(error, "http_status", None),
         getattr(error, "encoding", None), reason,
         f"{type(error).__name__}: {error}"[:500]))
    conn.commit()


def latest_rounds(conn, products=None) -> list[dict]:
    """Senaste observationen per (produkt, omgång), med rå post."""
    sql = ("SELECT o.product, o.serial_number, o.round_id, o.status, o.start_time, "
           "o.observed_at, o.payload_json FROM atg_round_observation o JOIN ("
           "SELECT MAX(id) AS id FROM atg_round_observation GROUP BY product, "
           "serial_number) last ON last.id = o.id")
    out = []
    for product, serial, round_id, status, start, observed, text in conn.execute(sql):
        if products is not None and product not in products:
            continue
        out.append({"product": product, "serial": int(serial), "round_id": round_id,
                    "status": status, "start": utc(start), "observed_at": utc(observed),
                    "record": json.loads(text)})
    return out


def latest_observation(conn, product: str, serial: int,
                       status: Optional[str] = None) -> Optional[dict]:
    sql = ("SELECT status, start_time, observed_at, payload_json FROM "
           "atg_round_observation WHERE product=? AND serial_number=?")
    params: list = [product, int(serial)]
    if status:
        sql += " AND status=?"
        params.append(status)
    row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()
    if row is None:
        return None
    return {"status": row[0], "start": utc(row[1]), "observed_at": utc(row[2]),
            "record": json.loads(row[3])}


def final_turnovers(conn, product: str, before: dt.datetime, n: int = 8) -> list[float]:
    """Slutomsättning (kr) för de senaste n FINALIZED omgångarna före `before`."""
    rows = [r for r in latest_rounds(conn, (product,))
            if r["status"] == "FINALIZED" and r["start"] and r["start"] < before]
    rows.sort(key=lambda r: r["start"], reverse=True)
    out = []
    for r in rows[:n]:
        turnover = ((r["record"].get("pool") or {}).get("turnover"))
        if isinstance(turnover, (int, float)) and turnover > 0:
            out.append(turnover / 100.0)
    return out


# ── kadens ───────────────────────────────────────────────────────────────

def _in_horizon_window(close: dt.datetime, now: dt.datetime) -> bool:
    from .spelai import indata
    return any(start <= now <= end for start, end in
               (indata.window(close, h) for h in indata.HORIZONS))


def fetch_due(conn, now: dt.datetime) -> tuple[bool, str]:
    rows = conn.execute(
        "SELECT fetched_at, ok FROM atg_offering_capture ORDER BY id DESC LIMIT 50"
    ).fetchall()
    if not rows:
        return True, "första hämtningen"
    last_attempt = utc(rows[0][0])
    last_ok = next((utc(t) for t, ok in rows if ok), None)
    since_attempt = now - last_attempt
    for r in latest_rounds(conn):
        close = r["start"]
        if close is None:
            continue
        if r["status"] == OPEN and now < close <= now + DENSE_BEFORE:
            if _in_horizon_window(close, now) and since_attempt >= WINDOW_MIN_GAP:
                return True, f"{r['product']} {r['serial']}: horisontfönster öppet"
            if since_attempt >= DENSE_INTERVAL:
                return True, f"{r['product']} {r['serial']}: inom 7 h före spelstopp"
        if (r["status"] not in DONE_STATES and close <= now
                and now - close <= AFTER_CLOSE_MAX and since_attempt >= DENSE_INTERVAL):
            return True, f"{r['product']} {r['serial']}: väntar på facit"
    if last_ok is None or now - last_ok >= BASE_INTERVAL:
        if since_attempt >= DENSE_INTERVAL:
            return True, "basvarv"
    return False, "inget att hämta"


Clock = Callable[[], dt.datetime]


def run_pass(conn, *, clock: Clock, fetch=fetch_offering, force: bool = False,
             on_round=None) -> dict:
    """Ett insamlingsvarv: avgör om en hämtning behövs, hämta, spara och lämna
    varje observerad omgång till `on_round(conn, obs)` (facitsidans paket)."""
    if not tables_exist(conn):
        return {"skipped": "atg-tabellerna saknas — kör scripts/migrera_atg.py"}
    due, reason = fetch_due(conn, clock())
    if not (due or force):
        return {"skipped": reason}
    reason = reason if due else "manuell"
    try:
        records, meta = fetch()
    except Exception as exc:  # noqa: BLE001 — en källa får inte fälla poolvarvet
        store_failure(conn, exc, fetched_at=clock(), reason=reason)
        return {"fel": f"{type(exc).__name__}: {exc}", "reason": reason}
    fetched_at = clock()     # EFTER anropet (observationstidsregeln 3)
    report = store_offering(conn, records, meta, fetched_at=fetched_at, reason=reason)
    report["reason"] = reason
    if on_round is not None:
        captured = []
        for item in report["written"]:
            if item["status"] != OPEN:
                continue
            obs = latest_observation(conn, item["product"], item["serial"], OPEN)
            if obs is None:
                continue
            try:
                got = on_round(conn, item["product"], obs, now=clock())
            except Exception as exc:  # noqa: BLE001
                got = {"fel": f"{type(exc).__name__}: {exc}"}
            captured.append({**item, "facit": got})
        report["facit"] = captured
    return report
