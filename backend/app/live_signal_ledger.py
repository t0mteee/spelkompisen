"""Framåtriktat signal-ledger för live-radarn (shadow, aldrig autospel).

Råcaptures och kontrollgruppsfacitet finns i ``live_settlement``. Det här
lagret svarar på en annan fråga: vad hände om man agerade på den signal som
faktiskt syntes? Därför sparas första förekomsten per match, signaltyp och
nivå, inklusive den live-Ö/U-lina som gick att observera just då.

Livepriser skrivs aldrig till ``oddset_odds``: den tabellen är prematchkanon
och skulle förorenas av inplay-linjer. Saknat eller stängt livepris sparas som
ett explicit statusvärde, aldrig som ett gissat odds.
"""
from __future__ import annotations

import datetime as dt
import random
from typing import Optional

from . import kambi, live_radar, live_settlement, oddset_data
from .storage import Storage

BLIND_MIN_PRICED = 200
BLIND_MIN_DAYS = 60
BOOTSTRAP_ITERS = 2000


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _at(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _canonical_match(store: Storage, row: dict) -> Optional[dict]:
    """Konservativ livekort→Oddset-identitet för Kambi-id:t.

    Samma liga, samma två lag och högst tre timmars startskillnad. Tvetydig
    topplacering ger ingen match och därmed inget odds — vi gissar aldrig.
    """
    anchor = _at(row.get("start_at") or row["captured_at"])
    candidates = store.oddset_matches(
        _iso(anchor - dt.timedelta(hours=3)),
        _iso(anchor + dt.timedelta(hours=3)))
    matches: list[tuple[float, dict]] = []
    for candidate in candidates:
        if candidate.get("league") != row.get("league"):
            continue
        direct = (live_radar._same_team(candidate.get("home"), row.get("home"))
                  and live_radar._same_team(
                      candidate.get("away"), row.get("away")))
        mirrored = (live_radar._same_team(candidate.get("home"), row.get("away"))
                    and live_radar._same_team(
                        candidate.get("away"), row.get("home")))
        if not direct and not mirrored:
            continue
        try:
            delta = abs((_at(candidate["start"]) - anchor).total_seconds())
        except (KeyError, TypeError, ValueError):
            delta = 3 * 3600
        matches.append((delta, candidate))
    matches.sort(key=lambda item: (item[0], item[1]["id"]))
    if not matches:
        return None
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return None
    return matches[0][1]


def _selected_source(match: dict) -> tuple[str, dict, str]:
    """Providern som BÄR signalen + dess rad och event-id.

    Id:t returneras som sträng: Flashscores är alfanumeriskt, de andra två
    heltal. Lagret behandlar det som en ogenomskinlig nyckel per provider.
    """
    stats_source = (match.get("signal") or {}).get("stats_source")
    if stats_source == "flashscore":
        source = match.get("flashscore") or match
        return ("flashscore", source,
                str(source.get("flashscore_id") or match["flashscore_id"]))
    if stats_source == "fotmob":
        source = match.get("fotmob") or match
        return ("fotmob", source,
                str(source.get("fotmob_id") or match["fotmob_id"]))
    return "sofascore", match, str(match["event_id"])


def _live_total(match: Optional[dict]) -> dict:
    """Observera SvS/Kambis huvudlina Ö/U vid signalen, med ärlig frånvaro.

    Statusvärdena skiljer på tre helt olika observationer (M20-lärdomen):
    ``suspended`` = marknaden sågs men var stängd just då, ``not_offered`` =
    live-Ö/U fanns inte alls i svaret, ``source_error`` = vi vet ingenting
    (fel får aldrig bli en frånvaroobservation)."""
    if not match:
        return {"odds_status": "no_canonical_match"}
    event_id = match.get("kambi_id")
    if not event_id:
        return {"odds_status": "no_svenskaspel_id"}
    try:
        markets = kambi.live_total(str(event_id), timeout=8.0, strict=True)
    except Exception as exc:  # noqa: BLE001 — ett oddsfel får inte fälla radarn
        return {"odds_source": "svenskaspel",
                "odds_status": f"source_error:{type(exc).__name__}"}
    observed_at = _now() - dt.timedelta(seconds=max(0, kambi.last_age_s))
    total = markets.get("ou") or {}
    if not all(total.get(key) is not None for key in ("line", "O", "U")):
        status = ("suspended" if markets.get("reason") == "suspended"
                  else "not_offered")
        return {"odds_source": "svenskaspel",
                "odds_observed_at": _iso(observed_at),
                "odds_status": status}
    return {
        "odds_source": "svenskaspel",
        "odds_observed_at": _iso(observed_at),
        "ou_line": float(total["line"]),
        "over_odds": float(total["O"]),
        "under_odds": float(total["U"]),
        "odds_status": "captured",
    }


def _locked_key(store: Storage, match: dict,
                now: dt.datetime, cohort: str) -> Optional[str]:
    """Stabil journalnyckel: samma fysiska match får ALDRIG två nycklar.

    Utan lås dubbleras blindkohorten tyst i två verifierade lägen: (a) den
    kanoniska Oddset-länkningen dyker upp mitt i matchen (oddskollektorn
    upsertar även startade matcher) och (b) ett FotMob-endast-kort byter till
    Sofascores heltals-id när den serien blir färsk. Nyckeln låses därför till
    den FÖRST bokförda radens match_key: i första hand via providrarnas
    event-id (kortet kan bära båda), i sista hand via lagjämförelse.

    Lagfallbacken är hårt spärrad (verifieringsrundan 2026-08-01 fällde en
    lösare variant): (1) rader från en provider vars id kortet självt bär
    utesluts — samma provider utan id-träff är BEVISAT en annan match, vilket
    stoppar prefix-falskmergar som 'Inter'↔'Inter U23'; (2) spegling
    accepteras (källorna är oense om hemmalag på neutral plan) precis som i
    `_canonical_match`; (3) starttider mer än tre timmar isär (dubbelmöten)
    låser aldrig; (4) fönstret är tre timmar — flippar sker mitt i matchen;
    (5) tvetydighet låser aldrig.

    `cohort` MÅSTE vara den kohort raden kommer att stämplas med, inte
    `RADAR_VERSION`: låset söker bland redan bokförda rader, och en sökning i
    fel kohort hittar dem inte — då skapas exakt den andra nyckeln låset finns
    för att förhindra."""
    identities: list[tuple[str, str]] = []
    raw = match.get("event_id")
    if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
        identities.append(("sofascore", str(raw)))
    fm_id = (match.get("fotmob") or {}).get("fotmob_id") \
        or match.get("fotmob_id")
    if fm_id is not None:
        identities.append(("fotmob", str(fm_id)))
    fs_id = (match.get("flashscore") or {}).get("flashscore_id") \
        or match.get("flashscore_id")
    if fs_id is not None:
        identities.append(("flashscore", str(fs_id)))
    locked = store.live_signal_locked_key(cohort, identities)
    if locked:
        return locked
    providers_with_id = {provider for provider, _ in identities}
    since = _iso(now - dt.timedelta(hours=3))
    keys = set()
    for row in store.live_signal_recent_keys(cohort, since):
        if (row["provider"] in providers_with_id
                or row["league"] != match.get("league")):
            continue
        direct = (live_radar._same_team(row["home"], match.get("home"))
                  and live_radar._same_team(row["away"], match.get("away")))
        mirrored = (live_radar._same_team(row["home"], match.get("away"))
                    and live_radar._same_team(row["away"], match.get("home")))
        if not direct and not mirrored:
            continue
        if row.get("start_at") and match.get("start_at"):
            try:
                gap = abs((_at(row["start_at"]) -
                           _at(match["start_at"])).total_seconds())
            except (TypeError, ValueError):
                gap = 0
            if gap > 3 * 3600:
                continue
        keys.add(row["match_key"])
    return keys.pop() if len(keys) == 1 else None


def _clock(provider: str, source: dict, match: dict) -> dict:
    """Minut/ställning = EXAKT signalens beräkningsbas, med proveniens.

    Journalen HÄRLEDER inte längre lånet på egen hand utan läser signalens
    ``basis``, som `live_radar._signal_with_basis` fyllde i när nivån räknades
    — inklusive `<fält>_source` per fält. Två oberoende härledningar av samma
    sak är just den konstruktion som gick isär i verifieringsrundan
    2026-08-01: journalen bokförde en ställning som motsade både signal_score
    och settlementets providerserie. Med basis som enda sanning kan de inte
    skilja sig åt, och lånets riktning följer automatiskt med när ankarkällan
    byts (Sofascore → Flashscore, 2026-08-06).

    ``clock_source`` är providern när inget lånats, annars 'låntagare+långivare'
    (eller enbart långivaren när ALLA tre fälten lånats). ``clock_observed_at``
    bär långivarens egen observationstid.
    """
    fields = ("minute", "home_score", "away_score")
    basis = (match.get("signal") or {}).get("basis") or {}
    if basis:
        values = {key: basis.get(key) for key in fields}
        lenders = {basis.get(f"{key}_source") for key in fields
                   if basis.get(key) is not None} - {provider, None}
    else:
        # Äldre kort utan basis: ingen härledning, ingen gissning.
        values = {key: source.get(key) for key in fields}
        lenders = set()
    if not lenders:
        return {**values, "clock_source": provider,
                "clock_observed_at": None}
    lender = "+".join(sorted(lenders))
    all_borrowed = all(source.get(key) is None for key in fields)
    return {**values,
            "clock_source": lender if all_borrowed else f"{provider}+{lender}",
            "clock_observed_at": match.get("captured_at")}


def capture_signals(store: Storage, *,
                    now: Optional[dt.datetime] = None) -> dict:
    """Spara nya synliga watch/strong-nivåer och deras livepris append-once."""
    fixed = now
    now = now or _now()
    report = {"candidates": 0, "saved": 0, "priced": 0, "errors": []}
    for match in live_radar.payload(store, now=now).get("matches") or []:
        signal = match.get("signal") or {}
        level, kind = signal.get("level"), signal.get("kind")
        if level not in {"watch", "strong"} or kind not in {"xg", "proxy"}:
            continue
        report["candidates"] += 1
        # Hela kandidaten i ett skydd: ett trasigt kort (saknat id, oväntad
        # payloadform) får aldrig fälla resten av varvet — och felet SYNS i
        # rapporten i stället för att kandidaten tyst försvinner.
        try:
            canonical = _canonical_match(store, match)
            provider, source, provider_event_id = _selected_source(match)
            captured_at = source.get("captured_at") or match["captured_at"]
            # Kohorten avgörs av observationstiden, inte av vilken version som
            # råkar vara laddad. Journalen stämplade förr `RADAR_VERSION` rakt
            # av, så 6 rader hamnade i v5 medan settlementet läste samma
            # ögonblick som v4. En rad producerad av vN-kod före vN:s
            # deklarerade start är `transitional` och ingår i INGEN kohort.
            cohort = live_radar.cohort_for(
                captured_at, produced_by=source.get("radar_version"))
            match_key = (_locked_key(store, match, now, cohort)
                         or (canonical["id"] if canonical
                             else str(match["event_id"])))
            if store.live_signal_exists(match_key, cohort, kind, level):
                continue
            odds = _live_total(canonical)
            saved = store.live_signal_save({
                "match_key": match_key,
                "match_id": canonical["id"] if canonical else None,
                "provider": provider,
                "provider_event_id": provider_event_id,
                "captured_at": captured_at,
                "capture_version": source.get("capture_version")
                or match["capture_version"],
                "signal_version": cohort,
                "league": match["league"],
                "tournament": match.get("tournament"),
                "home": match["home"], "away": match["away"],
                "start_at": match.get("start_at"),
                **_clock(provider, source, match),
                "signal_level": level, "signal_type": kind,
                "signal_team": signal.get("team"),
                "signal_side": signal.get("side"),
                "signal_score": signal.get("score"),
                "chance_gap": signal.get("chance_gap"),
                "total_gap": signal.get("total_gap"),
                "recent_xg": signal.get("recent_xg"),
                "proxy_index": signal.get("proxy_index"),
                "remaining_min": signal.get("remaining_min"),
                "reason": signal.get("reason"),
                "xg_home": source.get("xg_home"),
                "xg_away": source.get("xg_away"),
                "big_chances_home": source.get("big_chances_home"),
                "big_chances_away": source.get("big_chances_away"),
                "shots_on_home": source.get("shots_on_home"),
                "shots_on_away": source.get("shots_on_away"),
                "shots_inside_home": source.get("shots_inside_home"),
                "shots_inside_away": source.get("shots_inside_away"),
                **odds,
                # per kandidat, EFTER oddsanropet — aldrig varvstartens klocka
                # (observationstidsregeln p.3; Kambi-anrop kan ta 8 s styck)
                "recorded_at": _iso(fixed or _now()),
            })
        except Exception as exc:  # noqa: BLE001 — logga nästa kandidat vidare
            report["errors"].append(
                f"{match.get('event_id')}:{kind}:{level}:{type(exc).__name__}")
            continue
        report["saved"] += saved
        report["priced"] += saved * (odds.get("odds_status") == "captured")
    return report


def _result_for(signal: dict, results: list[dict]) -> Optional[tuple[dict, bool]]:
    target = _at(signal.get("start_at") or signal["captured_at"]).date()
    candidates: list[tuple[int, dict, bool]] = []
    for result in results:
        try:
            distance = abs((dt.date.fromisoformat(result["date"]) - target).days)
        except (KeyError, TypeError, ValueError):
            continue
        if distance > 1:
            continue
        # Trasig resultatrad (t.ex. hg satt men ag NULL ur en skadad payload)
        # får varken krascha settlingspasset eller matchas — hoppa över den.
        if result.get("hg") is None or result.get("ag") is None:
            continue
        direct = (live_radar._same_team(result.get("home"), signal.get("home"))
                  and live_radar._same_team(
                      result.get("away"), signal.get("away")))
        mirrored = (live_radar._same_team(result.get("home"), signal.get("away"))
                    and live_radar._same_team(
                        result.get("away"), signal.get("home")))
        if direct or mirrored:
            candidates.append((distance, result, bool(mirrored and not direct)))
    candidates.sort(key=lambda item: (item[0], item[1]["date"],
                                      item[1].get("home") or ""))
    if not candidates:
        return None
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0][1], candidates[0][2]


