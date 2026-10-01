"""Läsvägar och små skrivvägar för `/api/spelai/*` (designens 5.7).

GET-vägarna är rena läsningar och svarar tomt när tabellerna saknas.
Skrivvägarna (svar, spelat, paus) kräver tabellerna och skriver bara nya rader.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Optional

from . import inkorg, nivaer, schema, tillstand
from .tillstand import iso, utc


def _ready(conn) -> bool:
    return schema.tables_exist(conn)


def _rad(row: dict, result: Optional[dict]) -> dict:
    out = {"id": row["id"], "status": row["status"], "orsak": row["reason"],
           "version": row["strategy_version"], "config_key": row["config_key"],
           "format": row["format"], "rader": row["n_rows"], "kostnad_kr": row["cost_kr"],
           "hash": row["rows_hash"], "motivering": row["motivation"],
           "fryst": row["frozen_at"], "indata_id": row["input_id"],
           "indata_observerad": row["input_observed_at"],
           "underlag": {"svs": row["obs_svs_at"], "sharp": row["obs_sharp_at"],
                        "omsattning": row["obs_turnover_at"]}}
    if row["format"] == "msystem" and row["msystem_json"]:
        out["tecken"] = json.loads(row["msystem_json"])
    if result:
        out["facit"] = {"ratt_max": result["correct_max"],
                        "fordelning": json.loads(result["correct_dist"])
                        if result["correct_dist"] else None,
                        "utdelning_kr": result["payout_kr"],
                        "publicerad_kr": result["published_payout_kr"],
                        "komplett": (bool(result["payout_complete"])
                                     if result["payout_complete"] is not None else None),
                        "roi": result["roi"], "not": result["note"],
                        "rattad": result["settled_at"]}
    return out


def pool(conn, *, now: dt.datetime, product: Optional[str] = None,
         limit: int = 30) -> dict:
    if not _ready(conn):
        return {"tabeller": False, "omgangar": [], "per_niva": []}
    conn.row_factory = sqlite3.Row
    params: list = []
    where = ""
    if product:
        where = "WHERE product=?"
        params.append(product)
    draws = conn.execute(
        f"SELECT product, draw_number, MAX(reg_close_time) AS close FROM "
        f"spelai_pool_proposal {where} GROUP BY product, draw_number",
        params).fetchall()
    draws = sorted(draws, key=lambda r: utc(r["close"]) or now, reverse=True)[:limit]
    omgangar = []
    for d in draws:
        rows = conn.execute(
            "SELECT * FROM spelai_pool_proposal WHERE product=? AND draw_number=? "
            "ORDER BY level_kr, horizon, role", (d["product"], d["draw_number"])).fetchall()
        results = {r["proposal_id"]: dict(r) for r in conn.execute(
            "SELECT r.* FROM spelai_pool_result r JOIN spelai_pool_proposal p "
            "ON p.id=r.proposal_id WHERE p.product=? AND p.draw_number=?",
            (d["product"], d["draw_number"]))}
        nivamap: dict = {}
        for row in rows:
            entry = nivamap.setdefault(row["level_kr"], {}).setdefault(row["horizon"], {})
            entry[row["role"]] = _rad(dict(row), results.get(row["id"]))
        omgangar.append({
            "produkt": d["product"], "omgang": d["draw_number"],
            "spelstopp": d["close"],
            "nivaer": [{"niva_kr": lv, "horisonter": nivamap[lv]}
                       for lv in sorted(nivamap)]})
    return {"tabeller": True, "omgangar": omgangar, "per_niva": per_niva(conn)}



def _rader(row: dict) -> list[str]:
    if row.get("format") == "msystem" and row.get("msystem_json"):
        return nivaer.expandera(json.loads(row["msystem_json"]))
    return [line for line in (row.get("rows_text") or "").splitlines() if line]


def _andelar(row: dict, rows: list[str], n_matches: int) -> list[dict]:
    """Andel av raderna per tecken och match. M-systemet räknas ur tecknen
    (varje valt tecken bär 1/k av raderna) i stället för att räkna 39 366 rader."""
    if row.get("format") == "msystem" and row.get("msystem_json"):
        tecken = json.loads(row["msystem_json"])
        return [{s: (1.0 / len(t) if s in t else 0.0) for s in nivaer.SIGNS}
                for t in tecken]
    counts = [{s: 0 for s in nivaer.SIGNS} for _ in range(n_matches)]
    for text in rows:
        for i, sign in enumerate(text[:n_matches]):
            if sign in counts[i]:
                counts[i][sign] += 1
    total = len(rows) or 1
    return [{s: c[s] / total for s in nivaer.SIGNS} for c in counts]


def _tackta(andelar: list[dict]) -> list[str]:
    return ["".join(s for s in nivaer.SIGNS if a.get(s)) for a in andelar]


def _matcher(conn, input_id: Optional[int], events: list[int]) -> list[dict]:
    """Matchnamn ur indatapaketets draw (samma läsning som förslaget byggdes på)."""
    names: dict[int, str] = {}
    if input_id:
        found = conn.execute("SELECT payload_json FROM spelai_input WHERE id=?",
                             (input_id,)).fetchone()
        if found:
            draw = (json.loads(found[0]) or {}).get("draw") or {}
            for match in draw.get("matches") or []:
                home, away = match.get("home"), match.get("away")
                label = (f"{home} – {away}" if home and away
                         else match.get("description") or "")
                names[int(match.get("event_number") or 0)] = label
    return [{"event": e, "match": names.get(e, f"match {e}")} for e in events]


def _jamfor(egen: list[str], annan: list[str]) -> dict:
    andrade = [i + 1 for i, (a, b) in enumerate(zip(egen, annan)) if a != b]
    return {"andrade_matcher": andrade, "antal": len(andrade),
            "lika_matcher": len(egen) - len(andrade)}


def forslag(conn, proposal_id: int, *, med_rader: bool = False) -> Optional[dict]:
    """Ett fryst förslag med andel per tecken och match, matchnamn ur paketet,
    och vilka matcher som skiljer mot motrollen (agent/standard) och mot
    förhandsversionen. `med_rader` lämnar ut raderna (för export av radfil)."""
    if not _ready(conn):
        return None
    conn.row_factory = sqlite3.Row
    found = conn.execute("SELECT * FROM spelai_pool_proposal WHERE id=?",
                         (proposal_id,)).fetchone()
    if found is None:
        return None
    row = dict(found)
    result = conn.execute("SELECT * FROM spelai_pool_result WHERE proposal_id=?",
                          (proposal_id,)).fetchone()
    out = _rad(row, dict(result) if result else None)
    out.update({"produkt": row["product"], "omgang": row["draw_number"],
                "niva_kr": row["level_kr"], "horisont": row["horizon"],
                "roll": row["role"], "spelstopp": row["reg_close_time"]})
    events = [int(e) for e in (row.get("events_order") or "").split(",") if e.strip()]
    rows = _rader(row) if row["status"] == "fryst" else []
    out["matcher"] = _matcher(conn, row.get("input_id"), events)
    out["andelar"] = _andelar(row, rows, len(events)) if rows else []
    egen = _tackta(out["andelar"])
    jamforelse: dict = {}
    for namn, roll, horisont in (
            ("mot_motrollen", "standard" if row["role"] == "agent" else "agent",
             row["horizon"]),
            ("mot_forhandsversionen", row["role"], "6h")):
        if namn == "mot_forhandsversionen" and row["horizon"] == "6h":
            continue
        other = conn.execute(
            "SELECT * FROM spelai_pool_proposal WHERE product=? AND draw_number=? "
            "AND level_kr=? AND role=? AND horizon=?",
            (row["product"], row["draw_number"], row["level_kr"], roll,
             horisont)).fetchone()
        if other is None or other["status"] != "fryst" or not egen:
            continue
        other = dict(other)
        other_rows = _rader(other)
        jamforelse[namn] = {"id": other["id"], **_jamfor(
            egen, _tackta(_andelar(other, other_rows, len(events))))}
    out["jamforelse"] = jamforelse
    if med_rader and row["format"] == "rows":
        out["rader_lista"] = rows
    return out

def per_niva(conn) -> list[dict]:
    """Facit per nivå för officiella (30m) förslag: parade omgångar där BÅDE
    agent och standard frystes och rättades komplett. Bara siffror — ingen
    "förbättring" före gränserna i designens 5.6 (40 parade omgångar + BH-FDR)."""
    rows = conn.execute(
        "SELECT p.product, p.draw_number, p.level_kr, p.role, r.payout_kr, r.cost_kr, "
        "r.payout_complete FROM spelai_pool_proposal p JOIN spelai_pool_result r "
        "ON r.proposal_id=p.id WHERE p.horizon='30m' AND p.status='fryst'").fetchall()
    pairs: dict = {}
    for product, draw_number, level, role, payout, cost, complete in rows:
        if not complete or payout is None or not cost:
            continue
        pairs.setdefault((level, product, draw_number), {})[role] = (payout, cost)
    out: dict = {}
    for (level, _product, _draw), roles in pairs.items():
        if set(roles) != {"agent", "standard"}:
            continue
        agg = out.setdefault(level, {"niva_kr": level, "parade_omgangar": 0,
                                     "agent_utdelning": 0.0, "standard_utdelning": 0.0,
                                     "insats": 0.0})
        agg["parade_omgangar"] += 1
        agg["agent_utdelning"] += roles["agent"][0]
        agg["standard_utdelning"] += roles["standard"][0]
        agg["insats"] += roles["standard"][1]
    for agg in out.values():
        agg["gransen_nadd"] = agg["parade_omgangar"] >= 40
        agg["not"] = ("under 40 parade omgångar — siffror, aldrig en förbättring"
                      if not agg["gransen_nadd"] else
                      "40 parade omgångar — BH-FDR 10 % över nivåerna avgör")
    return [out[k] for k in sorted(out)]


def inbox(conn, *, now: dt.datetime) -> dict:
    if not _ready(conn):
        return {"tabeller": False, "poster": [], "vantar": 0}
    poster = inkorg.lista(conn, now=now)
    return {"tabeller": True, "poster": poster,
            "vantar": sum(1 for p in poster if p["status"] == "vantar"
                          and p["typ"] == "beslut")}


def korningar(conn, *, now: dt.datetime, limit: int = 100) -> dict:
    if not _ready(conn):
        return {"tabeller": False, "korningar": [], "kvot": None, "pausad": False}
    rows = conn.execute(
        "SELECT id, role, task, started_at, ended_at, status, model, usage_json, "
        "cost_usd, note FROM spelai_run ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    keys = ("id", "roll", "uppgift", "start", "slut", "status", "modell", "anvandning",
            "kostnad_usd", "not")
    korn = []
    for row in rows:
        item = dict(zip(keys, tuple(row)))
        if item["anvandning"]:
            try:
                item["anvandning"] = json.loads(item["anvandning"])
            except json.JSONDecodeError:
                pass
        korn.append(item)
    return {"tabeller": True, "korningar": korn,
            "kvot": tillstand.kvot_idag(conn, now), "pausad": tillstand.pausad(conn)}


def spelat(conn, payload: dict, *, user_agent: Optional[str],
           forwarded_for: Optional[str], client_host: Optional[str],
           now: dt.datetime) -> dict:
    """"Jag spelade detta" — bokför bara att Saman SJÄLV lämnat in. Lägger inget spel."""
    if not isinstance(payload, dict):
        raise ValueError("förväntade ett JSON-objekt")
    kind = payload.get("typ", "pool")
    if kind not in ("pool", "live"):
        raise ValueError("typ måste vara 'pool' eller 'live'")
    note = payload.get("not")
    if note is not None and not isinstance(note, str):
        raise ValueError("'not' måste vara text")
    proposal = None
    if kind == "pool":
        try:
            proposal_id = int(payload.get("forslag_id"))
        except (TypeError, ValueError):
            raise ValueError("'forslag_id' måste vara ett heltal") from None
        proposal = conn.execute(
            "SELECT id, product, draw_number, level_kr, status FROM spelai_pool_proposal "
            "WHERE id=?", (proposal_id,)).fetchone()
        if proposal is None:
            raise LookupError(f"förslag {proposal_id} finns inte")
        if proposal[4] != "fryst":
            raise ValueError("bara ett fryst förslag kan markeras som spelat")
        values = (kind, proposal[0], None, proposal[1], proposal[2], proposal[3])
    else:
        try:
            bet_id = int(payload.get("spel_id"))
        except (TypeError, ValueError):
            raise ValueError("'spel_id' måste vara ett heltal") from None
        values = (kind, None, bet_id, None, None, None)
    cur = conn.execute(
        "INSERT INTO spelai_played (kind, proposal_id, live_bet_id, product, "
        "draw_number, level_kr, note, played_at, user_agent, forwarded_for, "
        "client_host) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (*values, (note or "")[:500] or None, iso(now), (user_agent or "")[:400] or None,
         (forwarded_for or "")[:200] or None, (client_host or "")[:100] or None))
    conn.commit()
    tillstand.logga(conn, "spelat", str(cur.lastrowid), {"typ": kind}, now=now)
    return {"id": cur.lastrowid, "typ": kind}


def paus(conn, payload: dict, *, user_agent: Optional[str], now: dt.datetime) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("paus"), bool):
        raise ValueError("förväntade {\"paus\": true|false}")
    browser = inkorg.ar_webblasare(user_agent)
    source = "webb" if browser else "api-utan-webblasare"
    out = tillstand.satt_paus(conn, payload["paus"], source=source, now=now)
    if not browser:
        # Pausen gäller ändå (att stanna är alltid säkert), men en ändring som
        # inte kommer från en webbläsare larmar precis som ett misstänkt svar.
        tillstand.logga(conn, "paus_misstankt", None,
                        {"paus": payload["paus"], "user_agent": user_agent}, now=now)
    return out


__all__ = ["pool", "inbox", "korningar", "spelat", "paus", "per_niva", "nivaer"]
