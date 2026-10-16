"""Notiser för facitsidan (designens avsnitt 9) via ntfy.

Ämnet läses ur `SPELAI_NTFY_TOPIC` i gitignorerade `backend/.env`. Saknas det
skickas ingenting — händelsen bokförs ändå i `spelai_event`. Detta återaktiverar
INTE Spelkompisens pausade odds-/signalnotiser (`NTFY_TOPIC`).

* En notis per spel för det officiella förslaget (30 min), samlad för alla
  nivåer. Färre poolnotiser (beslut koordinatorn-2026-10-16-notiser-pool,
  val 0, `aviseras`): 6 h-versionen aviseras inte, och Topptipset-familjen
  bara när spelstoppet ligger 12:00–22:00 svensk tid (inklusive). Missade
  eller ogiltiga förslag aviseras alltid. Frysning, facit och mätning orörda.
  Regeln gäller i kandidaterna, alltså både ntfy och chattbudet.
* En notis per nytt beslut och per missat förslag.
* Tysta timmar 23–07 svensk tid — utom beslut med sista tid. En notis som
  hamnar i tysta timmar skjuts upp (kandidaterna härleds ur tabellerna), den
  försvinner inte; ett förslag vars spelstopp passerat skickas aldrig.
* Rollkörningar (fas F): en notis per avslutad körning — `roll_klar` med
  agentens SAMMANFATTNING-rad (kapad, radliknande tecken borttagna),
  `roll_fel` (fel/timeout/avbruten) utan felutskrift — och `kvot_slut` en
  gång per dygn. Samma tysta timmar och dedup.
* Aldrig rader, insatser eller loggar — bara vad som hänt och en länk.
* Länken (beslut koordinatorn-2026-10-16-notislank, val 0): `SPELAI_NOTIS_LANK`
  är Spelkompisens BASADRESS (byggd frontend 5175, Tailscale-adressen så att
  den fungerar hemma och borta). `lank_for` bygger direktlänken: beslut och
  genomförda beslut öppnar beslutssidan på posten (`#/beslut/<id>`), allt
  annat agentens app på samma värd, port 5176 (som `agentAppUrl` i frontenden).
* Dedup per händelse-id: `spelai_event.dedup_key = notis:<id>`.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Callable, Optional
from urllib.parse import urlsplit

from ..svenskaspel import PRODUCTS, family_of
from . import tillstand
from .tillstand import LOCAL_TZ, iso, utc

TOPIC_ENV = "SPELAI_NTFY_TOPIC"
LINK_ENV = "SPELAI_NOTIS_LANK"
AGENT_APP_PORT = 5176
BESLUT_KINDS = ("beslut", "genomforande")
QUIET_FROM, QUIET_TO = 23, 7
LOOKBACK_H = 12
HORISONT_TEXT = {"6h": "förhandsversion 6 h", "30m": "officiellt förslag 30 min"}
ROLL_TEXT = {"motivering": "motivering", "larm": "larmkörning",
             "morgonrunda": "morgonrunda", "forskningspass": "forskningspass",
             "veckogenomgang": "veckogenomgång"}
SAMMANFATTNING_MAX = 180
TYSTA_HORISONTER = ("6h",)          # poolförslag som bara syns i appen
TOPPTIPS_FONSTER = (dt.time(12, 0), dt.time(22, 0))   # spelstopp, svensk tid, inklusive
_RAD = re.compile(r"\b[1X2]{8,}\b")

Sender = Callable[[str, str, str, Optional[str]], bool]


def topic() -> Optional[str]:
    from .. import config  # noqa: F401 — laddar backend/.env om den finns
    return os.environ.get(TOPIC_ENV) or None


def tysta_timmar(now: dt.datetime) -> bool:
    hour = now.astimezone(LOCAL_TZ).hour
    return hour >= QUIET_FROM or hour < QUIET_TO


def ntfy_sender(topic_name: str, title: str, message: str,
                link: Optional[str]) -> bool:
    """ntfy:s JSON-publicering — UTF-8 i titeln utan headerkodning."""
    import httpx
    body = {"topic": topic_name, "title": title, "message": message,
            "tags": ["robot"]}
    if link:
        body["click"] = link
    try:
        response = httpx.post("https://ntfy.sh/", json=body, timeout=10)
        return response.status_code < 400
    except Exception:  # noqa: BLE001 — notiser får aldrig fälla tick
        return False


def lank_for(base: Optional[str], item: dict) -> Optional[str]:
    """Notisens direktlänk ur Spelkompisens basadress; None utan giltig bas."""
    if not base:
        return None
    try:
        parts = urlsplit(base.strip())
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    if item.get("kind") in BESLUT_KINDS:
        inbox_id = item.get("inbox_id")
        vy = f"#/beslut/{inbox_id}" if inbox_id is not None else "#/beslut"
        return f"{parts.scheme}://{parts.netloc}/{vy}"
    return f"{parts.scheme}://{host}:{AGENT_APP_PORT}/"


def _namn(product: str) -> str:
    return PRODUCTS.get(product, {}).get("name", product)


def aviseras(product: str, horizon: str, close: Optional[dt.datetime]) -> bool:
    """Får ett felfritt poolförslag aviseras? Missade/ogiltiga frågar aldrig här."""
    if horizon in TYSTA_HORISONTER:
        return False
    if family_of(product) == "topptipset":
        if close is None:
            return False                 # okänt spelstopp ligger inte i fönstret
        lokal = close.astimezone(LOCAL_TZ).time().replace(second=0, microsecond=0)
        return TOPPTIPS_FONSTER[0] <= lokal <= TOPPTIPS_FONSTER[1]
    return True


def kandidater(conn, *, now: dt.datetime) -> list[dict]:
    """Notiser som borde finnas, härledda ur tabellerna (dedup sker i skicka)."""
    since = now - dt.timedelta(hours=LOOKBACK_H)
    out: list[dict] = []
    groups: dict[tuple, dict] = {}
    for (product, draw_number, horizon, role, status, frozen_at,
         close_raw) in conn.execute(
            "SELECT product, draw_number, horizon, role, status, frozen_at, "
            "reg_close_time FROM spelai_pool_proposal ORDER BY id DESC LIMIT 2000"):
        frozen = utc(frozen_at)
        if frozen is None or frozen < since:
            continue
        g = groups.setdefault((product, draw_number, horizon), {
            "close": utc(close_raw), "statuses": {"agent": [], "standard": []}})
        g["statuses"][role].append(status)
    for (product, draw_number, horizon), g in groups.items():
        close = g["close"]
        stopp = close.astimezone(LOCAL_TZ).strftime("%H:%M") if close else "?"
        statuses = g["statuses"]
        alla = statuses["agent"] + statuses["standard"]
        namn = f"{_namn(product)} {draw_number}"
        if alla and all(s == "missat" for s in alla):
            out.append({"key": f"missat:{product}:{draw_number}:{horizon}",
                        "kind": "missat", "exempt": False, "close": close,
                        "title": "Poolförslag missat",
                        "message": f"{namn}: {HORISONT_TEXT[horizon]} frystes inte "
                                   f"i tid. Spelstopp {stopp}."})
            continue
        if all(s == "pausad" for s in alla):
            continue
        nivaer = len(statuses["standard"])
        ogiltiga = sum(1 for s in statuses["agent"] if s != "fryst")
        if not ogiltiga and not aviseras(product, horizon, close):
            continue
        extra = (f" Agentens förslag saknas eller är ogiltigt på {ogiltiga} "
                 f"nivå{'er' if ogiltiga != 1 else ''} — standarden visas."
                 if ogiltiga else "")
        out.append({"key": f"pool:{product}:{draw_number}:{horizon}",
                    "kind": "pool", "exempt": False, "close": close,
                    "title": "Poolförslag klart",
                    "message": f"{namn}: {HORISONT_TEXT[horizon]} fryst för "
                               f"{nivaer} nivå{'er' if nivaer != 1 else ''}. "
                               f"Spelstopp {stopp}.{extra}"})
    for inbox_id, rubrik, sista, created in conn.execute(
            "SELECT id, rubrik, sista_tid, created_at FROM spelai_inbox "
            "WHERE typ='beslut' ORDER BY id DESC LIMIT 200"):
        created_at = utc(created)
        if created_at is None or created_at < since:
            continue
        sista_at = utc(sista)
        if sista_at is not None and sista_at < now:
            continue
        msg = "Ett nytt beslut väntar på ditt svar"
        if sista_at is not None:
            msg += f" senast {sista_at.astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')}"
        out.append({"key": f"beslut:{inbox_id}", "kind": "beslut",
                    "inbox_id": inbox_id,
                    "exempt": sista_at is not None, "close": None,
                    "title": "Nytt beslut", "message": f"{msg}: {rubrik[:120]}"})
    out.extend(_roll_kandidater(conn, since=since))
    out.extend(_genomforande_kandidater(conn, since=since))
    return out


GENOMFORANDE_TITEL = {"genomfort": "Beslut genomfört", "ingen_andring": "Beslut: ingen ändring",
                      "aterstallt": "Beslut återställt", "misslyckades": "Beslut misslyckades"}


def _genomforande_kandidater(conn, *, since: dt.datetime) -> list[dict]:
    """Automatiskt genomförda beslut (app/spelai/genomforande.py)."""
    out: list[dict] = []
    for at, detail_json, dedup_key in conn.execute(
            "SELECT at, detail_json, dedup_key FROM spelai_event "
            "WHERE kind='genomforande_klar' ORDER BY id DESC LIMIT 100"):
        at_t = utc(at)
        if at_t is None or at_t < since:
            continue
        try:
            detail = json.loads(detail_json or "{}")
        except ValueError:
            detail = {}
        status = str(detail.get("status") or "")
        if detail.get("omforsok"):
            continue                 # prövas igen; bara slutresultatet rapporteras
        titel = GENOMFORANDE_TITEL.get(status, "Beslutet kunde inte genomföras")
        rubrik = str(detail.get("rubrik") or detail.get("id") or "")[:120]
        text = " ".join(str(detail.get("sammanfattning") or detail.get("orsak") or "").split())
        commit = str(detail.get("commit") or "")[:7]
        message = f"{rubrik}: {text[:SAMMANFATTNING_MAX]}" if text else rubrik
        if commit:
            message += f" (commit {commit})"
        out.append({"key": "genomforande:" + dedup_key.split(":", 1)[1],
                    "kind": "genomforande", "inbox_id": detail.get("inbox_id"),
                    "exempt": False, "close": None,
                    "title": titel, "message": message})
    return out


def _roll_kandidater(conn, *, since: dt.datetime) -> list[dict]:
    """Rollkörningarnas notiser ur journalen (app/spelai/roller.py)."""
    out: list[dict] = []
    for at, kind, ref, detail_json, dedup_key in conn.execute(
            "SELECT at, kind, ref, detail_json, dedup_key FROM spelai_event "
            "WHERE kind IN ('roll_klar', 'roll_fel', 'kvot_slut') "
            "ORDER BY id DESC LIMIT 200"):
        at_t = utc(at)
        if at_t is None or at_t < since:
            continue
        try:
            detail = json.loads(detail_json or "{}")
        except ValueError:
            detail = {}
        if kind == "kvot_slut":
            out.append({"key": f"kvot_slut:{ref}", "kind": "kvot_slut",
                        "exempt": False, "close": None,
                        "title": "Agenten: dagens tak nått",
                        "message": f"{detail.get('anvanda')} av {detail.get('tak')} "
                                   "körningar använda i dag. Väntande körningar "
                                   "får vänta till i morgon."})
            continue
        ref = ref or ""
        typ = str(detail.get("typ") or ref.split(":", 1)[0])
        text = ROLL_TEXT.get(typ, typ or "körning")
        vad = ref.split(":", 1)[1] if ":" in ref else ref
        key = "roll:" + (dedup_key.split(":", 1)[1] if dedup_key else ref)
        if kind == "roll_klar":
            summary = " ".join(_RAD.sub("[rad]", str(detail.get("sammanfattning") or ""))
                               .split())
            if len(summary) > SAMMANFATTNING_MAX:
                summary = summary[:SAMMANFATTNING_MAX - 1].rstrip() + "…"
            out.append({"key": key, "kind": "roll_klar", "exempt": False,
                        "close": None, "title": f"Agenten: {text} klar",
                        "message": summary or f"{text.capitalize()} {vad} klar "
                                              "(ingen sammanfattning)."})
        else:
            if detail.get("status") == "timeout":
                hur, titel = "nådde tidsgränsen", "avbröts"
            elif detail.get("avbruten"):
                hur, titel = "avbröts innan den var klar", "avbröts"
            else:
                hur, titel = "misslyckades", "misslyckades"
            out.append({"key": key, "kind": "roll_fel", "exempt": False,
                        "close": None, "title": f"Agenten: {text} {titel}",
                        "message": f"{text.capitalize()} {vad} {hur}. "
                                   "Se Agent-fliken."})
    return out


def skicka(conn, *, now: dt.datetime, sender: Optional[Sender] = None,
           topic_name: Optional[str] = None, link: Optional[str] = None) -> dict:
    """Skicka nya notiser. `sender` injiceras i testerna; i drift ntfy."""
    report = {"skickade": 0, "uppskjutna": 0, "utan_amne": 0, "fel": 0}
    link = link if link is not None else (os.environ.get(LINK_ENV) or None)
    quiet = tysta_timmar(now)
    for item in kandidater(conn, now=now):
        dedup = f"notis:{item['key']}"
        if tillstand.har_handelse(conn, dedup):
            continue
        if item["close"] is not None and item["close"] <= now:
            continue     # spelstoppet har passerat — notisen har inget värde
        if quiet and not item["exempt"]:
            report["uppskjutna"] += 1
            continue
        detail = {"kind": item["kind"], "title": item["title"]}
        if not topic_name:
            tillstand.logga(conn, "notis", item["key"],
                            {**detail, "skickad": False, "orsak": "ämne saknas"},
                            now=now, dedup_key=dedup)
            report["utan_amne"] += 1
            continue
        ok = (sender or ntfy_sender)(topic_name, item["title"], item["message"],
                                     lank_for(link, item))
        if ok:
            tillstand.logga(conn, "notis", item["key"], {**detail, "skickad": True},
                            now=now, dedup_key=dedup)
            report["skickade"] += 1
        else:
            tillstand.logga(conn, "notis_fel", item["key"], detail, now=now)
            report["fel"] += 1
    return report


def testnotis(conn, *, now: dt.datetime, sender: Optional[Sender] = None,
              topic_name: Optional[str] = None, link: Optional[str] = None,
              inbox_id: Optional[int] = None) -> dict:
    """En testnotis med beslutssidans länk (`cli.py spelai-testnotis`).

    Bokförs i journalen som `notis_test` med adressen, så att det syns vilken
    länk som provades och om ntfy tog emot den. Ingen dedup: varje prov räknas."""
    link = link if link is not None else (os.environ.get(LINK_ENV) or None)
    url = lank_for(link, {"kind": "beslut", "inbox_id": inbox_id})
    detail = {"lank": url, "bas": link, "skickad": False}
    if not topic_name:
        detail["orsak"] = "ämne saknas"
    elif not url:
        detail["orsak"] = f"{LINK_ENV} saknas eller är ogiltig"
    else:
        detail["skickad"] = bool((sender or ntfy_sender)(
            topic_name, "Testnotis",
            "Tryck här: länken ska öppna beslutssidan i Spelkompisen "
            "(Tailscale behöver vara på i telefonen).", url))
        if not detail["skickad"]:
            detail["orsak"] = "ntfy svarade inte"
    tillstand.logga(conn, "notis_test", str(inbox_id) if inbox_id else None,
                    detail, now=now)
    return detail