def _over_profit(total_goals: int, line: Optional[float],
                 odds: Optional[float]) -> tuple[Optional[str], Optional[float]]:
    """Enhetsinsats på Asian Över, inklusive push och kvartslinje."""
    if line is None or odds is None:
        return None, None
    line, odds = float(line), float(odds)
    quarter = abs(line * 2 - round(line * 2)) > 1e-9
    halves = (line - 0.25, line + 0.25) if quarter else (line,)
    profits = []
    for half in halves:
        if total_goals > half:
            profits.append(odds - 1.0)
        elif abs(total_goals - half) < 1e-9:
            profits.append(0.0)
        else:
            profits.append(-1.0)
    profit = sum(profits) / len(profits)
    full_win = odds - 1.0
    if abs(profit - full_win) < 1e-9:
        label = "win"
    elif profit > 0:
        label = "half_win"
    elif abs(profit) < 1e-9:
        label = "push"
    elif profit > -1:
        label = "half_loss"
    else:
        label = "loss"
    return label, round(profit, 4)


def _journal_moment(signal: dict, raw_moment: dict) -> dict:
    """Återskapa exakt den minut/ställning som signalraden bokförde.

    En FotMob-/Flashscore-signal kan ha lånat saknad minut eller ställning från
    sitt verifierade Sofascore-kort. Råproviderns capture är fortfarande rätt
    serie för framtida observationer, men den är då INTE signalögonblickets
    faktiska bas. Journalen är det append-only beslutskvitto användaren såg och
    dess tre fält måste därför vinna även när värdet är NULL (ärlig censur).
    """
    moment = dict(raw_moment)
    for field in ("minute", "home_score", "away_score"):
        moment[field] = signal.get(field)
    return moment


