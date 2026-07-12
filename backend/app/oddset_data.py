"""Datakällor för Oddset-modellen (Etapp 3): resultat, xG och Elo.

- football-data.co.uk (new/SWE.csv, new/NOR.csv): bulk-resultat sedan 2012 med
  Pinnacle-stängningsodds — fit-underlag + framtida backtest. Cache 12 h.
- Sofascore via curl_cffi (Chrome-TLS-imitation — vanlig httpx får 403):
  xG + hörnor + resultat för innevarande säsong. Verifierade id:n i docs/plan.md:
  Allsvenskan = unique-tournament 40, Eliteserien = 20. Paca anropen. Cache 6 h.
- ClubElo (api.clubelo.com/{datum}): hela rankingen i ett anrop. Cache 24 h.

Lagnamn lagras NORMALISERADE (oddset.norm_team) så källorna kolliderar på PK
och xG fyller på resultatraderna via COALESCE-upsert.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import time
from typing import Optional

import httpx

from .oddset import norm_team
from .storage import Storage

FD_URLS = {"allsvenskan": "https://www.football-data.co.uk/new/SWE.csv",
           "eliteserien": "https://www.football-data.co.uk/new/NOR.csv"}
FD_MIN_SEASON = 2024          # fit-fönster: ~2,5 säsonger räcker med tidsviktning
SOFA_UT = {"allsvenskan": 40, "eliteserien": 20, "superettan": 46}
# Superettan saknar football-data — Sofascore är enda resultatkällan (xG finns!).
MODEL_LEAGUES = set(FD_URLS) | {"superettan"}
SOFA_MAX_PAGES = 4            # events/last/{page} per körning (backfill tar några pass)

FD_TTL_H, XG_TTL_H, ELO_TTL_H = 12, 6, 24


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

def refresh_results(store: Storage, force: bool = False) -> dict:
    out = {}
    for lg, url in FD_URLS.items():
        if not force and not _stale(store, f"oddset_fd_at:{lg}", FD_TTL_H):
            continue
        try:
            r = httpx.get(url, timeout=30, follow_redirects=True)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            out[lg] = f"fel: {e}"
            continue
        n = 0
        reader = csv.DictReader(io.StringIO(r.text.lstrip("﻿")))
        for row in reader:
            try:
                season = int((row.get("Season") or "0")[:4])
                if season < FD_MIN_SEASON:
                    continue
                d = dt.datetime.strptime(row["Date"], "%d/%m/%Y").strftime("%Y-%m-%d")
                hg, ag = int(row["HG"]), int(row["AG"])
            except (ValueError, KeyError):
                continue
            store.oddset_save_result({
                "league": lg, "date": d,
                "home": norm_team(row["Home"]), "away": norm_team(row["Away"]),
                "home_raw": row["Home"], "away_raw": row["Away"],
                "hg": hg, "ag": ag, "source": "fd"})
            n += 1
        _mark(store, f"oddset_fd_at:{lg}")
        out[lg] = n
    return out


# --- Sofascore (xG) ----------------------------------------------------------------

def _sofa_get(path: str, timeout: float = 20.0):
    from curl_cffi import requests as cffi
    r = cffi.get(f"https://api.sofascore.com/api/v1{path}",
                 impersonate="chrome", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _sofa_season(store: Storage, lg: str) -> Optional[int]:
    """Innevarande säsongs id, cachat i meta (30 d)."""
    key = f"oddset_sofa_season:{lg}"
    cached = store.meta_get(key)
    if cached:
        try:
            sid, at = cached.split("|")
            if (_now() - dt.datetime.fromisoformat(at)).days < 30:
                return int(sid)
        except ValueError:
            pass
    try:
        seasons = _sofa_get(f"/unique-tournament/{SOFA_UT[lg]}/seasons")["seasons"]
        sid = seasons[0]["id"]
        store.meta_set(key, f"{sid}|{_now().isoformat()}")
        return sid
    except Exception:  # noqa: BLE001
        return None


def _ingest_event(store: Storage, lg: str, e: dict) -> bool:
    """Spara ett avslutat Sofascore-event (resultat + xG + hörnor). False om känt."""
    if e.get("status", {}).get("type") != "finished":
        return False
    eid = e["id"]
    if store.meta_get(f"oddset_sofa_seen:{eid}"):
        return False
    date = dt.datetime.fromtimestamp(
        e["startTimestamp"], dt.timezone.utc).strftime("%Y-%m-%d")
    row = {"league": lg, "date": date,
           "home": norm_team(e["homeTeam"]["name"]),
           "away": norm_team(e["awayTeam"]["name"]),
           "home_raw": e["homeTeam"]["name"],
           "away_raw": e["awayTeam"]["name"],
           "hg": e.get("homeScore", {}).get("current"),
           "ag": e.get("awayScore", {}).get("current"),
           "source": "sofa"}
    time.sleep(1.1)
    try:
        groups = _sofa_get(f"/event/{eid}/statistics") \
            .get("statistics", [{}])[0].get("groups", [])
        for g in groups:
            for s in g.get("statisticsItems", []):
                if s.get("name") == "Expected goals":
                    row["xg_h"] = float(s["home"])
                    row["xg_a"] = float(s["away"])
                elif s.get("name") == "Corner kicks":
                    row["cor_h"] = float(s["home"])
                    row["cor_a"] = float(s["away"])
    except Exception:  # noqa: BLE001 — äldre matcher kan sakna statistik
        pass
    store.oddset_save_result(row)
    store.meta_set(f"oddset_sofa_seen:{eid}", row["date"])
    return True


def refresh_xg(store: Storage, force: bool = False) -> dict:
    """Hämta xG/hörnor för färdigspelade matcher som saknas (innevarande säsong)."""
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

def refresh_elo(store: Storage, force: bool = False) -> Optional[int]:
    if not force and not _stale(store, "oddset_elo_at", ELO_TTL_H):
        return None
    try:
        r = httpx.get(f"http://api.clubelo.com/{_now().strftime('%Y-%m-%d')}", timeout=30)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    elo = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        if row.get("Country") in ("SWE", "NOR"):
            try:
                elo[norm_team(row["Club"])] = round(float(row["Elo"]))
            except (ValueError, KeyError):
                continue
    if elo:
        store.meta_set("oddset_elo", json.dumps(elo, ensure_ascii=False))
        _mark(store, "oddset_elo_at")
    return len(elo)


def get_elo(store: Storage) -> dict[str, int]:
    try:
        return json.loads(store.meta_get("oddset_elo") or "{}")
    except ValueError:
        return {}


def refresh_all(store: Storage, force: bool = False) -> dict:
    """Körs i varje insamlingspass — throttlarna gör det billigt."""
    return {"results": refresh_results(store, force),
            "xg": refresh_xg(store, force),
            "elo": refresh_elo(store, force)}


def merged_results(store: Storage, league: str) -> list[dict]:
    """Resultat med källorna ihopslagna: Sofascore-lagnamn kanoniseras till
    football-data-namnen (annars splittras lag som 'djurgardens'/'djurgarden'
    i fitten) och dubblettrader för samma match slås ihop (xG vinner)."""
    from .oddset import _team_sim
    rows = [dict(r) for r in store.oddset_results(league)]
    canon = sorted({r[side] for r in rows if r.get("source") == "fd"
                    for side in ("home", "away")})

    def to_canon(name: str) -> str:
        if name in canon:
            return name
        best, best_s = name, 0.7
        for c in canon:
            s = _team_sim(name, c)
            if s > best_s:
                best, best_s = c, s
        return best

    merged: dict[tuple, dict] = {}
    for r in rows:
        if r.get("source") != "fd":
            r["home"], r["away"] = to_canon(r["home"]), to_canon(r["away"])
        key = (r["date"], r["home"], r["away"])
        prev = merged.get(key)
        if not prev:
            merged[key] = r
            continue
        for k in ("xg_h", "xg_a", "cor_h", "cor_a", "hg", "ag"):
            if prev.get(k) is None and r.get(k) is not None:
                prev[k] = r[k]
    return sorted(merged.values(), key=lambda r: r["date"])
