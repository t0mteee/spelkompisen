"""Settlement av live-radarns capture-ögonblick — shadow-facit, aldrig spelbart.

Steg 2–3 i den förregistrerade planen (docs/live-radar-2026-07-25.md): varje
capture-ögonblick settlas mot de två förregistrerade utfallen, utan
efterhandsval:

* **Utfall A** — minst ett mål (någon sida) inom 15 minuter SPELTID efter
  ögonblicket. Avgörs enbart av senare captures i samma serie (scoreändring
  vid en matchminut inom fönstret).
* **Utfall B** — minst ett ytterligare mål före full tid. Ett observerat
  senare mål räcker för 1 (captures finns bara medan matchen pågår, så målet
  kom bevisligen före full tid); 0 kräver en capture med slutstatus.

Metodregler som styr implementationen:

* **Alla ögonblick settlas, inte bara signaler.** Basraten villkoras
  liga × minutband × målställningsdiff, och kontrollgruppen är just
  icke-signal-ögonblicken — utan dem finns inget jämförelsetal.
* **Signalen räknas om deterministiskt** ur radens råa fält med SAMMA funktion
  som API-payloaden använder (`live_radar.radar_signal`, jämförelsepunkten via
  `live_radar.previous_capture`). Ingen andra implementation får finnas.
* **Providrar blandas aldrig** (WP9a-regeln i fotmob.py): Sofascore-serier
  settlas mot Sofascore-captures och FotMob-serier mot FotMob — även utfallen,
  inte bara xG. FotMob-radernas signal räknas på FotMobs egna fält.
* **Censorering i stället för gissning.** Saknas captures som täcker
  15-minutersfönstret, eller slutstatus för utfall B, blir utfallet NULL med
  orsak — aldrig 0.
* **Append-once, ingen efterhandsjustering.** Rader skrivs bara för STÄNGDA
  serier (slutstatus observerad, eller ingen ny capture på
  SERIES_DONE_AFTER_MIN minuter — captures skapas bara medan matchen pågår,
  så en så gammal serie kan inte få fler punkter). Därmed kan inget settlat
  utfall någonsin behöva ändras; `INSERT OR IGNORE` på naturlig nyckel.
* **DB-only**: inga HTTP-anrop. **Shadow**: läses bara av `radar-facit` och
  påverkar aldrig tips, Kelly, notiser, CLV eller modellinput.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from . import live_radar
from .fotmob import CAPTURE_VERSION as FOTMOB_CAPTURE_VERSION
from .live_radar import CAPTURE_VERSION as SOFA_CAPTURE_VERSION

WINDOW_MIN = 15             # utfall A: speltidsfönster efter ögonblicket
MIN_AGE_MIN = 20            # settla först när fönstret hunnit passera i väggtid
SERIES_DONE_AFTER_MIN = 180  # 3 h utan ny capture ⇒ matchen kan inte pågå kvar
# Bara de senaste 30 dagarnas captures betraktas. Säkert eftersom varje serie
# stängs inom timmar efter matchslut och settlas då — spärren finns för att
# varvets DB-arbete inte ska växa med tabellens livstid.
LOOKBACK_DAYS = 30

# Censureringsorsaker (korta tokens, aldrig fritext):
#   no_clock           ögonblicket saknar matchminut — inget fönster kan definieras
#   no_score           ögonblicket saknar målställning (förekommer hos FotMob)
#   window_not_covered ingen senare capture täcker 15-minutersfönstret entydigt
#   no_final_capture   ingen capture med slutstatus — utfall B:s 0 kan inte bevisas


def _at(row: dict) -> dt.datetime:
    return dt.datetime.fromisoformat(row["captured_at"].replace("Z", "+00:00"))


def _total(row: dict) -> Optional[int]:
    home, away = row.get("home_score"), row.get("away_score")
    if home is None or away is None:
        return None
    return int(home) + int(away)


def _diff(row: dict) -> Optional[int]:
    home, away = row.get("home_score"), row.get("away_score")
    if home is None or away is None:
        return None
    return int(home) - int(away)


def _is_final(row: dict) -> bool:
    """Slutstatus — samma tokens som live_radar._minute räknar som matchslut.

    FotMob-captures saknar statuskolumn (insamlingen hoppar över avslutade
    matcher), så FotMob-serier får aldrig slutstatus här — deras utfall B blir
    censorerat om inget senare mål observerats, precis som kontraktet kräver.
    """
    label = (row.get("status") or "").casefold()
    return "finished" in label or "ended" in label


def _outcome_within_window(moment: dict, later: list[dict],
                           final: Optional[dict]) -> tuple[Optional[int],
                                                           Optional[str]]:
    """Utfall A ur senare captures i SAMMA serie. (utfall, censurorsak)."""
    minute0, total0 = moment.get("minute"), _total(moment)
    if minute0 is None:
        return None, "no_clock"
    if total0 is None:
        return None, "no_score"
    window_end = int(minute0) + WINDOW_MIN
    # 1) Mål observerat vid en matchminut inom fönstret ⇒ 1. Ställningen är
    #    kumulativ, så en högre total vid minut ≤ fönstrets slut bevisar ett
    #    mål efter ögonblicket och inom fönstret.
    for row in later:
        total = _total(row)
        if row.get("minute") is None or total is None:
            continue
        if int(row["minute"]) <= window_end and total > total0:
            return 1, None
    # 2) Oförändrad total vid en minut ≥ fönstrets slut ⇒ 0: monotona totaler
    #    kan inte gömma ett mellanliggande mål.
    for row in later:
        total = _total(row)
        if row.get("minute") is None or total is None:
            continue
        if int(row["minute"]) >= window_end and total == total0:
            return 0, None
    # 3) Matchen slutade utan ytterligare mål ⇒ fönstret kan omöjligt
    #    innehålla ett, även om det sträcker sig förbi full tid.
    if final is not None and _total(final) == total0:
        return 0, None
    # Ett mål SYNS efter fönstret utan täckande capture inne i det (eller
    # serien tog slut mitt i fönstret): tidpunkten är tvetydig — censurera,
    # gissa aldrig nej.
    return None, "window_not_covered"


def _outcome_more_before_ft(moment: dict, later: list[dict],
                            final: Optional[dict]) -> tuple[Optional[int],
                                                            Optional[str]]:
    """Utfall B: minst ett ytterligare mål före full tid."""
    total0 = _total(moment)
    if total0 is None:
        return None, "no_score"
    for row in later:
        total = _total(row)
        if total is not None and total > total0:
            # Captures skrivs bara medan matchen pågår ⇒ målet kom före FT.
            return 1, None
    if final is not None and _total(final) is not None \
            and _total(final) == total0:
        return 0, None
    return None, "no_final_capture"


def _signal_for(provider: str, captures: list[dict], index: int) -> dict:
    """Radera signalfrågan till den DELADE funktionen — aldrig en kopia.

    Jämförelsepunkten väljs som API-payloaden gör: Sofascore via
    `previous_capture` (~15 min bakåt med tolerans), FotMob via närmast
    föregående punkt i den egna serien. Punkten påverkar bara score/reason,
    aldrig nivån — men settlementet ska vara payloadens spegel, inte nästan.
    """
    current = captures[index]
    if provider == "fotmob":
        previous = captures[index - 1] if index > 0 else None
    else:
        previous = live_radar.previous_capture(captures[:index], _at(current))
    return live_radar.radar_signal(current, previous)


def _series(store, since: str) -> list[tuple[str, int, list[dict]]]:
    """Alla capture-serier per provider — sorterade i tidsordning av lagret."""
    out: list[tuple[str, int, list[dict]]] = []
    grouped: dict[int, list[dict]] = {}
    for row in store.oddset_live_captures(since, SOFA_CAPTURE_VERSION):
        grouped.setdefault(int(row["event_id"]), []).append(row)
    out.extend(("sofascore", event_id, captures)
               for event_id, captures in grouped.items())
    grouped = {}
    for row in store.live_fotmob_captures(since, FOTMOB_CAPTURE_VERSION):
        grouped.setdefault(int(row["fotmob_id"]), []).append(row)
    out.extend(("fotmob", event_id, captures)
               for event_id, captures in grouped.items())
    return out


def settle_moments(store, *, now: Optional[dt.datetime] = None) -> dict:
    """Settla alla ögonblick i stängda serier. Idempotent, append-once."""
    now = now or dt.datetime.now(dt.timezone.utc)
    settled_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    since = (now - dt.timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    age_gate = now - dt.timedelta(minutes=MIN_AGE_MIN)
    existing = store.live_settlement_keys()
    report = {"settled": 0, "censored_15min": 0, "censored_ft": 0,
              "open_series": 0, "providers": {}}
    for provider, event_id, captures in _series(store, since):
        final = next(
            (row for row in reversed(captures) if _is_final(row)), None)
        closed = final is not None or (
            now - _at(captures[-1]) >
            dt.timedelta(minutes=SERIES_DONE_AFTER_MIN))
        if not closed:
            report["open_series"] += 1
            continue
        for index, moment in enumerate(captures):
            key = (provider, event_id, moment["captured_at"],
                   moment["capture_version"])
            if key in existing or _at(moment) > age_gate:
                continue
            later = captures[index + 1:]
            outcome_a, censor_a = _outcome_within_window(moment, later, final)
            outcome_b, censor_b = _outcome_more_before_ft(moment, later, final)
            signal = _signal_for(provider, captures, index)
            saved = store.live_settlement_save({
                "provider": provider,
                "event_id": event_id,
                "captured_at": moment["captured_at"],
                "capture_version": moment["capture_version"],
                "league": moment.get("league"),
                "minute": moment.get("minute"),
                "score_diff": _diff(moment),
                "signal": 1 if signal.get("level") in ("watch", "strong")
                          else 0,
                "signal_type": signal.get("kind"),
                "signal_version": live_radar.RADAR_VERSION,
                "outcome_15min": outcome_a,
                "outcome_more_before_ft": outcome_b,
                "censored_15min": censor_a,
                "censored_ft": censor_b,
                "settled_at": settled_at,
            })
            if saved:
                report["settled"] += 1
                report["providers"][provider] = \
                    report["providers"].get(provider, 0) + 1
                if censor_a:
                    report["censored_15min"] += 1
                if censor_b:
                    report["censored_ft"] += 1
    return report


def format_settle(report: dict) -> str:
    per_provider = ", ".join(f"{provider} {count}" for provider, count
                             in sorted(report["providers"].items()))
    return (f"radar-settle (mode=shadow): {report['settled']} ögonblick"
            + (f" ({per_provider})" if per_provider else "")
            + f" · censur A {report['censored_15min']}"
            + f" · censur B {report['censored_ft']}"
            + f" · {report['open_series']} öppna serier väntar")


# --- Facit: signalögonblick mot villkorad basrate ---------------------------

MINUTE_BANDS = ((0, 15), (15, 30), (30, 45), (45, 60), (60, 75))
OUTCOME_FIELDS = (("outcome_15min", "utfall A: mål inom 15 min"),
                  ("outcome_more_before_ft", "utfall B: fler mål före FT"))


def _minute_band(minute) -> Optional[str]:
    if minute is None:
        return None
    value = int(minute)
    for low, high in MINUTE_BANDS:
        if low <= value < high:
            return f"{low}-{high}"
    return "75+"


def _diff_band(diff) -> Optional[str]:
    if diff is None:
        return None
    clamped = max(-2, min(2, int(diff)))
    return {-2: "-2-", -1: "-1", 0: "0", 1: "+1", 2: "+2+"}[clamped]


def _cell(row: dict) -> Optional[tuple]:
    """Basratecellen liga × minutband × målställningsband — eller None."""
    minute_band = _minute_band(row.get("minute"))
    diff_band = _diff_band(row.get("score_diff"))
    if minute_band is None or diff_band is None or not row.get("league"):
        return None
    return (row["league"], minute_band, diff_band)


def facit(store) -> dict:
    """Träffandel per signaltyp mot villkorad basrate ur kontrollögonblicken.

    Ingen KI-beräkning ännu — volymen är för liten; talen redovisas ärligt
    inklusive censur, och allt är märkt mode=shadow. Kontrollgruppen för en
    signaltyp är icke-signal-ögonblick av SAMMA kind (samma mätbarhet: en
    xG-signal jämförs med xG-täckta ögonblick, en proxysignal med proxytäckta).
    """
    rows = store.live_settlement_rows()
    out = {"mode": "shadow", "signal_version": live_radar.RADAR_VERSION,
           "n_moments": len(rows), "groups": {}}
    for signal_type in ("xg", "proxy"):
        of_type = [row for row in rows if row.get("signal_type") == signal_type]
        signals = [row for row in of_type if row["signal"]]
        controls = [row for row in of_type if not row["signal"]]
        group = {
            "n_signal_moments": len(signals),
            "n_signal_matches": len({(row["provider"], row["event_id"])
                                     for row in signals}),
            "n_control_moments": len(controls),
            "outcomes": {},
        }
        for field, label in OUTCOME_FIELDS:
            resolved = [row for row in signals if row[field] is not None]
            hits = sum(int(row[field]) for row in resolved)
            cells: dict[tuple, list[int]] = {}
            for row in controls:
                cell = _cell(row)
                if row[field] is None or cell is None:
                    continue
                cells.setdefault(cell, []).append(int(row[field]))
            matched_rates: list[float] = []
            without_cell = 0
            for row in resolved:
                cell = _cell(row)
                if cell is None or cell not in cells:
                    without_cell += 1
                    continue
                values = cells[cell]
                matched_rates.append(sum(values) / len(values))
            group["outcomes"][field] = {
                "label": label,
                "n_resolved": len(resolved),
                "hits": hits,
                "rate": hits / len(resolved) if resolved else None,
                "censored": len(signals) - len(resolved),
                # basraten viktas som signalgruppen: medel av cellernas
                # kontrollrater över de settlade signalögonblicken
                "base_rate": (sum(matched_rates) / len(matched_rates)
                              if matched_rates else None),
                "base_n_signal_moments": len(matched_rates),
                "without_cell": without_cell,
                "control_resolved": sum(len(v) for v in cells.values()),
                "control_censored": sum(1 for row in controls
                                        if row[field] is None),
            }
        out["groups"][signal_type] = group
    return out


def _pct(value: Optional[float]) -> str:
    return f"{100 * value:.1f}%" if value is not None else "–"


def format_facit(report: dict) -> str:
    lines = [f"Radar-facit (mode=shadow · {report['signal_version']}) · "
             f"{report['n_moments']} settlade ögonblick totalt"]
    for signal_type in ("xg", "proxy"):
        group = report["groups"][signal_type]
        lines.append(
            f"{signal_type}: {group['n_signal_moments']} signalögonblick i "
            f"{group['n_signal_matches']} matcher · "
            f"{group['n_control_moments']} kontrollögonblick")
        for field, _label in OUTCOME_FIELDS:
            data = group["outcomes"][field]
            lines.append(
                f"  {data['label']}: {data['hits']}/{data['n_resolved']} = "
                f"{_pct(data['rate'])} mot basrate {_pct(data['base_rate'])} "
                f"(villkorad liga×minutband×ställning, "
                f"{data['control_resolved']} kontroller) · "
                f"censur {data['censored']} signal / "
                f"{data['control_censored']} kontroll"
                + (f" · {data['without_cell']} signalögonblick utan basratecell"
                   if data["without_cell"] else ""))
    lines.append("Shadow-läge: påverkar inga tips, Kelly, notiser, CLV eller "
                 "modellinput.")
    return "\n".join(lines)
