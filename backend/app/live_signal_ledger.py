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
from collections import Counter
from typing import Optional

from . import (altenar, flashscore_data, kambi, live_radar, live_settlement,
               oddset_data, pinnacle)
from .oddset import _team_sim
from .storage import Storage

BLIND_MIN_PRICED = 200
BLIND_MIN_DAYS = 60
BOOTSTRAP_ITERS = 2000
PINNACLE_LIVE_MAX_AGE_S = 90

# ANKARE ≠ BOK, även live. Pinnacle går att spela hos, men den är projektets
# fair-value-ankare och har klart lägst marginal — den vinner därför nästan
# varje prisjämförelse. En ROI mätt på Pinnacles pris är därför inte "vad en
# bok gav mig" utan "vad fair value gav mig". Källan mäts och redovisas fullt
# ut, men märks som ospelbar i per-källa-facitet så att den inte läses som ett
# bokresultat. Samma princip som `ANCHOR_SOURCES` i oddset_value.
PLAYABLE_LIVE_SOURCES = frozenset({"svenskaspel", "ninja"})


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


# Bekräftade resultatnamn som är semantiskt samma klubb men inte kan lösas av
# en generell prefixregel. Tabellen används BARA när motståndaren redan
# matchar strikt, datumet är exakt och exakt en resultatrad återstår.
_RESULT_TEAM_ALIASES = {
    "hearts": "heart of midlothian",
}
_RESULT_TEAM_REJECTED = {
    frozenset({"egersund", "haugesund"}),
}


def _context_same_team(a: str, b: str) -> bool:
    """Svag lagjämförelse som aldrig får stå ensam som matchbevis."""
    if live_radar._same_team(a, b):
        return True
    x, y = live_radar.live_norm_team(a), live_radar.live_norm_team(b)
    x = _RESULT_TEAM_ALIASES.get(x, x)
    y = _RESULT_TEAM_ALIASES.get(y, y)
    if (frozenset({x, y}) in live_radar.LIVE_TEAM_REJECTED
            or frozenset({x, y}) in _RESULT_TEAM_REJECTED):
        return False
    if live_radar._squad(x) != live_radar._squad(y):
        return False
    return (live_radar._same_team_in_context(x, y)
            or _team_sim(x, y) >= 0.75)


def _match_orientation(home: str, away: str, other_home: str,
                       other_away: str, *, allow_context: bool) -> Optional[bool]:
    """Returnera False för rak, True för speglad och None för ingen länk.

    Kontextregeln kräver alltid att den ANDRA sidan matchar strikt. Därmed kan
    ett kortnamn som `Odense` länkas till `Odense Boldklub`, men aldrig två
    ungefärliga lag samtidigt.
    """
    home_direct = live_radar._same_team(home, other_home)
    away_direct = live_radar._same_team(away, other_away)
    if home_direct and away_direct:
        return False
    home_mirror = live_radar._same_team(home, other_away)
    away_mirror = live_radar._same_team(away, other_home)
    if home_mirror and away_mirror:
        return True
    if not allow_context:
        return None
    if ((home_direct and _context_same_team(away, other_away))
            or (away_direct and _context_same_team(home, other_home))):
        return False
    if ((home_mirror and _context_same_team(away, other_home))
            or (away_mirror and _context_same_team(home, other_away))):
        return True
    return None


def _live_kambi_match(match: dict, events: list[dict]) -> Optional[dict]:
    """Koppla ett pågående radarkort direkt till Kambis pågående lista.

    Prematchkanonen täcker inte alla forskningsligor och träningsmatcher.
    Båda kandidaterna är däremot bevisat live i samma anropsögonblick. Två
    lag krävs, och en kontextlänk kräver en strikt sida; tvetydighet ger inget
    pris. Detta förbättrar framtida täckning utan att bakfylla gamla odds.
    """
    candidates = []
    for event in events:
        mirrored = _match_orientation(
            match.get("home") or "", match.get("away") or "",
            event.get("home") or "", event.get("away") or "",
            allow_context=True)
        if mirrored is not None:
            candidates.append(event)
    if len(candidates) != 1:
        return None
    return {"kambi_id": str(candidates[0]["id"])}


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


