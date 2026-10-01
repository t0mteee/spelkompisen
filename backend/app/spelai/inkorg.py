"""Inkorgen: agentens beslut och förslag in, Samans svar ut (designens 5.5, 8).

Agenten lägger JSON-filer i `~/spel-ai-data/utkorg/`. Schemaläggaren läser in
dem: en giltig fil flyttas till `utkorg/inlasta/`, en ogiltig till
`utkorg/avvisade/` med en `.orsak.txt` bredvid. Agenten kan läsa svaren ur
databasen men aldrig skriva dem.

Filformat:
    {"id": "<agentens eget id, för dedup>",
     "typ": "beslut" | "forslag_forbattring" | "forslag_spelrad",
     "kalla": "<roll eller 'Spelkompisen'>",
     "rubrik": "...", "varfor": "...",
     "alternativ": [{"text": "...", "rekommenderas": true, "kvot": 10}, ...],
     "sista_tid": "2026-10-02T18:00:00Z"}            # valfri

Svar: beslut besvaras med alternativets index ("0", "1", ...) eller
"kommentar"; förslag med "kor_nu", "nej" eller "kommentar". Ett svar utan
webbläsar-User-Agent sparas men märks `misstankt`, ger en `spelai_event` och
räknas aldrig som beslutets svar. Status härleds: `besvarad` när ett
effektivt svar finns, `utgangen` när sista tiden passerat utan svar, annars
`vantar`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Optional

from . import tillstand
from .tillstand import iso, utc

UTKORG_DEFAULT = Path.home() / "spel-ai-data" / "utkorg"
TYPER = ("beslut", "forslag_forbattring", "forslag_spelrad")
FORSLAG_VAL = ("kor_nu", "nej", "kommentar")
MAX_FILE_BYTES = 64 * 1024
MAX_ALTERNATIV = 8
ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,100}$")
LIMITS = {"kalla": 60, "rubrik": 200, "varfor": 4000}
BROWSER_MARKERS = ("Mozilla/",)


class Ogiltig(ValueError):
    pass


def _text(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Ogiltig(f"fältet '{key}' saknas eller är tomt")
    if len(value) > LIMITS[key]:
        raise Ogiltig(f"fältet '{key}' är längre än {LIMITS[key]} tecken")
    return value.strip()


def validera(data) -> dict:
    if not isinstance(data, dict):
        raise Ogiltig("filen är inte ett JSON-objekt")
    ext_id = data.get("id")
    if not isinstance(ext_id, str) or not ID_RE.match(ext_id):
        raise Ogiltig("fältet 'id' saknas eller har ogiltiga tecken "
                      "(A–Z, 0–9, . _ : -, högst 100)")
    typ = data.get("typ")
    if typ not in TYPER:
        raise Ogiltig(f"fältet 'typ' måste vara ett av {', '.join(TYPER)}")
    out = {"external_id": ext_id, "typ": typ, "kalla": _text(data, "kalla"),
           "rubrik": _text(data, "rubrik"), "varfor": _text(data, "varfor")}
    alternativ = data.get("alternativ", [])
    if not isinstance(alternativ, list) or len(alternativ) > MAX_ALTERNATIV:
        raise Ogiltig(f"'alternativ' måste vara en lista med högst {MAX_ALTERNATIV}")
    if typ == "beslut" and not alternativ:
        raise Ogiltig("ett beslut måste ha minst ett alternativ")
    clean = []
    for index, alt in enumerate(alternativ):
        if not isinstance(alt, dict) or not isinstance(alt.get("text"), str) \
                or not alt["text"].strip():
            raise Ogiltig(f"alternativ {index} saknar 'text'")
        rec = alt.get("rekommenderas", False)
        if not isinstance(rec, bool):
            raise Ogiltig(f"alternativ {index}: 'rekommenderas' måste vara true/false")
        item = {"text": alt["text"].strip()[:500], "rekommenderas": rec}
        if "kvot" in alt:
            kvot = alt["kvot"]
            if not isinstance(kvot, int) or isinstance(kvot, bool) or kvot < 0:
                raise Ogiltig(f"alternativ {index}: 'kvot' måste vara ett heltal ≥ 0")
            item["kvot"] = kvot
        clean.append(item)
    if sum(1 for alt in clean if alt["rekommenderas"]) > 1:
        raise Ogiltig("högst ett alternativ får rekommenderas")
    out["alternativ"] = clean
    sista = data.get("sista_tid")
    if sista is not None:
        if not isinstance(sista, str):
            raise Ogiltig("'sista_tid' måste vara en ISO-tid")
        try:
            parsed = dt.datetime.fromisoformat(sista.replace("Z", "+00:00"))
        except ValueError:
            raise Ogiltig("'sista_tid' är inte en ISO-tid") from None
        if parsed.tzinfo is None:
            raise Ogiltig("'sista_tid' måste ha tidszon (t.ex. Z)")
        out["sista_tid"] = iso(parsed)
    else:
        out["sista_tid"] = None
    return out


def _move(path: Path, target_dir: Path, now: dt.datetime) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target.exists():
        target = target_dir / f"{path.stem}.{now.strftime('%Y%m%dT%H%M%S')}{path.suffix}"
    shutil.move(str(path), str(target))
    return target


def las_in(conn, utkorg: Path = UTKORG_DEFAULT, *, now: dt.datetime) -> dict:
    """Läs in alla *.json i utkorgen (inte undermappar)."""
    report = {"inlasta": 0, "avvisade": 0, "dubbletter": 0}
    utkorg = Path(utkorg)
    if not utkorg.is_dir():
        return report
    for path in sorted(utkorg.glob("*.json")):
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_FILE_BYTES:
                raise Ogiltig(f"filen är större än {MAX_FILE_BYTES} byte")
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise Ogiltig(f"ogiltig JSON: {exc}") from None
            item = validera(data)
        except Ogiltig as exc:
            target = _move(path, utkorg / "avvisade", now)
            target.with_name(target.name + ".orsak.txt").write_text(
                f"{iso(now)} avvisad: {exc}\n", encoding="utf-8")
            tillstand.logga(conn, "inkorg_avvisad", path.name, {"orsak": str(exc)},
                            now=now)
            report["avvisade"] += 1
            continue
        digest = hashlib.sha256(raw).hexdigest()[:16]
        cur = conn.execute(
            "INSERT OR IGNORE INTO spelai_inbox (external_id, typ, kalla, rubrik, "
            "varfor, alternativ_json, sista_tid, file_name, payload_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item["external_id"], item["typ"], item["kalla"], item["rubrik"],
             item["varfor"], json.dumps(item["alternativ"], ensure_ascii=False),
             item["sista_tid"], path.name, digest, iso(now)))
        conn.commit()
        _move(path, utkorg / "inlasta", now)
        if cur.rowcount == 1:
            report["inlasta"] += 1
            tillstand.logga(conn, "inkorg_ny", item["external_id"],
                            {"typ": item["typ"], "kalla": item["kalla"]}, now=now)
        else:
            report["dubbletter"] += 1
            tillstand.logga(conn, "inkorg_dubblett", item["external_id"],
                            {"fil": path.name}, now=now)
    return report


def _effektivt(conn, inbox_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, val, kommentar, answered_at FROM spelai_inbox_answer "
        "WHERE inbox_id=? AND misstankt=0 AND val!='kommentar' ORDER BY id LIMIT 1",
        (inbox_id,)).fetchone()
    if row is None:
        return None
    return {"id": row[0], "val": row[1], "kommentar": row[2], "tid": row[3]}


def status(conn, item: dict, now: dt.datetime) -> str:
    if _effektivt(conn, item["id"]):
        return "besvarad"
    sista = utc(item.get("sista_tid"))
    if sista is not None and now > sista:
        return "utgangen"
    return "vantar"


def lista(conn, *, now: dt.datetime, limit: int = 200) -> list[dict]:
    out = []
    for row in conn.execute(
            "SELECT id, external_id, typ, kalla, rubrik, varfor, alternativ_json, "
            "sista_tid, created_at FROM spelai_inbox ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall():
        item = {"id": row[0], "external_id": row[1], "typ": row[2], "kalla": row[3],
                "rubrik": row[4], "varfor": row[5],
                "alternativ": json.loads(row[6]), "sista_tid": row[7],
                "skapad": row[8]}
        item["svar"] = _effektivt(conn, item["id"])
        item["status"] = status(conn, item, now)
        item["kommentarer"] = [
            {"kommentar": k, "tid": t, "misstankt": bool(m)}
            for k, t, m in conn.execute(
                "SELECT kommentar, answered_at, misstankt FROM spelai_inbox_answer "
                "WHERE inbox_id=? AND kommentar IS NOT NULL ORDER BY id", (item["id"],))]
        out.append(item)
    return out


# Svar tas bara emot från Spelkompisens EGEN beslutssida (betrodd kod):
# byggd frontend 5175 och dev 5181. Agentens app (5176) är agentens kod och
# får aldrig kunna posta ett svar i Samans namn, inte ens via Samans webbläsare
# — en webbläsare sätter alltid Origin på en POST (designen 5.5).
SVAR_PORTAR = frozenset({5175, 5181})


def tillaten_origin(origin: Optional[str]) -> bool:
    from urllib.parse import urlsplit
    if not origin:
        return False
    try:
        parts = urlsplit(origin)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and port in SVAR_PORTAR


def ar_webblasare(user_agent: Optional[str]) -> bool:
    return bool(user_agent) and any(m in user_agent for m in BROWSER_MARKERS)


def svara(conn, inbox_id: int, val, kommentar: Optional[str], *,
          user_agent: Optional[str], forwarded_for: Optional[str],
          client_host: Optional[str], now: dt.datetime) -> dict:
    row = conn.execute("SELECT id, typ, alternativ_json FROM spelai_inbox WHERE id=?",
                       (inbox_id,)).fetchone()
    if row is None:
        raise LookupError(f"inkorgspost {inbox_id} finns inte")
    typ, alternativ = row[1], json.loads(row[2])
    val = str(val).strip() if val is not None else ""
    if typ == "beslut":
        allowed = {str(i) for i in range(len(alternativ))} | {"kommentar"}
    else:
        allowed = set(FORSLAG_VAL)
    if val not in allowed:
        raise ValueError(f"ogiltigt val {val!r} (tillåtna: {', '.join(sorted(allowed))})")
    if kommentar is not None and not isinstance(kommentar, str):
        raise ValueError("kommentaren måste vara text")
    kommentar = (kommentar or "").strip()[:2000] or None
    if val == "kommentar" and not kommentar:
        raise ValueError("val 'kommentar' kräver en kommentar")
    misstankt = not ar_webblasare(user_agent)
    cur = conn.execute(
        "INSERT INTO spelai_inbox_answer (inbox_id, val, kommentar, answered_at, "
        "user_agent, forwarded_for, client_host, misstankt) VALUES (?,?,?,?,?,?,?,?)",
        (inbox_id, val, kommentar, iso(now), (user_agent or "")[:400] or None,
         (forwarded_for or "")[:200] or None, (client_host or "")[:100] or None,
         int(misstankt)))
    conn.commit()
    if misstankt:
        tillstand.logga(conn, "svar_misstankt", str(inbox_id),
                        {"user_agent": user_agent, "forwarded_for": forwarded_for,
                         "client_host": client_host}, now=now)
    else:
        tillstand.logga(conn, "svar", str(inbox_id), {"val": val}, now=now)
    return {"id": cur.lastrowid, "inbox_id": inbox_id, "val": val,
            "misstankt": misstankt, "raknas": not misstankt and val != "kommentar"}
