"""Flashscore som modelldatakälla: frånvaro och xG-komplettering.

Bakgrund (mätt 2026-08-01, se `docs/live-radar-2026-07-25.md`): Flashscore
har statistik minst lika bra som Sofascore i alla våra ligor, och xG där
Sofascore saknar den helt — Allsvenskan hade 0 av 11 hos Sofascore mot 10 av
10 hos Flashscore i mätfönstret. Sofascores Allsvenskan-xG har dessutom
slutat komma in (0 av de 19 senaste, mot 63 % historiskt).

Två medvetna begränsningar:

* **Ingen bakfyllning.** Flashscores dagsfeeds når ~7–8 dygn bakåt och deras
  säsongsfeeds längre än så, men vi använder BARA dagsfeeds. Historiska rader
  ska samlas framåt, inte rekonstrueras i efterhand — samma regel som styr
  pool-PIT och prediktionsledgern.
* **xG skrivs bara där den SAKNAS.** En befintlig Sofascore-siffra skrivs
  aldrig över: att byta värde på redan lagrade modellindata mitt i en
  mätserie vore en tyst ändring av modellens historik. `oddset_results.source`
  bär `+fs` när Flashscore fyllt luckan.

Frånvaron läses via Flashscores publika persisted query (se `flashscore.py`)
och lagras i SAMMA PIT-tabeller som Sofascore-vägen, med
`source_event_id = "fs:<id>"` så proveniensen alltid går att skilja i efterhand.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Optional

from . import flashscore
from .oddset import norm_team
from .storage import Storage

# Hur många dygn bakåt xG-kompletteringen tittar. Dagsfeeds når ~7–8 dygn;
# 5 ger marginal utan att slösa anrop på matcher vi redan fyllt.
XG_LOOKBACK_DAYS = 5
# Frånvaro publiceras nära avspark; samma fönster som Sofascore-vägen använde.
ABSENCE_WINDOW_H = 48
FS_TTL_H = 2


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_country(name: str) -> str:
    """Flashscore märker träningsmatcher med land: 'Chelsea (Eng)'.

    Suffixet är källans egen etikett, inte en del av klubbnamnet, och måste
    bort före normalisering — annars matchar ingen enda träningsmatch.
    """
    return re.sub(r"\s*\([A-Za-z]{2,4}\)\s*$", "", name or "").strip()


def _same(a: str, b: str) -> bool:
    """Konservativ lagjämförelse mellan Flashscore och vår kanon.

    Projektets egen `norm_team` klarar redan klubbprefix och -suffix
    ('BK Häcken' → hacken, 'Kalmar FF' → kalmar). Kvar är svensk genitiv
    ('Östersunds FK' → ostersunds mot Flashscores 'Ostersund'), som tillåts
    med exakt EN teckens skillnad. Medvetet strängare än live-radarns
    prefixregel: en felaktig länk här skriver modelldata, inte ett kort.
    'Inter' ↔ 'Internacional' avvisas därför.
    """
    x, y = norm_team(_strip_country(a)), norm_team(_strip_country(b))
    if not x or not y:
        return False
    if x == y:
        return True
    return x.rstrip("s") == y.rstrip("s") and abs(len(x) - len(y)) <= 1


def _find(candidates: list[dict], league: str, home: str,
          away: str) -> Optional[dict]:
    """Entydig träff eller ingenting — en tvetydig lista länkas aldrig."""
    hits = [c for c in candidates
            if c.get("league") == league
            and _same(c.get("home") or "", home)
            and _same(c.get("away") or "", away)]
    return hits[0] if len(hits) == 1 else None


def refresh_xg(store: Storage, force: bool = False) -> dict:
    """Fyll SAKNAD xG på nyss avgjorda matcher ur Flashscores dagsfeeds."""
    from .oddset_data import _mark, _stale
    if not force and not _stale(store, "oddset_fs_xg_at", FS_TTL_H):
        return {}
    now = _now()
    since = (now - dt.timedelta(days=XG_LOOKBACK_DAYS)).date().isoformat()
    missing = [dict(row) for row in store.conn.execute(
        "SELECT * FROM oddset_results WHERE date>=? AND xg_h IS NULL",
        (since,))]
    out = {"saknade": len(missing), "matchade": 0, "fyllda": 0, "fel": []}
    if not missing:
        _mark(store, "oddset_fs_xg_at")
        return out
    by_date: dict[str, list[dict]] = {}
    with flashscore.Flashscore() as api:
        for offset in range(0, -(XG_LOOKBACK_DAYS + 1), -1):
            try:
                rows, _at = api.day(offset, flashscore.STATUS_FINISHED)
            except Exception as exc:  # noqa: BLE001 — en dag får inte fälla varvet
                out["fel"].append(f"dag {offset}: {type(exc).__name__}")
                continue
            for row in rows:
                if not row.get("start_ts"):
                    continue
                date = dt.datetime.fromtimestamp(
                    row["start_ts"], dt.timezone.utc).date().isoformat()
                by_date.setdefault(date, []).append(row)
        for result in missing:
            # Matcher kring midnatt UTC kan ligga på angränsande dygn hos
            # källan — pröva båda, men bara med entydig lagträff.
            day = dt.date.fromisoformat(result["date"])
            found = None
            for delta in (0, -1, 1):
                candidates = by_date.get(
                    (day + dt.timedelta(days=delta)).isoformat()) or []
                found = _find(candidates, result["league"],
                              result.get("home_raw") or result["home"],
                              result.get("away_raw") or result["away"])
                if found:
                    break
            if not found:
                continue
            out["matchade"] += 1
            try:
                stats, _at = api.stats(found["flashscore_id"])
            except Exception as exc:  # noqa: BLE001
                out["fel"].append(
                    f"{found['flashscore_id']}: {type(exc).__name__}")
                continue
            if stats.get("xg_home") is None or stats.get("xg_away") is None:
                continue
            out["fyllda"] += store.oddset_fill_xg({
                "league": result["league"], "date": result["date"],
                "home": result["home"], "away": result["away"],
                "xg_h": stats["xg_home"], "xg_a": stats["xg_away"],
                "cor_h": stats.get("corners_home"),
                "cor_a": stats.get("corners_away"),
            })
    _mark(store, "oddset_fs_xg_at")
    return out


def refresh_absences(store: Storage, force: bool = False) -> dict:
    """Frånvarande spelare för kommande matcher, ur Flashscores publika väg."""
    from .oddset_data import _mark, _stale
    if not force and not _stale(store, "oddset_fs_abs_at", FS_TTL_H):
        return {}
    now = _now()
    matches = store.oddset_matches(
        since=_iso(now),
        until=_iso(now + dt.timedelta(hours=ABSENCE_WINDOW_H)))
    out = {"kandidater": len(matches), "matchade": 0, "med_franvaro": 0,
           "fel": []}
    if not matches:
        _mark(store, "oddset_fs_abs_at")
        return out
    scheduled: list[dict] = []
    with flashscore.Flashscore() as api:
        for offset in (0, 1, 2):
            try:
                rows, _at = api.day(offset, flashscore.STATUS_SCHEDULED)
            except Exception as exc:  # noqa: BLE001
                out["fel"].append(f"dag {offset}: {type(exc).__name__}")
                continue
            scheduled.extend(rows)
        for match in matches:
            found = _find(scheduled, match["league"], match["home"],
                          match["away"])
            if not found:
                continue
            out["matchade"] += 1
            try:
                players, observed_at = api.absences(found["flashscore_id"])
            except Exception as exc:  # noqa: BLE001
                out["fel"].append(
                    f"{found['flashscore_id']}: {type(exc).__name__}")
                continue
            if not players:
                continue
            record = {"home": [], "away": [], "confirmed": 0}
            rows = []
            for player in players:
                entry = {"player_id": player.get("player_id"),
                         "name": player.get("name"),
                         "position": None,
                         "reason_code": None,
                         "reason": player.get("reason") or "okänd orsak",
                         "description": None, "expected_end": None}
                record[player["side"]].append(entry)
                rows.append({**entry, "side": player["side"]})
            payload = json.dumps(record, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
            store.oddset_save_absence_capture({
                "match_id": match["id"], "captured_at": _iso(observed_at),
                # proveniensen syns i efterhand: fs: = Flashscore-vägen
                "source_event_id": f"fs:{found['flashscore_id']}",
                "match_start": match.get("start"),
                "confirmed": 0,
                "payload_hash": hashlib.sha256(
                    payload.encode()).hexdigest(),
            }, rows)
            store.meta_set(f"oddset_abs:{match['id']}",
                           json.dumps(record, ensure_ascii=False))
            out["med_franvaro"] += 1
    _mark(store, "oddset_fs_abs_at")
    return out