def _unique_live_event(match: dict, events: list[dict]) -> tuple[Optional[dict], str]:
    """Entydig tvåsidig lagmatchning för en oddsproviders livelista."""
    candidates = [
        event for event in events
        if _match_orientation(
            match.get("home") or "", match.get("away") or "",
            event.get("home") or "", event.get("away") or "",
            allow_context=True) is not None
    ]
    if len(candidates) == 1:
        return candidates[0], "captured"
    return None, "ambiguous_match" if candidates else "no_match"


def _source_quote(source: str, *, checked_at: str, status: str,
                  event_id=None, observed_at=None, age_s=None,
                  total: Optional[dict] = None,
                  offers: Optional[list[dict]] = None) -> dict:
    return {
        "source": source,
        "provider_event_id": str(event_id) if event_id is not None else None,
        "checked_at": checked_at,
        "observed_at": observed_at,
        "status": status,
        "age_s": age_s,
        "main": total,
        "offers": offers if offers is not None else ([total] if total else []),
    }


def _refresh_pinnacle(event: dict) -> Optional[dict]:
    """Färskt Pinnacle-pris för EN redan identifierad livematch.

    Identiteten kommer ur bulken (den duger — lagnamn ändras inte), men priset
    hämtas om per matchup-id. Fel isoleras: misslyckas det behåller anroparen
    bulkobservationen, som i värsta fall bara märks `stale` som förut.
    """
    ids = [str(i) for i in (event.get("matchup_ids") or []) if i]
    if not ids:
        return None
    try:
        with pinnacle.Pinnacle(timeout=6.0) as client:
            return client.refresh_live_total(ids)
    except Exception:  # noqa: BLE001 — aldrig fälla signalen på en oddskälla
        return None