def _later_after_decision(signal: dict, later: list[dict]) -> list[dict]:
    """Ignorera providerpunkter som föregår ett lånat klockögonblick.

    Statistikcapturen kan vara några sekunder äldre än den Sofascore-klocka
    journalen lånade. En capture mellan dessa tider är inte en observation
    *efter* signalbasen och får inte avgöra utfallet.
    """
    observed = _at(signal["captured_at"])
    if signal.get("clock_observed_at"):
        observed = max(observed, _at(signal["clock_observed_at"]))
    return [row for row in later if _at(row["captured_at"]) > observed]


def settle_signals(store: Storage, *,
                   now: Optional[dt.datetime] = None) -> dict:
    """Settla öppna signaler mot observerat slutresultat, append-once."""
    fixed = now
    now = now or _now()
    report = {"settled": 0, "waiting_result": 0,
              "ambiguous_or_invalid": 0}
    by_league: dict[str, list[dict]] = {}
    for signal in store.live_unsettled_signals():
        league = signal["league"]
        if league not in by_league:
            by_league[league] = oddset_data.merged_results(store, league)
        found = _result_for(signal, by_league[league])
        if found is None:
            report["waiting_result"] += 1
            continue
        result, mirrored = found
        home_final = int(result["ag"] if mirrored else result["hg"])
        away_final = int(result["hg"] if mirrored else result["ag"])
        home0, away0 = signal.get("home_score"), signal.get("away_score")
        if (home0 is None or away0 is None or
                home_final + away_final < int(home0) + int(away0)):
            report["ambiguous_or_invalid"] += 1
            continue
        series = store.live_provider_series(
            signal["provider"], signal["provider_event_id"],
            signal["capture_version"])
        try:
            index = next(i for i, row in enumerate(series)
                         if row["captured_at"] == signal["captured_at"])
        except StopIteration:
            report["ambiguous_or_invalid"] += 1
            continue
        moment = _journal_moment(signal, series[index])
        later = _later_after_decision(signal, series[index + 1:])
        final = {**moment, "minute": 90, "status": "Ended",
                 "home_score": home_final, "away_score": away_final}
        outcome_a, censor_a = live_settlement._outcome_within_window(
            moment, later, final)
        outcome_b, censor_b = live_settlement._outcome_more_before_ft(
            moment, later, final)
        goals_after = ((home_final + away_final) -
                       (int(home0) + int(away0)))
        over_result, over_profit = _over_profit(
            home_final + away_final, signal.get("ou_line"),
            signal.get("over_odds"))
        result_key = (f"{league}|{result['date']}|{result.get('home')}|"
                      f"{result.get('away')}")
        report["settled"] += store.live_signal_result_save({
            # settled_at per rad (observationstidsregeln p.3), inte varvstart
            "signal_id": signal["id"], "settled_at": _iso(fixed or _now()),
            "final_home_score": home_final,
            "final_away_score": away_final,
            "goals_after_signal": goals_after,
            "outcome_15min": outcome_a,
            "outcome_more_before_ft": outcome_b,
            "censored_15min": censor_a, "censored_ft": censor_b,
            "over_result": over_result, "over_profit": over_profit,
            "result_source": result.get("source"),
            "result_key": result_key,
        })
    return report


