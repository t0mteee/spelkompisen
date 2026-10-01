"""Facitsidans tillstånd: paus, startpunkt, kvot och händelsejournal.

Tillståndet är append-only: `spelai_state` får en NY rad per ändring och den
senaste raden per nyckel gäller. Journalen `spelai_event` bär en valfri
`dedup_key` som gör en händelse (t.ex. en skickad notis) idempotent.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Optional
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Stockholm")

# Det ABSOLUTA taket för AI-körningar per dygn. Står i facitsidans kod och
# ändras bara av Claude eller Codex — agenten kan aldrig höja sitt eget tak
# (designens 5.5). Ett besvarat beslut kan bara sänka eller höja inom taket.
MAX_KORNINGAR_ABS = 12
STANDARD_KVOT = 8

PAUS_KEY = "paus"
FACIT_START_KEY = "facit_start"


def utc(value) -> Optional[dt.datetime]:
    """ISO-tid som UTC-datetime. Tider jämförs som tider, aldrig som text."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        try:
            parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    """UTC med `Z` — konverterar först (CLAUDE.md: `Z` betyder UTC)."""
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── händelser ────────────────────────────────────────────────────────────

def logga(conn: sqlite3.Connection, kind: str, ref: Optional[str] = None,
          detail: Optional[dict] = None, *, now: dt.datetime,
          dedup_key: Optional[str] = None) -> bool:
    """Skriv en händelse. Med dedup_key: bara första gången (True = ny)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO spelai_event (at, kind, ref, detail_json, dedup_key) "
        "VALUES (?,?,?,?,?)",
        (iso(now), kind, ref,
         json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail else None,
         dedup_key))
    conn.commit()
    return cur.rowcount == 1


def har_handelse(conn: sqlite3.Connection, dedup_key: str) -> bool:
    return conn.execute("SELECT 1 FROM spelai_event WHERE dedup_key=?",
                        (dedup_key,)).fetchone() is not None


# ── nyckel/värde ─────────────────────────────────────────────────────────

def satt(conn: sqlite3.Connection, key: str, value: Optional[str], *,
         source: str, now: dt.datetime) -> None:
    conn.execute("INSERT INTO spelai_state (key, value, set_at, source) "
                 "VALUES (?,?,?,?)", (key, value, iso(now), source))
    conn.commit()


def hamta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM spelai_state WHERE key=? "
                       "ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    return row[0] if row else None


def pausad(conn: sqlite3.Connection) -> bool:
    return hamta(conn, PAUS_KEY) == "1"


def satt_paus(conn: sqlite3.Connection, paus: bool, *, source: str,
              now: dt.datetime) -> dict:
    satt(conn, PAUS_KEY, "1" if paus else "0", source=source, now=now)
    logga(conn, "paus" if paus else "aterupptagen", None,
          {"kalla": source}, now=now)
    return {"pausad": paus, "satt": iso(now)}


def facit_start(conn: sqlite3.Connection) -> Optional[dt.datetime]:
    """Tidpunkten då facitsidan driftsattes (skrivs av migreringen).

    Fönster som öppnade FÖRE den markeras aldrig som missade: facitsidan
    fanns inte då, och gamla `Open`-rader i `draws` är inga missar."""
    return utc(hamta(conn, FACIT_START_KEY))


# ── kvot ─────────────────────────────────────────────────────────────────

def godkant_tak(conn: sqlite3.Connection) -> dict:
    """Taket för AI-körningar per dygn ur BESVARADE beslut.

    Ett kvotbeslut är ett beslut vars valda alternativ bär ett heltalsfält
    `kvot`. Varje besluts EFFEKTIVA svar är dess första icke misstänkta svar
    som inte bara är en kommentar (samma regel som inkorgen); det senast
    givna effektiva kvotsvaret gäller. Utan sådant svar gäller STANDARD_KVOT.
    Taket klipps alltid mot MAX_KORNINGAR_ABS."""
    rows = conn.execute(
        "SELECT i.id, i.alternativ_json, a.id, a.val FROM spelai_inbox i "
        "JOIN spelai_inbox_answer a ON a.id = ("
        "  SELECT b.id FROM spelai_inbox_answer b WHERE b.inbox_id=i.id "
        "  AND b.misstankt=0 AND b.val!='kommentar' ORDER BY b.id LIMIT 1) "
        "WHERE i.typ='beslut' ORDER BY a.id DESC").fetchall()
    for inbox_id, alternativ_json, _answer_id, val in rows:
        try:
            chosen = json.loads(alternativ_json)[int(val)]
        except (ValueError, IndexError, TypeError):
            continue
        kvot = chosen.get("kvot") if isinstance(chosen, dict) else None
        if isinstance(kvot, int) and not isinstance(kvot, bool) and kvot >= 0:
            return {"tak": min(kvot, MAX_KORNINGAR_ABS), "kalla": f"beslut {inbox_id}",
                    "begart": kvot, "abs_tak": MAX_KORNINGAR_ABS}
    return {"tak": STANDARD_KVOT, "kalla": "standard", "begart": None,
            "abs_tak": MAX_KORNINGAR_ABS}


def kvot_idag(conn: sqlite3.Connection, now: dt.datetime) -> dict:
    """Körningar som startat i dag (svensk kalenderdag) mot taket."""
    tak = godkant_tak(conn)
    day = now.astimezone(LOCAL_TZ).date()
    used = 0
    # Tider jämförs som tider: de senaste raderna räcker (taket är <= 12/dygn).
    for (started_at,) in conn.execute(
            "SELECT started_at FROM spelai_run ORDER BY id DESC LIMIT 500"):
        started = utc(started_at)
        if started is not None and started.astimezone(LOCAL_TZ).date() == day:
            used += 1
    return {**tak, "anvanda": used, "kvar": max(0, tak["tak"] - used),
            "dag": day.isoformat()}