class _LivePriceCollector:
    """Ett bulk-anrop per källa och radarvarv, sedan lokala matchningar.

    Alla tre källor frågas även när den första ger pris. Det är nödvändigt för
    att `bäst odds` ska vara ett observerat val och för att coverage ska kunna
    följas per källa. Fel isoleras per provider och får aldrig fälla signalen.
    """

    def __init__(self):
        self._catalogues: dict[str, dict] = {}

    def _catalogue(self, source: str) -> dict:
        if source in self._catalogues:
            return self._catalogues[source]
        try:
            if source == "svenskaspel":
                rows = kambi.live_events(timeout=8.0)
                age_s = max(0, int(kambi.last_age_s or 0))
            elif source == "ninja":
                rows = altenar.live_events(
                    integration="ninjacasinose", timeout=8.0, strict=True)
                age_s = max(0, int(altenar.last_age_s or 0))
            elif source == "pinnacle":
                with pinnacle.Pinnacle(timeout=8.0) as client:
                    rows = client.soccer_live_totals()
                    age_s = max(0, int(client.last_age_s or 0))
            else:  # pragma: no cover — intern konstant skyddar
                raise ValueError(source)
            result = {"rows": rows, "age_s": age_s,
                      "checked_at": _iso(_now()), "error": None}
        except Exception as exc:  # noqa: BLE001 — fel isoleras per oddsprovider
            result = {"rows": [], "age_s": None, "checked_at": _iso(_now()),
                      "error": f"source_error:{type(exc).__name__}"}
        self._catalogues[source] = result
        return result

    def _kambi(self, match: dict, canonical: Optional[dict]) -> dict:
        catalogue = self._catalogue("svenskaspel")
        checked_at = catalogue["checked_at"]
        if catalogue["error"]:
            return _source_quote("svenskaspel", checked_at=checked_at,
                                 status=catalogue["error"])
        odds_match = canonical
        if not (odds_match or {}).get("kambi_id"):
            odds_match = _live_kambi_match(match, catalogue["rows"]) or odds_match
        event_id = (odds_match or {}).get("kambi_id")
        if not event_id:
            return _source_quote("svenskaspel", checked_at=checked_at,
                                 status="no_match")
        result = _live_total(odds_match)
        status = result.get("odds_status") or "not_offered"
        total = None
        if status == "captured":
            total = {"line": result["ou_line"], "O": result["over_odds"],
                     "U": result["under_odds"]}
        return _source_quote(
            "svenskaspel", checked_at=_iso(_now()), status=status,
            event_id=event_id, observed_at=result.get("odds_observed_at"),
            age_s=max(0, int(kambi.last_age_s or 0)), total=total)

    def _listed(self, source: str, match: dict) -> dict:
        catalogue = self._catalogue(source)
        if catalogue["error"]:
            return _source_quote(source, checked_at=catalogue["checked_at"],
                                 status=catalogue["error"])
        event, match_status = _unique_live_event(match, catalogue["rows"])
        if not event:
            return _source_quote(source, checked_at=catalogue["checked_at"],
                                 status=match_status,
                                 age_s=catalogue["age_s"])
        checked_at = catalogue["checked_at"]
        age_s = int(event.get("age_s", catalogue["age_s"]) or 0)
        status = event.get("status") or "not_offered"
        if source == "pinnacle":
            # Bulkens live-pris ligger i samma 905-sekunderscache som
            # prematch och var därför för gammalt i de flesta signalögonblick.
            # Matchen är redan identifierad ur bulken; priset hämtas om direkt
            # på matchup-id. Endast matcher med signal berörs.
            fresh = _refresh_pinnacle(event)
            if fresh is not None:
                checked_at = _iso(_now())
                age_s = int(fresh.get("age_s") or 0)
                status = fresh.get("status") or "not_offered"
                event = {**event, "ou": fresh.get("ou"),
                         "offers": fresh.get("offers") or []}
            if status == "captured" and age_s > PINNACLE_LIVE_MAX_AGE_S:
                status = "stale"
        observed_at = _iso(_at(checked_at) - dt.timedelta(seconds=age_s))
        return _source_quote(
            source, checked_at=checked_at, status=status,
            event_id=event.get("id"), observed_at=observed_at, age_s=age_s,
            total=event.get("ou"), offers=event.get("offers") or [])

    def observe(self, match: dict, canonical: Optional[dict]) -> list[dict]:
        # Ordningen är fast men urvalet nedan är oberoende av anropsordningen.
        return [self._kambi(match, canonical),
                self._listed("ninja", match),
                self._listed("pinnacle", match)]


