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
           "eliteserien": "https://www.football-data.co.uk/new/NOR.csv",
           "mls": "https://www.football-data.co.uk/new/USA.csv"}
FD_MIN_SEASON = 2024          # fit-fönster: ~2,5 säsonger räcker med tidsviktning
SOFA_UT = {"allsvenskan": 40, "eliteserien": 20, "superettan": 46,
           "obosligaen": 22, "mls": 242}
# OBS: sök ALDRIG fram Sofascore-id:n utan att verifiera sporten — 1420 ("1.
# Divisjon") visade sig vara HANDBOLL och 28937 volleyboll; fotbollens norska
# andraliga är ut 22 ("Norwegian 1st Division", verifierad med lagnamn + xG).
# Superettan/OBOS saknar football-data — Sofascore är enda resultatkällan.
MODEL_LEAGUES = set(FD_URLS) | {"superettan", "obosligaen"}
SOFA_MAX_PAGES = 4            # events/last/{page} per körning (backfill tar några pass)

FD_TTL_H, XG_TTL_H, ELO_TTL_H, ABS_TTL_H = 12, 6, 24, 2

# Databehandlingens version — ingår i signal_version-fingeravtrycken (gransknings-
# punkt 5): bumpa MANUELLT när semantiken i datat ändras utan att en parameter gör
# det. 1 = ursprunglig; 2 = normaltime + identitetsmerge (alias/±1 dygn), 2026-07-13.
DATA_VERSION = 2
# missingPlayers-orsakskoder (Sofascore): observerade typer
_ABS_REASON = {1: "skada", 2: "tveksam", 3: "avstängd", 11: "annat"}


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
        with store.bulk():   # WP0: EN transaktion i stället för ~1 700 commits
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
          if m["league"] in SOFA_UT]
    out = {"checked": 0, "found": 0}
    ev_index: dict[str, list] = {}
    for lg in {m["league"] for m in ms}:
        sid = _sofa_season(store, lg)
        if not sid:
            continue
        try:
            evs = _sofa_get(f"/unique-tournament/{SOFA_UT[lg]}/season/{sid}"
                            f"/events/next/0").get("events") or []
        except Exception:  # noqa: BLE001
            continue
        ev_index[lg] = [(e["id"], norm_team(e["homeTeam"]["name"]),
                         norm_team(e["awayTeam"]["name"])) for e in evs]
    for m in ms:
        cands = ev_index.get(m["league"]) or []
        hn, an = norm_team(m["home"]), norm_team(m["away"])
        eid = next((i for i, h, a in cands
                    if _team_sim(hn, h) >= 0.75 and _team_sim(an, a) >= 0.75), None)
        if not eid:
            continue
        out["checked"] += 1
        time.sleep(1.0)
        try:
            lu = _sofa_get(f"/event/{eid}/lineups")
        except Exception:  # noqa: BLE001 — 404 tills lineups/frånvaro publicerats
            continue
        rec = {"at": frm, "confirmed": bool(lu.get("confirmed"))}
        ut, sid = SOFA_UT[m["league"]], _sofa_season(store, m["league"])
        for side in ("home", "away"):
            rec[side] = []
            for p in (lu.get(side) or {}).get("missingPlayers") or []:
                pl = p.get("player") or {}
                entry = {"name": pl.get("name"),
                         "reason": _ABS_REASON.get(p.get("reason"),
                                                   f"kod {p.get('reason')}")}
                # spelarens säsongsstatus: få matcher = marginell frånvaro som
                # inte ska väga tungt (Samans poäng — en reserv borta är inte
                # samma sak som en ordinarie)
                if pl.get("id"):
                    time.sleep(0.8)
                    try:
                        st = _sofa_get(f"/player/{pl['id']}/unique-tournament/{ut}"
                                       f"/season/{sid}/statistics/overall") \
                            .get("statistics") or {}
                        entry["apps"] = st.get("appearances")
                        if st.get("rating"):
                            entry["rating"] = round(st["rating"], 2)
                    except Exception:  # noqa: BLE001 — ingen säsongsstatistik = okänd
                        pass
                rec[side].append(entry)
        store.meta_set(f"oddset_abs:{m['id']}", json.dumps(rec, ensure_ascii=False))
        out["found"] += 1
    _mark(store, "oddset_abs_at")
    return out


def get_absences(store: Storage, match_ids: list[str]) -> dict[str, dict]:
    out = {}
    for mid in match_ids:
        raw = store.meta_get(f"oddset_abs:{mid}")
        if raw:
            try:
                out[mid] = json.loads(raw)
            except ValueError:
                pass
    return out


def refresh_all(store: Storage, force: bool = False) -> dict:
    """Körs i varje insamlingspass — throttlarna gör det billigt."""
    return {"results": refresh_results(store, force),
            "xg": refresh_xg(store, force),
            "elo": refresh_elo(store, force),
            "absences": refresh_absences(store, force)}


# Manuella lagnamns-alias (identitetslager, granskning 2026-07-13): källnamn →
# football-data-kanoniskt namn, per liga. Fuzzy-tröskeln 0.7 missar dessa
# (la galaxy↔los angeles galaxy = 0.67 → laget splittrades i två identiteter i
# fitten). Runtime-tillägg utan deploy: meta-nyckeln oddset_alias:{liga} (JSON).
TEAM_ALIAS = {"mls": {"la galaxy": "los angeles galaxy"}}


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
    för samma match slås ihop (xG vinner). Matchnyckeln tål ±1 dygns datumskillnad
    mellan källorna (MLS: Sofascore = UTC-datum, football-data = lokalt/brittiskt
    → 304 dubbletter i fitten före fixen) — kräver samma lagpar, olika källor och
    samma mål. audit (dict) fylls med det som INTE avgjordes tyst:
    'unmatched' = namn som inte kunde kanoniseras (med bästa förslag + likhet),
    'date_dups' = kvarvarande par samma lag/olika källa inom ±1 dygn."""
    from .oddset import _team_sim
    rows = [dict(r) for r in store.oddset_results(league)]
    alias = _alias_map(store, league)
    canon = sorted({r[side] for r in rows if r.get("source") == "fd"
                    for side in ("home", "away")})

    def to_canon(name: str) -> str:
        if not canon or name in canon:
            return name          # en-källe-liga (Superettan/OBOS) kanoniserar inte
        if name in alias:
            return alias[name]   # manuellt verifierad koppling vinner
        best, best_s = name, 0.7
        for c in canon:
            s = _team_sim(name, c)
            if s > best_s:
                best, best_s = c, s
        if best is name and audit is not None:
            # föreslå i stället för att tyst lämna osammanslaget
            cand = max(((c, _team_sim(name, c)) for c in canon),
                       key=lambda t: t[1], default=(None, 0.0))
            if cand[0] and cand[1] >= 0.5:
                audit.setdefault("unmatched", []).append(
                    {"name": name, "suggestion": cand[0], "sim": round(cand[1], 2)})
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
                for k in ("xg_h", "xg_a", "cor_h", "cor_a", "hg", "ag"):
                    if base.get(k) is None and fill.get(k) is not None:
                        base[k] = fill[k]
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