def _ci90(profits: list[float]) -> Optional[list[float]]:
    if len(profits) < 3:
        return None
    rng = random.Random(f"live-signal-roi:{len(profits)}:{sum(profits):.6f}")
    means = []
    for _ in range(BOOTSTRAP_ITERS):
        sample = rng.choices(profits, k=len(profits))
        means.append(sum(sample) / len(sample))
    means.sort()
    return [round(means[int(0.05 * len(means))], 4),
            round(means[min(len(means) - 1, int(0.95 * len(means)))], 4)]


def _summary(rows: list[dict]) -> dict:
    settled = [row for row in rows if row.get("settled_at")]
    priced = [row for row in settled if row.get("over_profit") is not None]
    profits = [float(row["over_profit"]) for row in priced]
    goal15 = [int(row["outcome_15min"]) for row in settled
              if row.get("outcome_15min") is not None]
    more = [int(row["outcome_more_before_ft"]) for row in settled
            if row.get("outcome_more_before_ft") is not None]
    goals = [int(row["goals_after_signal"]) for row in settled
             if row.get("goals_after_signal") is not None]
    dates = [_at(row["captured_at"]) for row in priced]
    return {
        "n_signals": len(rows),
        "n_matches": len({row["match_key"] for row in rows}),
        "n_settled": len(settled),
        "n_priced_settled": len(priced),
        "roi_over": round(sum(profits) / len(profits), 4) if profits else None,
        "roi_ci90": _ci90(profits),
        "over_positive_rate": (round(sum(value > 0 for value in profits)
                                     / len(profits), 4) if profits else None),
        "goal_15min_rate": (round(sum(goal15) / len(goal15), 4)
                            if goal15 else None),
        "n_goal_15min": len(goal15),
        "more_before_ft_rate": (round(sum(more) / len(more), 4)
                                if more else None),
        "avg_goals_after": (round(sum(goals) / len(goals), 3)
                            if goals else None),
        "span_days": ((max(dates) - min(dates)).days if len(dates) >= 2 else 0),
    }


