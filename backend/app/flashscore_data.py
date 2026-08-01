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
* **Providers hålls separata.** Flashscore och Sofascore får varsin observation
  i `oddset_result_stats`. Läsningen väljer hem/borta som ett helt providerpar
  inom xG respektive hörnor; `oddset_results.source` beskriver enbart
  resultatets identitet och ändras aldrig av statistik.

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


def _reference_start(store: Storage, result: dict) -> Optional[dt.datetime]:
    """Hämta en entydig, redan observerad avspark för resultatidentiteten."""
    starts = {
        row["match_start_at"] for row in store.oddset_result_stats(
            result["league"], result["date"])
        if (row["date"] == result["date"] and
            row["home"] == result["home"] and row["away"] == result["away"]
            and row.get("match_start_at"))
    }
    day = dt.date.fromisoformat(result["date"])
    matches = store.oddset_matches(
        since=f"{day - dt.timedelta(days=1)}T00:00:00Z",
        until=f"{day + dt.timedelta(days=2)}T00:00:00Z")
    starts.update(
        match["start"] for match in matches
        if (match.get("league") == result["league"] and match.get("start")
            and _same(match.get("home") or "", result.get("home_raw") or result["home"])
            and _same(match.get("away") or "", result.get("away_raw") or result["away"]))
    )
    parsed = set()
    for value in starts:
        try:
            parsed.add(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
        except (AttributeError, ValueError):
            continue
    return next(iter(parsed)) if len(parsed) == 1 else None


def _find_finished(candidates: list[dict], result: dict,
                   reference_start: Optional[dt.datetime]) -> Optional[dict]:
    """Länka bara när lag, faktisk start och normaltidsresultat stämmer."""
    if reference_start is None:
        return None
    target_day = dt.date.fromisoformat(result["date"])
    hits = []
    for candidate in candidates:
        found = _find([candidate], result["league"],
                      result.get("home_raw") or result["home"],
                      result.get("away_raw") or result["away"])
        if not found or not found.get("start_ts"):
            continue
        source_day = dt.datetime.fromtimestamp(
            found["start_ts"], dt.timezone.utc).date()
        if abs((source_day - target_day).days) > 1:
            continue
        source_start = dt.datetime.fromtimestamp(
            found["start_ts"], dt.timezone.utc)
        if abs((source_start - reference_start).total_seconds()) > 90 * 60:
            continue
        if (found.get("home_score") is None or found.get("away_score") is None
                or result.get("hg") is None or result.get("ag") is None
                or int(found["home_score"]) != int(result["hg"])
                or int(found["away_score"]) != int(result["ag"])):
            continue
        hits.append(found)
    return hits[0] if len(hits) == 1 else None


def _find_scheduled(candidates: list[dict], match: dict) -> Optional[dict]:
    """Schemalänk kräver även avspark inom sex timmar, inte bara lagnamn."""
    try:
        start = dt.datetime.fromisoformat(match["start"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return None
    hits = []
    for candidate in candidates:
        found = _find([candidate], match["league"], match["home"], match["away"])
        if not found or not found.get("start_ts"):
            continue
        source_start = dt.datetime.fromtimestamp(
            found["start_ts"], dt.timezone.utc)
        if abs((source_start - start).total_seconds()) <= 6 * 3600:
            hits.append(found)
    return hits[0] if len(hits) == 1 else None


def refresh_xg(store: Storage, force: bool = False) -> dict:
    """Fyll SAKNAD xG på nyss avgjorda matcher ur Flashscores dagsfeeds."""
    from .oddset_data import _mark, _stale
    if not force and not _stale(store, "oddset_fs_xg_at", FS_TTL_H):
        return {}
    now = _now()
    since = (now - dt.timedelta(days=XG_LOOKBACK_DAYS)).date().isoformat()
    from .oddset_data import MODEL_STATS_LEAGUES
    marks = ",".join("?" for _ in MODEL_STATS_LEAGUES)
    missing = [dict(row) for row in store.conn.execute(
        "SELECT r.* FROM oddset_results r LEFT JOIN oddset_result_stats s ON "
        "s.league=r.league AND s.date=r.date AND s.home=r.home AND s.away=r.away "
        "AND s.provider='flashscore' WHERE r.date>=? "
        f"AND r.league IN ({marks}) AND (s.provider IS NULL OR s.xg_h IS NULL "
        "OR s.xg_a IS NULL)",
        (since, *sorted(MODEL_STATS_LEAGUES)))]
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
            candidates = []
            for delta in (0, -1, 1):
                candidates.extend(by_date.get(
                    (day + dt.timedelta(days=delta)).isoformat()) or [])
            found = _find_finished(
                candidates, result, _reference_start(store, result))
            if not found:
                continue
            out["matchade"] += 1
            try:
                stats, observed_at = api.stats(found["flashscore_id"])
            except Exception as exc:  # noqa: BLE001
                out["fel"].append(
                    f"{found['flashscore_id']}: {type(exc).__name__}")
                continue
            if stats.get("xg_home") is None or stats.get("xg_away") is None:
                continue
            out["fyllda"] += store.oddset_save_result_stats({
                "league": result["league"], "date": result["date"],
                "home": result["home"], "away": result["away"],
                "provider": "flashscore",
                "provider_event_id": str(found["flashscore_id"]),
                "observed_at": _iso(observed_at),
                "match_start_at": _iso(dt.datetime.fromtimestamp(
                    found["start_ts"], dt.timezone.utc)),
                "final_home_score": found["home_score"],
                "final_away_score": found["away_score"],
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
    from .oddset_data import RESEARCH_MODEL_LEAGUES, SOFA_UT
    matches = [match for match in store.oddset_matches(
        since=_iso(now), until=_iso(now + dt.timedelta(hours=ABSENCE_WINDOW_H)))
        if match["league"] in SOFA_UT
        and match["league"] not in RESEARCH_MODEL_LEAGUES]
    out = {"kandidater": len(matches), "matchade": 0, "observerade": 0,
           "med_franvaro": 0, "unavailable": 0, "fel": []}
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
            found = _find_scheduled(scheduled, match)
            if not found:
                continue
            out["matchade"] += 1
            try:
                observation, observed_at = api.absence_observation(
                    found["flashscore_id"])
            except Exception as exc:  # noqa: BLE001
                out["fel"].append(
                    f"{found['flashscore_id']}: {type(exc).__name__}")
                # Transportfel säger ingenting om frånvarolistan. Bara ett
                # tolkat källsvar får skapa observed/unavailable-capture.
                continue
            players = observation["players"]
            status = observation["status"]
            if status == "unavailable":
                payload = json.dumps({"provider": "flashscore",
                                      "status": "unavailable",
                                      "event_id": found["flashscore_id"]},
                                     sort_keys=True, separators=(",", ":"))
                store.oddset_save_absence_capture({
                    "match_id": match["id"], "captured_at": _iso(observed_at),
                    "provider": "flashscore", "status": "unavailable",
                    "source_event_id": f"fs:{found['flashscore_id']}",
                    "match_start": match.get("start"), "confirmed": 0,
                    "payload_hash": hashlib.sha256(payload.encode()).hexdigest(),
                }, [])
                out["unavailable"] += 1
                continue
            record = {"home": [], "away": [], "confirmed": 0,
                      "provider": "flashscore", "status": "observed"}
            rows = []
            for player in players:
                raw_id = player.get("player_id")
                entry = {"player_id": f"fs:{raw_id}" if raw_id else None,
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
                "provider": "flashscore", "status": "observed",
                "source_event_id": f"fs:{found['flashscore_id']}",
                "match_start": match.get("start"),
                "confirmed": 0,
                "payload_hash": hashlib.sha256(
                    payload.encode()).hexdigest(),
            }, rows)
            store.meta_set(f"oddset_abs:{match['id']}",
                           json.dumps(record, ensure_ascii=False))
            out["observerade"] += 1
            out["med_franvaro"] += int(bool(players))
    _mark(store, "oddset_fs_abs_at")
    return out