def _choose_live_price(observations: list[dict]) -> tuple[dict, list[dict]]:
    """Välj högsta Över-odds på exakt samma, förregistrerade huvudlina.

    Pinnacles färska huvudlina definierar spelet när den finns; annars behålls
    Kambi som kontinuitetsankare och Ninja är sista reserv. Att jämföra 2.20
    på Ö3.5 med 1.90 på Ö2.5 vore inte `bäst odds` utan två olika spel.
    Därför jämförs böcker endast på samma lina; Pinnacles alternativlinor gör
    att den ändå ofta kan delta när en mjuk boks huvudlina väljs.
    """
    priority = {"pinnacle": 0, "svenskaspel": 1, "ninja": 2}
    eligible = [obs for obs in observations
                if obs.get("status") == "captured" and obs.get("main")]
    anchor = min(eligible, key=lambda obs: priority[obs["source"]], default=None)
    checked_at = max((obs.get("checked_at") for obs in observations
                      if obs.get("checked_at")), default=_iso(_now()))
    quotes = []
    candidates = []
    canonical_line = float(anchor["main"]["line"]) if anchor else None
    for observation in observations:
        status = observation.get("status") or "unknown"
        offer = observation.get("main")
        if status == "captured" and canonical_line is not None:
            offer = next((candidate for candidate in observation.get("offers") or []
                          if abs(float(candidate["line"]) - canonical_line) < 1e-9),
                         None)
            if offer is None:
                offer = observation.get("main")
                status = "line_mismatch"
        quote = {
            "source": observation["source"],
            "provider_event_id": observation.get("provider_event_id"),
            "observed_at": observation.get("observed_at"),
            "checked_at": observation.get("checked_at") or checked_at,
            "status": status,
            "line": float(offer["line"]) if offer else None,
            "over_odds": float(offer["O"]) if offer else None,
            "under_odds": float(offer["U"]) if offer else None,
            "selected": 0,
            "age_s": observation.get("age_s"),
        }
        quotes.append(quote)
        if status == "captured" and quote["over_odds"] is not None:
            candidates.append(quote)

    if not candidates:
        statuses = {quote["status"] for quote in quotes}
        overall = ("all_sources_failed" if statuses and all(
            status.startswith("source_error") for status in statuses)
            else "no_eligible_quote")
        return {"odds_status": overall}, quotes

    best = max(candidates, key=lambda quote: (
        quote["over_odds"], -priority.get(quote["source"], 99)))
    best["selected"] = 1
    return {
        "odds_source": best["source"],
        "odds_observed_at": best["observed_at"],
        "ou_line": best["line"],
        "over_odds": best["over_odds"],
        "under_odds": best["under_odds"],
        "odds_status": "captured",
    }, quotes


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
    price_collector: Optional[_LivePriceCollector] = None
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
            if price_collector is None:
                price_collector = _LivePriceCollector()
            observations = price_collector.observe(match, canonical)
            odds, quotes = _choose_live_price(observations)
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
            }, quotes=quotes)
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
        mirrored = _match_orientation(
            signal.get("home") or "", signal.get("away") or "",
            result.get("home") or "", result.get("away") or "",
            # Utan exakta avsparkar får den svagare namnregeln bara användas
            # samma kalenderdag. ±1 dygn behålls enbart för två strikt
            # matchande lag (UTC-/lokaldatumsfallet).
            allow_context=distance == 0)
        if mirrored is not None:
            candidates.append((distance, result, mirrored))
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
                   now: Optional[dt.datetime] = None,
                   refresh_recent: bool = False) -> dict:
    """Settla öppna signaler mot observerat slutresultat, append-once."""
    fixed = now
    now = now or _now()
    report = {"settled": 0, "waiting_result": 0,
              "ambiguous_or_invalid": 0, "recent_results": {}}
    signals = store.live_unsettled_signals()
    if refresh_recent:
        report["recent_results"] = flashscore_data.refresh_recent_results(
            store, signals, now=now)
    by_league: dict[str, list[dict]] = {}
    for signal in signals:
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


def _source_roi(settled: list[dict]) -> dict:
    """Kontrafaktisk Över-ROI PER ODDSKÄLLA — diagnostik, aldrig grind.

    Alla källor prissätter exakt den lina signalen bokförde, så den enda
    skillnaden mellan raderna är priset. Då blir "vad hade jag tjänat om jag
    alltid spelat hos X" en ren jämförelse och inte tre olika spel.

    Två tal måste läsas ihop. `n_priced` är täckningen: en källa som listar
    hälften av matcherna kan ha bäst ROI utan att vara ett bättre val, och
    urvalet är dessutom inte slumpmässigt — en bok som stänger marknaden när
    den är osäker lämnar just de matcherna ur sin egen serie. `n_best` säger
    hur ofta källan faktiskt vann prisjämförelsen.

    Pinnacle redovisas som EGEN rad och inte som en bok bland andra: den är
    projektets ankare, har lägst marginal och vinner därför nästan alltid
    "bäst odds". Att låta den bära huvudsiffran vore att mäta ROI mot ett pris
    som ligger på fair value (ANKARE ≠ BOK).
    """
    per: dict[str, dict] = {}
    for row in settled:
        home, away = row.get("final_home_score"), row.get("final_away_score")
        if home is None or away is None:
            continue
        goals = int(home) + int(away)
        for quote in row.get("odds_quotes") or []:
            source = str(quote.get("source") or "unknown")
            item = per.setdefault(
                source, {"n_asked": 0, "n_priced": 0, "n_best": 0,
                         "profits": [], "odds": []})
            item["n_asked"] += 1
            if int(quote.get("selected") or 0):
                item["n_best"] += 1
            if quote.get("status") != "captured":
                continue
            _, profit = _over_profit(
                goals, quote.get("line"), quote.get("over_odds"))
            if profit is None:
                continue
            item["n_priced"] += 1
            item["profits"].append(profit)
            item["odds"].append(float(quote["over_odds"]))
    out = {}
    for source, item in sorted(per.items()):
        profits = item["profits"]
        out[source] = {
            "n_asked": item["n_asked"],
            "n_priced": item["n_priced"],
            "n_best": item["n_best"],
            "playable": source in PLAYABLE_LIVE_SOURCES,
            "roi_over": (round(sum(profits) / len(profits), 4)
                         if profits else None),
            "roi_ci90": _ci90(profits),
            "avg_over_odds": (round(sum(item["odds"]) / len(item["odds"]), 3)
                              if item["odds"] else None),
        }
    return out