def _version_facit(rows: list[dict]) -> dict:
    """Blindgate och nivågrupper för exakt en, redan filtrerad version."""
    first_by_match: dict[str, dict] = {}
    for row in rows:
        first_by_match.setdefault(row["match_key"], row)
    first = list(first_by_match.values())
    blind = _summary(first)
    ci = blind.get("roi_ci90")
    enough = (blind["n_priced_settled"] >= BLIND_MIN_PRICED and
              blind["span_days"] >= BLIND_MIN_DAYS)
    blind_gate = {
        **blind,
        "required_priced_settled": BLIND_MIN_PRICED,
        "required_span_days": BLIND_MIN_DAYS,
        "status": ("collecting" if not enough else
                   "pass" if ci and ci[0] > 0 else "no_support"),
        "unit": "första aktiva signalen per match",
    }
    groups = []
    keys = sorted({(row["signal_type"], row["signal_level"])
                   for row in rows})
    for kind, level in keys:
        selected = [row for row in rows
                    if row["signal_type"] == kind
                    and row["signal_level"] == level]
        groups.append({"signal_type": kind, "signal_level": level,
                       **_summary(selected)})
    return {
        "forward_only_since": rows[0]["captured_at"] if rows else None,
        "last_captured_at": rows[-1]["captured_at"] if rows else None,
        "blind_gate": blind_gate, "groups": groups,
    }


