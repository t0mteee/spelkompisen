"""Frysning: standard och agent per nivå ur ETT indatapaket (designens 5.2).

`spelai-tick` bearbetar obearbetade paket i `spelai_input`:

1. Tidsregeln. Paketet ska vara observerat i horisontens fönster och frysas
   inom `FREEZE_MAX_MIN` efter observationen (30m: 5 min, 6h: 30 min).
   Annars blir alla nivåer `missat` för båda rollerna — en sen frysning skulle
   låta agenten läsa databasen med data som inte fanns vid observationen.
2. Paus ⇒ `pausad` (inte `missat`).
3. Standarden byggs för varje nivå med PH3:s egen byggväg
   (`pool_system_ledger.build_config_rows`) och configs — se STANDARD_CONFIGS.
   Den fryses FÖRE agentkörningen, så att den finns även om agenten kraschar.
4. Agenten anropas EN gång för alla nivåer, i sandbox, och läses bara via
   stdout. En nivå som saknas eller är ogiltig ⇒ `ogiltigt` för just den nivån.

`mark_missed` skriver `missat`/`pausad` för horisonter utan paket när fönstret
passerat. Fönster som öppnade före facitsidans start (`facit_start`) räknas
aldrig. Allt är append-only och idempotent per
(produkt, omgång, nivå, horisont, roll).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
from typing import Callable, Optional

from .. import pool_system_ledger as ph3
from ..analysis import analyze_draw
from . import indata, nivaer, tillstand
from .sandbox import AgentSvar, TIMEOUT_S
from .tillstand import iso, utc

# Standarden per nivå = Spelkompisens byggare på samma budget, strategi medel.
# Nycklarna är PH3:s/forskningsfamiljernas FÖRREGISTRERADE configs; dict:en
# hämtas därifrån (aldrig en kopia), så en ändring där syns här.
STANDARD_CONFIGS = {
    256: "dr1-b256-medel",                 # PH3-championen (alla poolspel)
    512: "dr1-b512-medel",                 # PH3-gridens 512-medel
    5000: "ph5-v4-dr1-b5000-medel",        # PH5 forward, värderader medel
    20000: "reducedmax-v2-dr1-b20000-ev50",  # reducerat max, EV medel
    39366: "mathmax-v2-dr1-b39366-ev50",   # matematiskt max (M-system), EV medel
}
STANDARD_PREFIX = "standard"
# Marginal för standardbygget före agentens tidsfrist (sekunder).
AGENT_MIN_S = 10.0
ROLES = ("standard", "agent")

Clock = Callable[[], dt.datetime]


def standard_config(level: int) -> dict:
    key = STANDARD_CONFIGS[int(level)]
    for config in (*ph3.BENCHMARKS, *ph3.PH5_FORWARD_CONFIGS,
                   *ph3.REDUCEDMAX_FORWARD_CONFIGS, *ph3.MATHMAX_FORWARD_CONFIGS):
        if config["key"] == key:
            return config
    raise KeyError(f"standardconfig {key} finns inte i pool_system_ledger")


def analysis_from_payload(payload: dict):
    """Samma steg som PH3:s freeze_due: analys, värderingsomsättning, jackpot."""
    draw = indata.draw_from_payload(payload["draw"])
    analysis = analyze_draw(draw, indata.decode_sharp(payload.get("sharp")),
                            indata.decode_movement(payload.get("movement")))
    used = float((payload.get("turnover") or {}).get("used") or 0.0)
    if used > (analysis.turnover or 0.0):
        analysis.turnover = used
    jp = max(0.0, float((payload.get("jackpot") or {}).get("value") or 0.0))
    return analysis, jp


def build_standard(payload: dict, level: int, analysis=None, jp=None) -> dict:
    """Standardens förslag för en nivå, i facitsidans valideringsform."""
    if analysis is None:
        analysis, jp = analysis_from_payload(payload)
    config = standard_config(level)
    plan = ph3._prize_plan(payload["product"])  # noqa: SLF001
    rows, _n, _cost, note = ph3.build_config_rows(
        analysis, config, payload["horizon"], plan, jp)
    texts = ["".join(row) for row in rows]
    if nivaer.format_for(level) == "msystem":
        tecken = ["".join(s for s in nivaer.SIGNS if any(r[i] == s for r in texts))
                  for i in range(len(analysis.matches))]
        forslag = {"format": "msystem", "tecken": tecken}
    else:
        forslag = {"format": "rows", "rows": texts}
    out = nivaer.validera(payload["product"], level, forslag,
                          n_matches=len(analysis.matches))
    if out["format"] == "msystem" and out["n_rows"] != len(texts):
        raise nivaer.Ogiltigt(
            f"standardens {len(texts)} rader är inte ett kartesiskt M-system")
    out["config_key"] = config["key"]
    out["note"] = note
    return out


@dataclasses.dataclass
class Rad:
    status: str
    reason: Optional[str] = None
    form: Optional[dict] = None          # nivaer.validera-form
    version: Optional[str] = None
    config_key: Optional[str] = None
    stderr: Optional[str] = None


def _insert(conn, payload_or_draw: dict, level: int, horizon: str, role: str,
            rad: Rad, *, frozen_at: dt.datetime, input_row: Optional[dict],
            code_version: str) -> bool:
    form = rad.form or {}
    tider = (input_row or {}).get("underlag_tider") or {}
    events = (input_row or {}).get("events_order")
    rows_text = None
    if form.get("format") == "rows":
        rows_text = "\n".join(form["rows"])
    cur = conn.execute(
        "INSERT OR IGNORE INTO spelai_pool_proposal (product, draw_number, "
        "level_kr, horizon, role, status, reason, strategy_version, config_key, "
        "format, events_order, rows_text, msystem_json, n_rows, cost_kr, "
        "rows_hash, motivation, input_id, input_observed_at, obs_svs_at, "
        "obs_sharp_at, obs_turnover_at, reg_close_time, frozen_at, code_version, "
        "agent_stderr) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (payload_or_draw["product"], int(payload_or_draw["draw_number"]),
         int(level), horizon, role, rad.status, rad.reason, rad.version,
         rad.config_key, form.get("format"),
         ",".join(str(e) for e in events) if events else None,
         rows_text,
         json.dumps(form["tecken"]) if form.get("tecken") else None,
         form.get("n_rows"), form.get("cost_kr"), form.get("rows_hash"),
         form.get("motivering"),
         (input_row or {}).get("_id"), (input_row or {}).get("observed_at"),
         tider.get("svs"), tider.get("sharp"), tider.get("omsattning"),
         payload_or_draw["reg_close_time"], iso(frozen_at), code_version,
         rad.stderr))
    return cur.rowcount == 1


def _has_rows(conn, product: str, draw_number: int, horizon: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM spelai_pool_proposal WHERE product=? AND draw_number=? "
        "AND horizon=? LIMIT 1", (product, draw_number, horizon)).fetchone() is not None


def _write_all(conn, head: dict, horizon: str, status: str, reason: str, *,
               now: dt.datetime, input_row: Optional[dict], code_version: str) -> int:
    n = 0
    for level in nivaer.nivaer_for(head["product"]):
        for role in ROLES:
            n += _insert(conn, head, level, horizon, role, Rad(status, reason),
                         frozen_at=now, input_row=input_row,
                         code_version=code_version)
    conn.commit()
    return n


def _agent_rows(payload: dict, svar: AgentSvar) -> dict[int, Rad]:
    levels = list(nivaer.nivaer_for(payload["product"]))
    if svar.status == "saknas":
        return {lv: Rad("saknas", svar.reason, stderr=svar.stderr) for lv in levels}
    if svar.status != "ok":
        return {lv: Rad("ogiltigt", svar.reason, stderr=svar.stderr) for lv in levels}
    data = svar.data or {}
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        return {lv: Rad("ogiltigt", "svaret saknar strategiversion ('version')",
                        stderr=svar.stderr) for lv in levels}
    version = version.strip()[:120]
    forslag = data.get("forslag")
    if not isinstance(forslag, dict):
        return {lv: Rad("ogiltigt", "svaret saknar objektet 'forslag'", version=version,
                        stderr=svar.stderr) for lv in levels}
    out = {}
    for level in levels:
        item = forslag.get(str(level))
        if item is None:
            out[level] = Rad("ogiltigt", f"nivån {level} saknas i svaret", version=version)
            continue
        try:
            form = nivaer.validera(payload["product"], level, item,
                                   n_matches=payload["n_matches"])
        except nivaer.Ogiltigt as exc:
            out[level] = Rad("ogiltigt", str(exc), version=version)
            continue
        out[level] = Rad("fryst", None, form=form, version=version)
    return out


def _pending_inputs(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT i.id, i.product, i.draw_number, i.horizon, i.observed_at, "
        "i.reg_close_time, i.payload_json FROM spelai_input i "
        "WHERE NOT EXISTS (SELECT 1 FROM spelai_pool_proposal p WHERE "
        "p.product=i.product AND p.draw_number=i.draw_number AND p.horizon=i.horizon) "
        "ORDER BY i.id").fetchall()
    out = []
    for id_, product, draw_number, horizon, observed_at, close, text in rows:
        payload = json.loads(text)
        payload["_id"] = id_
        out.append(payload)
    return out


def process_inputs(conn, runner, *, clock: Clock, code_version: str = "dev") -> dict:
    """Bearbeta alla obearbetade indatapaket. `runner(payload, nivaer, timeout)`
    → AgentSvar (sandbox.runner_for i drift, en falsk agent i testerna)."""
    report = {"frysta": 0, "missat": 0, "pausad": 0, "agent": {}}
    for payload in _pending_inputs(conn):
        product, draw_number = payload["product"], int(payload["draw_number"])
        horizon = payload["horizon"]
        if _has_rows(conn, product, draw_number, horizon):
            continue
        now = clock()
        close = utc(payload["reg_close_time"])
        observed = utc(payload["observed_at"])
        start, end = indata.window(close, horizon)
        deadline = observed + dt.timedelta(minutes=indata.FREEZE_MAX_MIN[horizon])
        ref = f"{product}:{draw_number}:{horizon}"
        if not (start <= observed <= end):
            n = _write_all(conn, payload, horizon, "missat",
                           f"paketet observerades {iso(observed)}, utanför fönstret "
                           f"[{iso(start)}, {iso(end)}]",
                           now=now, input_row=payload, code_version=code_version)
            report["missat"] += n
            tillstand.logga(conn, "missat", ref, {"orsak": "utanför fönstret"}, now=now)
            continue
        if now > deadline:
            n = _write_all(conn, payload, horizon, "missat",
                           f"bearbetades {iso(now)}, efter fristen {iso(deadline)} "
                           f"({indata.FREEZE_MAX_MIN[horizon]} min efter observationen)",
                           now=now, input_row=payload, code_version=code_version)
            report["missat"] += n
            tillstand.logga(conn, "missat", ref, {"orsak": "frist passerad"}, now=now)
            continue
        if tillstand.pausad(conn):
            n = _write_all(conn, payload, horizon, "pausad",
                           "facitsidan var pausad när förslaget skulle frysas",
                           now=now, input_row=payload, code_version=code_version)
            report["pausad"] += n
            tillstand.logga(conn, "pausad", ref, None, now=now)
            continue

        # 1) standarden — fryses före agentkörningen
        levels = list(nivaer.nivaer_for(product))
        try:
            analysis, jp = analysis_from_payload(payload)
        except Exception as exc:  # noqa: BLE001
            analysis, jp = None, None
            analysis_error = f"{type(exc).__name__}: {exc}"
        for level in levels:
            if analysis is None:
                rad = Rad("saknas", f"underlaget gick inte att analysera ({analysis_error})")
            else:
                try:
                    form = build_standard(payload, level, analysis, jp)
                    rad = Rad("fryst", form.get("note"), form=form,
                              version=f"{STANDARD_PREFIX}:{form['config_key']}",
                              config_key=form["config_key"])
                except Exception as exc:  # noqa: BLE001 — en nivå får inte stoppa resten
                    rad = Rad("saknas", f"standarden kunde inte byggas: "
                                        f"{type(exc).__name__}: {exc}"[:500],
                              config_key=STANDARD_CONFIGS.get(level))
            _insert(conn, payload, level, horizon, "standard", rad,
                    frozen_at=clock(), input_row=payload, code_version=code_version)
        conn.commit()

        # 2) agenten — EN körning för alla nivåer, inom fristen
        left = (deadline - clock()).total_seconds()
        timeout = min(float(TIMEOUT_S), left)
        if timeout < AGENT_MIN_S:
            rows = {lv: Rad("missat", f"ingen tid kvar till fristen {iso(deadline)}")
                    for lv in levels}
            svar = None
        else:
            agent_payload = {k: v for k, v in payload.items() if k != "_id"}
            agent_payload["input_id"] = payload["_id"]
            svar = runner(agent_payload, levels, timeout)
            rows = _agent_rows(payload, svar)
        frozen = clock()
        if svar is not None and svar.status == "ok" and frozen > deadline:
            rows = {lv: Rad("missat", f"agenten svarade {iso(frozen)}, efter fristen "
                                      f"{iso(deadline)}", version=r.version)
                    for lv, r in rows.items()}
        for level, rad in rows.items():
            _insert(conn, payload, level, horizon, "agent", rad, frozen_at=frozen,
                    input_row=payload, code_version=code_version)
        conn.commit()
        statuses = sorted({r.status for r in rows.values()})
        report["agent"][ref] = statuses
        report["frysta"] += 1
        tillstand.logga(conn, "frysning", ref,
                        {"agent": {str(lv): r.status for lv, r in rows.items()},
                         "input_id": payload["_id"]}, now=frozen)
    return report


def mark_missed(conn, *, now: dt.datetime, code_version: str = "dev",
                grace_min: float = 2.0) -> dict:
    """`missat`/`pausad` för horisonter utan paket när fönstret passerat.

    Bara fönster som ÖPPNADE efter facit_start räknas: gamla `Open`-rader i
    `draws` och omgångar före driftsättningen är inga missar."""
    report = {"missat": 0, "pausad": 0}
    start_at = tillstand.facit_start(conn)
    if start_at is None:
        return report
    paused = tillstand.pausad(conn)
    for product, draw_number, state, close_raw in conn.execute(
            "SELECT product, draw_number, state, reg_close_time FROM draws "
            "WHERE reg_close_time IS NOT NULL").fetchall():
        if not nivaer.nivaer_for(product):
            continue
        if state and "cancel" in str(state).lower():
            continue
        close = utc(close_raw)
        if close is None:
            continue
        for horizon in indata.HORIZONS:
            start, end = indata.window(close, horizon)
            if start < start_at or now <= end + dt.timedelta(minutes=grace_min):
                continue
            if _has_rows(conn, product, draw_number, horizon):
                continue
            if conn.execute("SELECT 1 FROM spelai_input WHERE product=? AND "
                            "draw_number=? AND horizon=?",
                            (product, draw_number, horizon)).fetchone():
                continue    # paketet finns — process_inputs avgör
            status = "pausad" if paused else "missat"
            head = {"product": product, "draw_number": draw_number,
                    "reg_close_time": iso(close)}
            n = _write_all(conn, head, horizon, status,
                           f"inget indatapaket observerades i fönstret "
                           f"[{iso(start)}, {iso(end)}]",
                           now=now, input_row=None, code_version=code_version)
            report[status] += n
            tillstand.logga(conn, status, f"{product}:{draw_number}:{horizon}",
                            {"orsak": "inget paket"}, now=now)
    return report
