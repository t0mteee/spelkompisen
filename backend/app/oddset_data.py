"""Datakällor för Oddset-modellen (Etapp 3): resultat, xG och Elo.

- football-data.co.uk (new/SWE.csv, new/NOR.csv): bulk-resultat sedan 2012 med
  Pinnacle-stängningsodds — fit-underlag + framtida backtest. Cache 12 h.
- Sofascore via curl_cffi (Chrome-TLS-imitation — vanlig httpx får 403):
  xG + hörnor + resultat för innevarande säsong. Verifierade id:n i docs/plan.md:
  Allsvenskan = unique-tournament 40, Eliteserien = 20. Paca anropen. Cache 6 h.
- ClubElo (api.clubelo.com/{datum}): hela rankingen i ett anrop. Cache 24 h.

Lagnamn lagras NORMALISERADE (oddset.norm_team) så resultatidentiteter kan
sammanfogas. xG och hörnor lagras som separata providerobservationer och väljs
parvis vid läsning; resultatets källa överlastas aldrig med statistikproveniens.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import time
from typing import Optional

import httpx

from .oddset import RESEARCH_LEAGUE_KEYS, norm_team
from .storage import Storage

FD_URLS = {"allsvenskan": "https://www.football-data.co.uk/new/SWE.csv",
           "eliteserien": "https://www.football-data.co.uk/new/NOR.csv",
           "mls": "https://www.football-data.co.uk/new/USA.csv"}
# De fyra höst/vår-ligorna publiceras som en fil per säsong. Koder och filformat
# verifierades 2026-07-23 mot football-data.co.uk. 2026/27-filen läggs till
# automatiskt när den finns; 404 före premiären är ett förväntat tillstånd.
FD_SEASON_CODES = {
    "premier_league": "E0",
    "championship": "E1",
    "serie_a": "I1",
    "serie_b": "I2",
    "la_liga": "SP1",
    "segunda": "SP2",
    "bundesliga": "D1",
    "zweite_bundesliga": "D2",
}
FD_MIN_SEASON = 2024          # fit-fönster: ~2,5 säsonger räcker med tidsviktning
SOFA_UT = {"allsvenskan": 40, "eliteserien": 20, "superettan": 46,
           "obosligaen": 22, "mls": 242,
           "premier_league": 17, "serie_a": 23, "la_liga": 8,
           "bundesliga": 35}
# OBS: sök ALDRIG fram Sofascore-id:n utan att verifiera sporten — 1420 ("1.
# Divisjon") visade sig vara HANDBOLL och 28937 volleyboll; fotbollens norska
# andraliga är ut 22 ("Norwegian 1st Division", verifierad med lagnamn + xG).
# Superettan/OBOS saknar football-data — Sofascore är enda resultatkällan.
MODEL_LEAGUES = set(FD_URLS) | {"superettan", "obosligaen"}
RESEARCH_MODEL_LEAGUES = set(RESEARCH_LEAGUE_KEYS)
RESULT_LEAGUES = MODEL_LEAGUES | set(FD_SEASON_CODES)
# Avsiktligt xG-scope: ordinarie fitpooler + V2.2:s huvud-/matarligor. Cuper,
# Besta deild och träningsmatcher är resultatfacit, aldrig modellträning.
MODEL_STATS_LEAGUES = RESULT_LEAGUES
# Resultat-ENDAST-ligor (P2, 2026-07-28): utanför football-data OCH utanför
# modellspåret, men värdeflaggorna behöver facitresultat (utfalls-ROI).
# MEDVETET en EGEN tabell, inte SOFA_UT — SOFA_UT ingår i wp9c-POLICY-/
# V2.2-fingeravtrycken och rörs bara vid en omfrysning. Endast slutresultat
# hämtas (inga statistik-anrop): ingen xG, ingen modell, ingen PIT-fråga.
# Cupkvalen delar huvudturneringens UT (verifierat 28/7); bestadeild ut 188
# verifierad fotboll (27/7); friendlies UT 853 är global men resultatrader
# joinas ändå per liga+lag+datum så överskottet är harmlöst.
RESULT_ONLY_UT = {"champions_league": 7, "europa_league": 679,
                  "conference_league": 17015, "bestadeild": 188,
                  "friendlies": 853}
SOFA_MAX_PAGES = 4            # events/last/{page} per körning (backfill tar några pass)

FD_TTL_H, XG_TTL_H, ELO_TTL_H, ABS_TTL_H = 12, 6, 24, 2
# Hellre utebliven Sofascore-frånvaro än fel spelares frånvaro. Lagnamn
# måste matcha, provider-eventet måste ha en avspark nära Oddset-matchen och
# exakt en kandidat måste återstå.
ABSENCE_START_TOLERANCE_MIN = 30

# Databehandlingens version — ingår i signal_version-fingeravtrycken (gransknings-
# punkt 5): bumpa MANUELLT när semantiken i datat ändras utan att en parameter gör
# det. 1 = ursprunglig; 2 = normaltime + identitetsmerge (alias/±1 dygn),
# 2026-07-13; 3 = provideridentitet write-once + per-lagströskel och
# läskarantän för bevisade odds-eventkrockar, 2026-07-26. Sharp-pipelinen ändras
# inte av providerstatistikens modellv4 och behåller därför dataversion 3.
DATA_VERSION = 3
# Målmodellens resultatsammanslagning: 4 = separat providerobservation,
# Flashscore→Sofascore→football-data/legacy och aldrig fältvis källblandning.
MODEL_DATA_VERSION = 4
# missingPlayers-orsakskoder (Sofascore): observerade typer
_ABS_REASON = {0: "annat", 1: "skada", 2: "tveksam", 3: "avstängd",
               11: "avstängd", 12: "avstängd", 13: "avstängd"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _stale(store: Storage, key: str, ttl_h: float) -> bool:
    ts = store.meta_get(key)
    if not ts:
        return True
    try:
        age = _now() - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return age.total_seconds() > ttl_h * 3600
    except ValueError:
        return True


def _mark(store: Storage, key: str) -> None:
    store.meta_set(key, _now().strftime("%Y-%m-%dT%H:%M:%SZ"))


# --- football-data.co.uk ---------------------------------------------------------

def _fd_season_urls(code: str, today: Optional[dt.date] = None) -> list[str]:
    """Rullande football-data-filer från kalenderåret 2024 till aktuell säsong."""
    today = today or _now().date()
    # Europeisk säsong som börjar år Y kodas YY(Y+1), t.ex. 2526.
    current_start = today.year if today.month >= 7 else today.year - 1
    return [
        f"https://www.football-data.co.uk/mmz4281/{year % 100:02d}"
        f"{(year + 1) % 100:02d}/{code}.csv"
        for year in range(FD_MIN_SEASON, current_start + 1)
    ]


def _fd_result_rows(text: str, league: str) -> list[dict]:
    """Normalisera både football-datas nya landsfiler och klassiska ligafiler."""
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        raw_date = row.get("Date")
        try:
            parsed_date = None
            for fmt in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    parsed_date = dt.datetime.strptime(raw_date or "", fmt).date()
                    break
                except ValueError:
                    continue
            if parsed_date is None or parsed_date.year < FD_MIN_SEASON:
                continue
            home = row.get("Home") or row.get("HomeTeam")
            away = row.get("Away") or row.get("AwayTeam")
            hg_raw = row.get("HG") if row.get("HG") not in (None, "") else row.get("FTHG")
            ag_raw = row.get("AG") if row.get("AG") not in (None, "") else row.get("FTAG")
            hg, ag = int(hg_raw), int(ag_raw)
            if not home or not away:
                continue
        except (TypeError, ValueError):
            continue
        result = {
            "league": league, "date": parsed_date.isoformat(),
            "home": norm_team(home), "away": norm_team(away),
            "home_raw": home, "away_raw": away,
            "hg": hg, "ag": ag, "source": "fd",
        }
        try:
            if row.get("HC") not in (None, "") and row.get("AC") not in (None, ""):
                result["cor_h"], result["cor_a"] = float(row["HC"]), float(row["AC"])
                result["stats_provider"] = "football_data"
        except ValueError:
            pass
        rows.append(result)
    return rows


def refresh_results(store: Storage, force: bool = False) -> dict:
    out = {}
    sources = {
        **{league: [url] for league, url in FD_URLS.items()},
        **{league: _fd_season_urls(code)
           for league, code in FD_SEASON_CODES.items()},
    }
    for lg, urls in sources.items():
        if not force and not _stale(store, f"oddset_fd_at:{lg}", FD_TTL_H):
            continue
        n = 0
        errors = []
        parsed = []
        for url in urls:
            try:
                r = httpx.get(url, timeout=30, follow_redirects=True)
                if r.status_code == 404 and lg in FD_SEASON_CODES:
                    continue
                r.raise_for_status()
                parsed.extend(_fd_result_rows(r.text, lg))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url.rsplit('/', 2)[-2]}: {exc}")
        if not parsed:
            out[lg] = "fel: " + "; ".join(errors or ["inga publicerade filer"])
            continue
        with store.bulk():   # WP0: EN transaktion i stället för ~1 700 commits
            for row in parsed:
                store.oddset_save_result(row)
                n += 1
        _mark(store, f"oddset_fd_at:{lg}")
        out[lg] = n if not errors else {"rows": n, "errors": errors}
    return out


# --- Sofascore (xG) ----------------------------------------------------------------

def _sofa_get(path: str, timeout: float = 20.0):
    from curl_cffi import requests as cffi
    r = cffi.get(f"https://api.sofascore.com/api/v1{path}",
                 impersonate="chrome", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _sofa_season(store: Storage, lg: str,
                 ut: Optional[int] = None) -> Optional[int]:
    """Innevarande säsongs id, cachat i meta (30 d).

    Tournament-id ingår i cachevärdet. Det förhindrar att ett gammalt säsongs-id
    från en felaktigt identifierad sport återanvänds efter att SOFA_UT rättats
    (OBOS hade kvar handbollssäsongen 97377 trots korrekt fotbolls-UT 22).
    `ut` låter resultat-ENDAST-ligorna (RESULT_ONLY_UT) använda samma väg
    utan att stå i SOFA_UT.
    """
    ut = SOFA_UT[lg] if ut is None else ut
    key = f"oddset_sofa_season:{lg}"
    cached = store.meta_get(key)
    if cached:
        try:
            tournament_id, sid, at = cached.split("|")
            if (int(tournament_id) == ut and
                    (_now() - dt.datetime.fromisoformat(at)).days < 30):
                return int(sid)
        except ValueError:
            pass
    try:
        seasons = _sofa_get(f"/unique-tournament/{ut}/seasons")["seasons"]
        sid = seasons[0]["id"]
        store.meta_set(key, f"{ut}|{sid}|{_now().isoformat()}")
        return sid
    except Exception:  # noqa: BLE001
        return None


def _ingest_event(store: Storage, lg: str, e: dict,
                  results_only: bool = False) -> bool:
    """Spara ett avslutat Sofascore-event (resultat + xG + hörnor).

    Resultatet är användbart även om statistik-anropet tillfälligt fallerar och
    sparas därför direkt. Eventet markeras däremot inte som färdigbehandlat
    förrän statistik-endpointen svarat (404/410 = permanent utan statistik).
    På så vis kan nästa 6h-varv fylla xG/hörnor i stället för att luckan blir
    permanent. False betyder känt/ej avslutat eller väntar på retry.

    `results_only` (RESULT_ONLY_UT-ligorna): hoppa över statistik-anropet
    helt — slutresultatet är hela behovet och varje extra anrop mot den
    delade källan är en kostnad (samma artighetsprincip som live-radarns
    matchtak).
    """
    if e.get("status", {}).get("type") != "finished":
        return False
    eid = e["id"]
    if store.meta_get(f"oddset_sofa_seen:{eid}"):
        return False
    date = dt.datetime.fromtimestamp(
        e["startTimestamp"], dt.timezone.utc).strftime("%Y-%m-%d")
    # normaltime, inte current: för slutspel/cup inkluderar current straffar
    # (Montreal–Atlanta 2024 blev "6-7" i stället för 2-2 — hittad av
    # merge-vakten 2026-07-13)
    hs, as_ = e.get("homeScore", {}), e.get("awayScore", {})
    row = {"league": lg, "date": date,
           "home": norm_team(e["homeTeam"]["name"]),
           "away": norm_team(e["awayTeam"]["name"]),
           "home_raw": e["homeTeam"]["name"],
           "away_raw": e["awayTeam"]["name"],
           "hg": hs.get("normaltime", hs.get("current")),
           "ag": as_.get("normaltime", as_.get("current")),
           "source": "sofa"}
    # Basresultatet ska inte gå förlorat bara för att detaljstatistiken ligger
    # nere; en senare lyckad detaljhämtning får en egen providerobservation.
    store.oddset_save_result(row)
    if results_only:
        store.meta_set(f"oddset_sofa_seen:{eid}", row["date"])
        return True
    time.sleep(1.1)
    try:
        payload = _sofa_get(f"/event/{eid}/statistics")
    except Exception as exc:  # noqa: BLE001 — 403/429/5xx ska försökas igen
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status not in (404, 410):
            retry_key = f"oddset_sofa_retry:{eid}"
            attempts = 0
            try:
                attempts = int(json.loads(store.meta_get(retry_key) or "{}").get(
                    "attempts", 0))
            except (ValueError, TypeError):
                pass
            store.meta_set(retry_key, json.dumps({
                "attempts": attempts + 1,
                "last_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "error": type(exc).__name__,
                "status": status,
            }))
            return False
        payload = {}  # permanent avsaknad: resultatet är komplett utan stats

    stats = payload.get("statistics") or []
    groups = (stats[0].get("groups", []) if stats else [])
    for g in groups:
        for s in g.get("statisticsItems", []):
            if s.get("name") == "Expected goals":
                row["xg_h"] = float(s["home"])
                row["xg_a"] = float(s["away"])
            elif s.get("name") == "Corner kicks":
                row["cor_h"] = float(s["home"])
                row["cor_a"] = float(s["away"])
    row.update({
        "stats_provider": "sofascore",
        "provider_event_id": str(eid),
        "stats_observed_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "match_start_at": dt.datetime.fromtimestamp(
            e["startTimestamp"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    store.oddset_save_result(row)
    store.meta_delete(f"oddset_sofa_retry:{eid}")
    store.meta_set(f"oddset_sofa_seen:{eid}", row["date"])
    return True


def refresh_results_extra(store: Storage, force: bool = False) -> dict:
    """Slutresultat för resultat-ENDAST-ligorna (RESULT_ONLY_UT).

    Samma sid-/säsongsväg som refresh_xg men utan statistik-anrop: en
    sidhämtning per varv och liga när cachen är kall, inget mer. Utfalls-
    facitet (oddset_value.resolve_outcomes) är enda konsumenten."""
    out = {}
    for lg, ut in RESULT_ONLY_UT.items():
        if not force and not _stale(store, f"oddset_resx_at:{lg}", FD_TTL_H):
            continue
        sid = _sofa_season(store, lg, ut)
        if not sid:
            out[lg] = "ingen säsong"
            continue
        n_new = 0
        failed = None
        for page in range(SOFA_MAX_PAGES):
            try:
                evs = _sofa_get(
                    f"/unique-tournament/{ut}/season/{sid}/events/last/{page}") \
                    .get("events") or []
            except Exception as e:  # noqa: BLE001
                # Sofascore svarar 404 EFTER sista sidan (inte tom lista) —
                # för en cup med en enda sida är 404 på sida 1 normalflöde,
                # inte ett fel. Uppmätt 28/7: sida 0 ingesterades och felet
                # skrev över räknaren. Bara sida 0-fel är ett riktigt fel.
                status = getattr(getattr(e, "response", None),
                                 "status_code", None)
                if page > 0 and status == 404:
                    break
                failed = f"fel: {e}"
                break
            if not evs:
                break
            new_on_page = sum(
                _ingest_event(store, lg, e, results_only=True)
                for e in evs)
            n_new += new_on_page
            if new_on_page == 0:
                break   # hela sidan redan känd -> äldre sidor också
        if failed and not n_new:
            out[lg] = failed
            continue
        _mark(store, f"oddset_resx_at:{lg}")
        out[lg] = n_new
    return out


def refresh_xg(store: Storage, force: bool = False) -> dict:
    """Hämta Sofa-xG/hörnor för färdigspelade matcher (innevarande säsong)."""
    out = {}
    for lg, ut in SOFA_UT.items():
        if not force and not _stale(store, f"oddset_xg_at:{lg}", XG_TTL_H):
            continue
        sid = _sofa_season(store, lg)
        if not sid:
            out[lg] = "ingen säsong"
            continue
        n_new = 0
        try:
            for page in range(SOFA_MAX_PAGES):
                evs = _sofa_get(f"/unique-tournament/{ut}/season/{sid}/events/last/{page}") \
                    .get("events") or []
                if not evs:
                    break
                new_on_page = sum(_ingest_event(store, lg, e) for e in evs)
                n_new += new_on_page
                if new_on_page == 0:
                    break   # hela sidan redan känd -> äldre sidor också
        except Exception as e:  # noqa: BLE001
            out[lg] = f"fel: {e}"
            continue
        _mark(store, f"oddset_xg_at:{lg}")
        out[lg] = n_new
    return out


def xg_backfill(store: Storage, seasons_back: int = 2, max_pages: int = 12) -> dict:
    """Engångs-backfill: xG/hörnor för TIDIGARE säsonger (till backtest v2 och
    hörn-modellen). ~240 matcher/säsong/liga, pacat — kör i bakgrunden."""
    out = {}
    for lg, ut in SOFA_UT.items():
        n = 0
        try:
            seasons = _sofa_get(f"/unique-tournament/{ut}/seasons")["seasons"]
        except Exception as e:  # noqa: BLE001
            out[lg] = f"fel: {e}"
            continue
        for s in seasons[:1 + seasons_back]:   # inkl. innevarande (djupa sidor)
            try:
                for page in range(max_pages):
                    evs = _sofa_get(f"/unique-tournament/{ut}/season/{s['id']}"
                                    f"/events/last/{page}").get("events") or []
                    if not evs:
                        break
                    n += sum(_ingest_event(store, lg, e) for e in evs)
            except Exception:  # noqa: BLE001 — nästa säsong ändå
                continue
        out[lg] = n
    return out


# --- ClubElo -----------------------------------------------------------------------

CLUBELO_BASE = "http://api.clubelo.com"
ELO_COUNTRIES = Storage.ODDSET_ELO_COUNTRIES


def parse_elo_csv(text: str) -> list[dict]:
    """Läs ClubElos ranking/historik och bevara dess giltighetsintervall."""
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        if row.get("Country") not in ELO_COUNTRIES:
            continue
        try:
            club_raw = row["Club"].strip()
            valid_from = dt.date.fromisoformat(row["From"]).isoformat()
            valid_to = dt.date.fromisoformat(row["To"]).isoformat()
            elo = float(row["Elo"])
            level = int(row["Level"]) if row.get("Level") not in (None, "") else None
        except (ValueError, KeyError, AttributeError):
            continue
        if not club_raw or valid_to < valid_from:
            continue
        rows.append({
            "club_key": norm_team(club_raw), "club_raw": club_raw,
            "country": row["Country"], "level": level, "elo": elo,
            "valid_from": valid_from, "valid_to": valid_to,
        })
    return rows


def fetch_elo_csv(identifier: str) -> str:
    r = httpx.get(f"{CLUBELO_BASE}/{identifier}", timeout=60,
                  follow_redirects=True,
                  headers={"User-Agent": "spelkompisen/1.0 (local personal tool)"})
    r.raise_for_status()
    return r.text


def save_elo_capture(store: Storage, requested_date: str, text: str,
                     source: str = "daily", captured_at: Optional[str] = None) -> int:
    """Spara endast ett komplett, icke-tomt svar för ligornas länder."""
    ratings = parse_elo_csv(text)
    if not ratings:
        return 0
    at = captured_at or _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    payload_hash = hashlib.sha256(text.encode()).hexdigest()
    saved = store.oddset_save_elo_capture({
        "captured_at": at, "requested_date": requested_date,
        "source": source, "payload_hash": payload_hash,
    }, ratings)
    # Datumrankingen bär själv providerintervallen From/To. Spara dem även i
    # PIT-lagret så att daglig drift successivt fyller framtida historik och så
    # att ett idempotent capture-retry kan reparera saknade intervall.
    store.oddset_save_elo_history(ratings, at)
    return saved


def refresh_elo(store: Storage, force: bool = False) -> Optional[int]:
    if not force and not _stale(store, "oddset_elo_at", ELO_TTL_H):
        return None
    requested_date = _now().strftime("%Y-%m-%d")
    try:
        text = fetch_elo_csv(requested_date)
    except Exception:  # noqa: BLE001
        return None
    ratings = parse_elo_csv(text)
    elo = {r["club_key"]: round(r["elo"]) for r in ratings}
    if elo:
        save_elo_capture(store, requested_date, text)
        store.meta_set("oddset_elo", json.dumps(elo, ensure_ascii=False))
        _mark(store, "oddset_elo_at")
    return len(elo)


def get_elo(store: Storage, as_of: Optional[str] = None) -> dict[str, int]:
    if as_of is not None:
        return store.oddset_elo_as_of(as_of[:10])
    latest = store.oddset_latest_elo()
    if latest:
        return latest
    try:
        return json.loads(store.meta_get("oddset_elo") or "{}")
    except ValueError:
        return {}


def _absence_entry(raw: dict) -> dict:
    """Normalisera ett Sofascore-missingPlayer utan att kasta provideridentitet."""
    player = raw.get("player") or {}
    code = raw.get("reason")
    return {
        "player_id": player.get("id"),
        "name": player.get("name"),
        "position": player.get("position"),
        "reason_code": code,
        "reason": _ABS_REASON.get(code, f"kod {code}"),
        "description": raw.get("description"),
        "expected_end": raw.get("expectedEndDate"),
    }


def _sofa_absence_event(candidates: list[dict], match: dict,
                        team_similarity) -> Optional[dict]:
    """Entydig Sofascore-länk för frånvaro, inklusive avspark.

    Namnlikhet ensam är inte en matchidentitet: samma feed kan innehålla
    herr-, U23- och reservlag med nästan samma namn. Saknad/ogiltig avspark,
    fler än en kandidat eller en tidsavvikelse över toleransen stänger därför
    länken i stället för att välja första träffen.
    """
    try:
        target_start = dt.datetime.fromisoformat(
            str(match["start"]).replace("Z", "+00:00"))
        if target_start.tzinfo is None:
            target_start = target_start.replace(tzinfo=dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    home = norm_team(match.get("home") or "")
    away = norm_team(match.get("away") or "")
    hits = []
    for event in candidates:
        try:
            source_start = dt.datetime.fromtimestamp(
                float(event["startTimestamp"]), dt.timezone.utc)
            source_home = norm_team(event["homeTeam"]["name"])
            source_away = norm_team(event["awayTeam"]["name"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if abs(source_start - target_start) > dt.timedelta(
                minutes=ABSENCE_START_TOLERANCE_MIN):
            continue
        if (team_similarity(home, source_home) >= 0.75 and
                team_similarity(away, source_away) >= 0.75):
            hits.append(event)
    return hits[0] if len(hits) == 1 else None


def refresh_absences(store: Storage, force: bool = False) -> dict:
    """Frånvarolistor (skador/avstängningar/tveksamma) + bekräftade elvor från
    Sofascore /event/{id}/lineups för kommande matcher (<48 h). Strukturerad
    skadedata — gratis, från källan vi redan kör. 404 = elvor ej publicerade än.
    Sparas i meta oddset_abs:{match_id}; visas i UI (🚑) och detaljvyn."""
    if not force and not _stale(store, "oddset_abs_at", ABS_TTL_H):
        return {}
    from .oddset import norm_team, _team_sim
    now = _now()
    frm = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    to = (now + dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ms = [m for m in store.oddset_matches(since=frm, until=to)
          if m["league"] in SOFA_UT and
          m["league"] not in RESEARCH_MODEL_LEAGUES]
    # Båda providrarna samlas. Visningen väljer en hel capture explicit i
    # Storage; en tunn Flashscore-lista får därför aldrig blockera Sofascores
    # position/framträdanden/rating.
    out = {"checked": 0, "found": 0, "unavailable": 0}
    ev_index: dict[str, list[dict]] = {}
    for lg in {m["league"] for m in ms}:
        sid = _sofa_season(store, lg)
        if not sid:
            continue
        try:
            evs = _sofa_get(f"/unique-tournament/{SOFA_UT[lg]}/season/{sid}"
                            f"/events/next/0").get("events") or []
        except Exception:  # noqa: BLE001
            continue
        ev_index[lg] = evs
    for m in ms:
        cands = ev_index.get(m["league"]) or []
        event = _sofa_absence_event(cands, m, _team_sim)
        if event is None:
            continue
        eid = event["id"]
        out["checked"] += 1
        time.sleep(1.0)
        try:
            lu = _sofa_get(f"/event/{eid}/lineups")
        except Exception as exc:  # noqa: BLE001 — 404 tills lineups publicerats
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 404:
                # Nät-/transportfel bevisar inte att källan saknar data.
                continue
            captured_at = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
            payload = json.dumps({"provider": "sofascore", "status": "unavailable",
                                  "event_id": str(eid)}, sort_keys=True)
            store.oddset_save_absence_capture({
                "match_id": m["id"], "captured_at": captured_at,
                "provider": "sofascore", "status": "unavailable",
                "source_event_id": str(eid), "match_start": m.get("start"),
                "confirmed": False,
                "payload_hash": hashlib.sha256(payload.encode()).hexdigest(),
            }, [])
            out["unavailable"] += 1
            continue
        captured_at = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
        rec = {"at": captured_at, "confirmed": bool(lu.get("confirmed")),
               "source_event_id": str(eid)}
        players = []
        ut, sid = SOFA_UT[m["league"]], _sofa_season(store, m["league"])
        for side in ("home", "away"):
            rec[side] = []
            for p in (lu.get(side) or {}).get("missingPlayers") or []:
                entry = _absence_entry(p)
                # spelarens säsongsstatus: få matcher = marginell frånvaro som
                # inte ska väga tungt (Samans poäng — en reserv borta är inte
                # samma sak som en ordinarie)
                if entry.get("player_id"):
                    time.sleep(0.8)
                    try:
                        st = _sofa_get(f"/player/{entry['player_id']}/unique-tournament/{ut}"
                                       f"/season/{sid}/statistics/overall") \
                            .get("statistics") or {}
                        entry["apps"] = st.get("appearances")
                        if st.get("rating"):
                            entry["rating"] = round(st["rating"], 2)
                    except Exception:  # noqa: BLE001 — ingen säsongsstatistik = okänd
                        pass
                rec[side].append(entry)
                players.append({**entry, "side": side})
        payload = json.dumps(rec, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
        store.oddset_save_absence_capture({
            "match_id": m["id"], "captured_at": captured_at,
            "provider": "sofascore", "status": "observed",
            "source_event_id": str(eid), "match_start": m.get("start"),
            "confirmed": rec["confirmed"],
            "payload_hash": hashlib.sha256(payload.encode()).hexdigest(),
        }, players)
        store.meta_set(f"oddset_abs:{m['id']}", json.dumps(rec, ensure_ascii=False))
        out["found"] += 1
    _mark(store, "oddset_abs_at")
    return out


def get_absences(store: Storage, match_ids: list[str]) -> dict[str, dict]:
    out = store.oddset_latest_absences(match_ids)
    for mid in (m for m in match_ids if m not in out):
        raw = store.meta_get(f"oddset_abs:{mid}")
        if raw:
            try:
                out[mid] = json.loads(raw)
            except ValueError:
                pass
    return out


def refresh_all(store: Storage, force: bool = False) -> dict:
    """Körs i varje insamlingspass — throttlarna gör det billigt."""
    from . import oddset_schedule
    # Resultatskelettet måste finnas INNAN providerstatistik länkas. Därefter
    # samlas Flashscore och Sofascore oberoende i separata rader. Modelläsningen
    # väljer Flashscore→Sofascore deterministiskt; körordning kan inte längre
    # skriva om eller blanda en observation.
    from . import flashscore_data
    out = {"results": refresh_results(store, force),
           "results_extra": refresh_results_extra(store, force)}
    for name, fn in (("fs_xg", flashscore_data.refresh_xg),
                     ("fs_absences", flashscore_data.refresh_absences)):
        try:
            out[name] = fn(store, force)
        except Exception as exc:  # noqa: BLE001 — får aldrig fälla varvet
            out[name] = {"error": f"{type(exc).__name__}: {str(exc)[:80]}"}
    out.update({"xg": refresh_xg(store, force),
                "elo": refresh_elo(store, force),
                "absences": refresh_absences(store, force)})
    try:
        out["team_events"] = oddset_schedule.refresh(store, force=force)
    except Exception as exc:  # noqa: BLE001 — WP9c får inte fälla övrig insamling
        out["team_events"] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


# Manuella lagnamns-alias (identitetslager, granskning 2026-07-13): källnamn →
# football-data-kanoniskt namn, per liga. Fuzzy-tröskeln 0.7 missar dessa
# (la galaxy↔los angeles galaxy = 0.67 → laget splittrades i två identiteter i
# fitten). Runtime-tillägg utan deploy: meta-nyckeln oddset_alias:{liga} (JSON).
TEAM_ALIAS = {
    "allsvenskan": {
        "halmstads": "halmstad", "ifk goteborg": "goteborg",
        "djurgardens": "djurgarden", "ifk norrkoping": "norrkoping",
        "ifk varnamo": "varnamo", "osters": "oster",
        "landskrona bois": "landskrona",
    },
    "eliteserien": {
        "tromso il": "tromso", "sandefjord fotball": "sandefjord",
        "odds": "odd", "aalesunds": "aalesund",
    },
    "mls": {
        "la galaxy": "los angeles galaxy", "atlanta united": "atlanta utd",
    },
    "premier_league": {
        "coventry city": "coventry", "manchester united": "man united",
        "ipswich town": "ipswich", "nottingham": "nottm forest",
        "manchester city": "man city", "newcastle united": "newcastle",
    },
    "serie_a": {"internazionale": "inter"},
    "la_liga": {
        "racing santander": "santander", "espanyol": "espanol",
        "dep la coruna": "la coruna",
        "deportivo la coruna": "la coruna", "celta vigo": "celta",
        "real sociedad": "sociedad", "athletic bilbao": "ath bilbao",
        "rayo vallecano": "vallecano", "atletico madrid": "ath madrid",
        "real betis": "betis",
    },
    "bundesliga": {
        "bayern munchen": "bayern munich",
        "borussia mgladbach": "mgladbach",
        "bayer leverkusen": "leverkusen",
        "borussia dortmund": "dortmund", "1 koln": "koln",
        "tsg hoffenheim": "hoffenheim",
        "1 union berlin": "union berlin",
        "eintracht frankfurt": "ein frankfurt",
        "mainz 05": "mainz", "paderborn 07": "paderborn",
        "hamburger sv": "hamburg",
    },
}
TEAM_REJECTED_LINKS = {
    "eliteserien": {("egersund", "haugesund")},
}
FUZZY_AUTO_MIN = 0.75
FUZZY_SUGGEST_MIN = 0.55


def _alias_map(store: Storage, league: str) -> dict[str, str]:
    m = dict(TEAM_ALIAS.get(league, {}))
    try:
        m.update(json.loads(store.meta_get(f"oddset_alias:{league}") or "{}"))
    except ValueError:
        pass
    return m


def merged_results(store: Storage, league: str,
                   audit: Optional[dict] = None) -> list[dict]:
    """Resultat med källorna ihopslagna: Sofascore-lagnamn kanoniseras till
    football-data-namnen (alias-tabell → exakt → fuzzy >0.7) och dubblettrader
    för samma match slås ihop (providerprioritet per statistikpar). Matchnyckeln tål ±1 dygns datumskillnad
    mellan källorna (MLS: Sofascore = UTC-datum, football-data = lokalt/brittiskt
    → 304 dubbletter i fitten före fixen) — kräver samma lagpar, olika källor och
    samma mål. audit (dict) fylls med alla automatiska/öppna identitetsbeslut:
    'fuzzy_links' = alla icke-exakta/icke-alias-länkar med likhet, antal berörda
    matcher och verified=False (godkänd länk ska flyttas till alias-tabellen),
    'unmatched' = namn som inte kunde kanoniseras (med bästa förslag + likhet),
    'date_dups' = kvarvarande par samma lag/olika källa inom ±1 dygn."""
    from .oddset import _team_sim
    rows = [dict(r) for r in store.oddset_results(league)]
    alias = _alias_map(store, league)
    canon = sorted({r[side] for r in rows if r.get("source") == "fd"
                    for side in ("home", "away")})
    fuzzy_links: dict[tuple[str, str], dict] = {}
    unmatched_links: dict[tuple[str, str], dict] = {}
    rejected_links: dict[tuple[str, str], dict] = {}

    stats_priority = {provider: index for index, provider in
                      enumerate(Storage.RESULT_STATS_PRIORITY)}

    def provider_rank(provider: Optional[str]) -> tuple:
        return (stats_priority.get(provider, len(stats_priority)), provider or "")

    def merge_into(base: dict, fill: dict) -> None:
        """Slå ihop identitet/resultat och bevara hela hem/borta-par.

        xG och hörnor är olika statistikfamiljer och får ha olika providers,
        men hem/borta inom ett par får aldrig plockas fältvis från olika källor.
        """
        for key in ("hg", "ag"):
            if base.get(key) is None and fill.get(key) is not None:
                base[key] = fill[key]
        # xG-paret och hörnparet väljs var för sig, men aldrig ett fält i paret
        # från vardera källa. Då kan FS-xG samexistera med football-data-hörnor.
        if (fill.get("xg_h") is not None and fill.get("xg_a") is not None and
                (base.get("xg_h") is None or base.get("xg_a") is None or
                 provider_rank(fill.get("xg_provider")) <
                 provider_rank(base.get("xg_provider")))):
            for key in ("xg_h", "xg_a", "xg_provider",
                        "xg_provider_event_id", "xg_observed_at"):
                base[key] = fill.get(key)
        if (fill.get("cor_h") is not None and fill.get("cor_a") is not None and
                (base.get("cor_h") is None or base.get("cor_a") is None or
                 provider_rank(fill.get("corners_provider")) <
                 provider_rank(base.get("corners_provider")))):
            for key in ("cor_h", "cor_a", "corners_provider",
                        "corners_provider_event_id", "corners_observed_at"):
                base[key] = fill.get(key)
        base["stats_provider"] = (base.get("xg_provider") or
                                  base.get("corners_provider"))

    def to_canon(name: str, match_key: tuple) -> str:
        if not canon or name in canon:
            return name          # en-källe-liga (Superettan/OBOS) kanoniserar inte
        if name in alias:
            return alias[name]   # manuellt verifierad koppling vinner
        best, best_s = name, FUZZY_AUTO_MIN
        for c in canon:
            s = _team_sim(name, c)
            if s > best_s:
                best, best_s = c, s
        if best != name and audit is not None:
            link = fuzzy_links.setdefault((name, best), {
                "source_name": name, "target_name": best,
                "sim": round(best_s, 3), "verified": False,
                "_matches": set(),
            })
            link["_matches"].add(match_key)
        elif best == name and audit is not None:
            # föreslå i stället för att tyst lämna osammanslaget
            cand = max(((c, _team_sim(name, c)) for c in canon),
                       key=lambda t: t[1], default=(None, 0.0))
            if cand[0] and cand[1] >= FUZZY_SUGGEST_MIN:
                pair = (name, cand[0])
                rejected = pair in TEAM_REJECTED_LINKS.get(league, set())
                bucket = rejected_links if rejected else unmatched_links
                link = bucket.setdefault(pair, {
                    "name": name, "suggestion": cand[0],
                    "sim": round(cand[1], 2), "_matches": set(),
                })
                link["_matches"].add(match_key)
        return best

    merged: dict[tuple, dict] = {}
    for r in rows:
        if r.get("source") != "fd":
            raw_match = (r["source"], r["date"], r["home"], r["away"])
            r["home"], r["away"] = (to_canon(r["home"], raw_match),
                                      to_canon(r["away"], raw_match))
        key = (r["date"], r["home"], r["away"])
        prev = merged.get(key)
        if not prev:
            merged[key] = r
            continue
        merge_into(prev, r)

    if audit is not None:
        links = []
        for link in fuzzy_links.values():
            links.append({
                "source_name": link["source_name"],
                "target_name": link["target_name"],
                "sim": link["sim"], "matches": len(link["_matches"]),
                "verified": link["verified"],
            })
        audit["fuzzy_links"] = sorted(
            links, key=lambda link: (-link["matches"], link["source_name"]))
        if unmatched_links:
            audit["unmatched"] = sorted(({
                "name": link["name"], "suggestion": link["suggestion"],
                "sim": link["sim"], "matches": len(link["_matches"]),
            } for link in unmatched_links.values()),
                key=lambda link: (-link["matches"], link["name"]))
        if rejected_links:
            audit["rejected_links"] = sorted(({
                "source_name": link["name"], "target_name": link["suggestion"],
                "sim": link["sim"], "matches": len(link["_matches"]),
                "verified": True, "decision": "rejected",
            } for link in rejected_links.values()),
                key=lambda link: (-link["matches"], link["source_name"]))

    # datumtolerans: samma lagpar från OLIKA källor ±1 dygn med samma mål =
    # samma match (fd-raden är bas — backtestens xG-koppling nycklar på fd-datum)
    by_pair: dict[tuple, list[dict]] = {}
    for r in merged.values():
        by_pair.setdefault((r["home"], r["away"]), []).append(r)
    out: list[dict] = []
    for pair_rows in by_pair.values():
        pair_rows.sort(key=lambda r: r["date"])
        i = 0
        while i < len(pair_rows):
            r, nxt = pair_rows[i], pair_rows[i + 1] if i + 1 < len(pair_rows) else None
            if nxt is not None and _same_match(r, nxt):
                base, fill = (r, nxt) if r.get("source") == "fd" else (nxt, r)
                merge_into(base, fill)
                out.append(base)
                i += 2
                continue
            if nxt is not None and audit is not None \
                    and _date_gap(r, nxt) <= 1 and r.get("source") != nxt.get("source"):
                audit.setdefault("date_dups", []).append(
                    {"pair": f"{r['home']}–{r['away']}", "dates": [r["date"], nxt["date"]],
                     "note": "olika mål — mergas ej"})
            out.append(r)
            i += 1
    return sorted(out, key=lambda r: r["date"])


def _date_gap(a: dict, b: dict) -> int:
    try:
        return abs((dt.date.fromisoformat(b["date"])
                    - dt.date.fromisoformat(a["date"])).days)
    except ValueError:
        return 99


def _same_match(a: dict, b: dict) -> bool:
    """Samma lagpar inom ±1 dygn från olika källor räknas som samma match —
    men bara om målen stämmer överens (skydd mot t.ex. omspel/felmatchning)."""
    if a.get("source") == b.get("source") or _date_gap(a, b) > 1:
        return False
    for k in ("hg", "ag"):
        if a.get(k) is not None and b.get(k) is not None and a[k] != b[k]:
            return False
    return True