def _summary(rows: list[dict]) -> dict:
    settled = [row for row in rows if row.get("settled_at")]
    priced_signals = [row for row in rows
                      if row.get("odds_status") == "captured"
                      and row.get("ou_line") is not None
                      and row.get("over_odds") is not None]
    priced = [row for row in settled if row.get("over_profit") is not None]
    profits = [float(row["over_profit"]) for row in priced]
    goal15 = [int(row["outcome_15min"]) for row in settled
              if row.get("outcome_15min") is not None]
    more = [int(row["outcome_more_before_ft"]) for row in settled
            if row.get("outcome_more_before_ft") is not None]
    goals = [int(row["goals_after_signal"]) for row in settled
             if row.get("goals_after_signal") is not None]
    dates = [_at(row["captured_at"]) for row in priced]
    odds_status_counts = Counter(
        str(row.get("odds_status") or "unknown") for row in rows)
    quote_source_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        for quote in row.get("odds_quotes") or []:
            counts = quote_source_counts.setdefault(quote["source"], {})
            status = str(quote.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    return {
        "n_signals": len(rows),
        "n_matches": len({row["match_key"] for row in rows}),
        "n_settled": len(settled),
        "n_priced_signals": len(priced_signals),
        "n_priced_settled": len(priced),
        "odds_status_counts": dict(sorted(odds_status_counts.items())),
        "quote_source_counts": {
            source: dict(sorted(counts.items()))
            for source, counts in sorted(quote_source_counts.items())
        },
        "source_roi": _source_roi(settled),
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
    first_ids = {row["id"] for row in first}
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
        level_bets = [row for row in selected
                      if row["id"] in first_ids
                      and row.get("odds_status") == "captured"
                      and row.get("ou_line") is not None
                      and row.get("over_odds") is not None]
        groups.append({"signal_type": kind, "signal_level": level,
                       "n_test_bets": len(level_bets),
                       "n_test_bets_settled": sum(
                           bool(row.get("settled_at")) for row in level_bets),
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
    # Märk exakt vilka rader som utgör blindtestets låtsasspel. Första aktiva
    # signalen per fysisk match är det förregistrerade beslutet. En senare
    # Stark-rad är diagnostik även om den råkar ha odds; en första signal utan
    # observerat pris är heller inget spel och får aldrig visas som vinst/förlust.
    annotated = []
    seen_matches = set()
    for row in rows:
        blind_entry = row["match_key"] not in seen_matches
        seen_matches.add(row["match_key"])
        priced = (row.get("odds_status") == "captured"
                  and row.get("ou_line") is not None
                  and row.get("over_odds") is not None)
        annotated.append({
            **row,
            "blind_entry": blind_entry,
            "test_bet": bool(blind_entry and priced),
            "test_bet_exclusion": (None if blind_entry and priced else
                                   "later_signal" if not blind_entry else
                                   "no_live_price"),
        })
    return {
        "mode": "shadow", "signal_version": current,
        "all_versions_n_signals": len(all_rows),
        **_version_facit(rows),
        "historical_versions": historical,
        "transitional_n_signals": len(transitional),
        "rows": list(reversed(annotated[-max(1, int(limit)):])),
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