def facit(store: Storage, limit: int = 200) -> dict:
    """Aktuell blindkohort, med äldre signalversioner tydligt separerade."""
    all_rows = store.live_signal_facit_rows()
    current = live_radar.RADAR_VERSION
    rows = [row for row in all_rows if row["signal_version"] == current]
    # `transitional` är INGEN äldre version — det är rader som ingen kohort
    # äger (vN-kod före vN:s deklarerade start, eller inne i en observerad
    # växling). Att lista dem bland versionerna hade läst som en fjärde kohort.
    transitional = [row for row in all_rows
                    if row["signal_version"] == live_radar.RADAR_TRANSITIONAL]
    old_versions = sorted({row["signal_version"] for row in all_rows
                           if row["signal_version"] not in
                           (current, live_radar.RADAR_TRANSITIONAL)})
    historical = [
        {"signal_version": version,
         **_version_facit([row for row in all_rows
                           if row["signal_version"] == version])}
        for version in old_versions
    ]
    return {
        "mode": "shadow", "signal_version": current,
        "all_versions_n_signals": len(all_rows),
        **_version_facit(rows),
        "historical_versions": historical,
        "transitional_n_signals": len(transitional),
        "rows": list(reversed(rows[-max(1, int(limit)):])),
        "thresholds": {
            "xg_watch": {
                "minute": "15–78, minst 12 minuter kvar",
                "rule": "lagets xG−mål ≥ 0,65 eller matchens xG−mål ≥ 1,00",
            },
            "xg_strong": {
                "minute": "samma tidsfönster som Följer",
                "rule": "lagets xG−mål ≥ 1,15 eller matchens xG−mål ≥ 1,65",
            },
            "proxy_watch": {
                "minute": "20–78, minst 12 minuter kvar",
                "rule": ("stora chanser−mål ≥ 1,5, eller skott på mål−mål "
                         "≥ 5 och minst 8 skott i box"),
            },
            "proxy_strong": None,
        },
    }
