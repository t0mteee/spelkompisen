"""Shadow-radar för livefotboll: chansskapande som överstiger utdelningen.

Radarn är informationsstöd, inte en spelmodell. Den läser separata,
kumulativa serier från Flashscore, FotMob och Sofascore och visar en försiktig
xG- eller proxyflagga. Modulen läser inga liveodds; den separata
``live_signal_ledger`` observerar Kambi-priset när en synlig signal först
uppstår. Inga automatiska spel/notiser skapas.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from typing import Optional

from .oddset import norm_team
from .oddset_data import SOFA_UT
from .storage import Storage

CAPTURE_VERSION = "sofa-live-v2"
# v4 (2026-08-01): källvalet använder kompletthet, färskhet och verifierad
# matchidentitet innan en signal räknas. Det ändrar kohortens datagenererande
# process trots oförändrade trösklar, så blindtestet får en ny version. Äldre
# rader ligger kvar som historik och ska aldrig blandas med v4.
RADAR_VERSION = "chance-gap-shadow-v4"
# Fryst före driftsstart. Råcaptures saknar radarversion, så settlement använder
# dessa gränser för v2 (<08), v3 (08–21) och den rena v4-kohorten (>=21).
# ÄNDRA ALDRIG efter att insamlingen startats igen.
RADAR_V3_STARTED_AT = "2026-08-01T08:00:00Z"
RADAR_VERSION_STARTED_AT = "2026-08-01T21:00:00Z"
RECENT_MINUTES = 15
RECENT_TOLERANCE_MIN = 6
MAX_DISPLAY_AGE_MIN = 12
LINK_START_TOLERANCE_MIN = 30
SOFA_PRESENCE_KEY = "live_radar_sofascore_presence"
FOTMOB_PRESENCE_KEY = "live_radar_fotmob_presence"

# Providerspecifika lagalias för live-länken. Håll dem här, inte i Oddsets
# TEAM_ALIASES: en bekräftad live-dubblett ska inte ändra modellens
# identitetsbehandling eller signalversion. Endast observerade par.
LIVE_TEAM_ALIASES = {
    # Sofascore `ETO FC Győr` ↔ FotMob `Györi ETO`, 2026-07-30.
    "gyori eto": "eto gyor",
    # Samma driftverifiering fann `RSC Anderlecht` ↔ `Anderlecht`.
    "rsc anderlecht": "anderlecht",
    # MLS-natten 2026-08-01/02: Sofascore `LA Galaxy` ↔ Flashscore
    # `Los Angeles Galaxy`, och Flashscore `Atlanta Utd` ↔ Sofascore
    # `Atlanta United`. Båda gav dubbelt journalkort där odds hamnade på den
    # ena raden och facit på den andra — matchen bidrog alltså med NOLL till
    # blindkohorten trots att båda delarna fanns i databasen.
    # MLS- och Allsvenskan-paren (LA Galaxy, Atlanta Utd, IFK-klubbarna) låg
    # först här men flyttades 2026-08-02 till Oddsets `TEAM_ALIASES`: de var
    # inte bara en live-presentationsskillnad utan dubblerade även
    # resultathistoriken, alltså en modellidentitetsfråga. `norm_team` körs
    # före den här tabellen, så länken gäller fortfarande i radarn.
}

# Bekräftat OLIKA klubbar som normaliseringen annars slår ihop. Samma princip
# som `oddset_data.TEAM_REJECTED_LINKS` (Egersund ≠ Haugesund): kända falska
# par skrivs ut explicit, aldrig via en generell regel.
#
# `Los Angeles FC` normaliseras till `los angeles` (FC är föreningssuffix), och
# flerords-prefixregeln nedan gjorde då `los angeles` ≡ `los angeles galaxy`.
# LAFC och LA Galaxy är två MLS-klubbar som spelar samtidigt — en falsk merge
# hade blandat ställning, statistik och odds från skilda matcher.
LIVE_TEAM_REJECTED = {
    frozenset({"los angeles", "los angeles galaxy"}),
}

# EGEN HTTP-VÄG (2026-07-25). Radarn använde `oddset_data._sofa_get` — samma
# klient som matar xG/hörnor till den SPELBARA modellen. En shadow-funktion som
# pollar var femte minut kunde alltså strypa den spelbara pipelinen om
# Sofascore ratelimitar. Radarn har nu egen kortare timeout, eget matchtak och
# egen tidsbudget så att den varken kan hänga varvet eller äta källkvoten.
LIVE_TIMEOUT_S = 8.0        # kortare än modellens 20 s — shadow får inte hänga

# TAKET (omdimensionerat 2026-07-25). Det gamla taket 14 var satt efter en
# GISSNING om tidsbudgeten. Uppmätt kostar ett statistik-anrop **0,06 s**, så
# 90-sekundersbudgeten räcker till över tusen matcher — tiden var alltså aldrig
# den bindande gränsen, och taket klippte i onödan (43 behöriga
# träningsmatcher en lördag).
#
# Det som ÄR en verklig kostnad är antalet anrop mot en DELAD källa: radarn
# pollar var 5:e minut, så varje matchplats kostar 12 anrop/timme mot Sofascore
# — samma källa som matar den SPELBARA xG-pipelinen och frånvarodatan. Att
# fyrdubbla lasten för en shadow-funktion är precis den risk radarn en gång
# fick egen klient för att undvika.
#
# Lösningen är sortering FÖRST, taket som artighetsgräns. Matcher vi REDAN
# VET saknar chansmått läggs sist (`_known_empty_events`), så taket klipper
# dem i stället för Allsvenskan.
# TAKET HÖJT 30→60 (Samans beslut 2026-07-28). Det gamla argumentet ("de som
# klipps är ändå de som döljs — 60 hade gett samma synliga lista till dubbla
# anropen") byggde på träningsmatchernas täckning (~8 av 47 med chansdata).
# Europacuperna ändrade mätläget: kvalmatcher HAR chansdata (15 av 23 uppmätt
# 28/7), och en kvaltorsdag spelar 43 ECL- + 10 EL-matcher samtidigt — vid
# tak 30 klipps matcher som skulle ha VISATS. 60 rymmer hela kvällens slate;
# kostnaden (upp till ~60 × 12 anrop/h, ~30/h i förtätning) accepteras för
# cupkvällar och sorteringen ser till att ett eventuellt klipp fortfarande
# tar det minst värdefulla först.
# De tomma pollas fortfarande när det finns plats kvar, så vi märker om
# statistik dyker upp sent; ett hårt skip hade gjort oss permanent blinda.
MAX_MATCHES = 60
BUDGET_S = 90.0             # backstopp, inte den styrande gränsen
EMPTY_AFTER_MIN = 25        # först efter denna minut räknas "saknar chansmått"
                            # som ett besked; tidigare är tomt helt normalt


def _live_get(path: str):
    """Sofascore-anrop för radarn — medvetet skild från modellens klient."""
    from curl_cffi import requests as cffi
    r = cffi.get(f"https://api.sofascore.com/api/v1{path}",
                 impersonate="chrome", timeout=LIVE_TIMEOUT_S)
    r.raise_for_status()
    return r.json()

# Träningsmatcher ingår i Oddset men saknar en enda stabil ligaidentitet.
TARGET_UT = {tournament_id: league for league, tournament_id in SOFA_UT.items()}
# Sofascore delar upp träningsmatcher på MÅNGA turneringar. 853 (Club Friendly
# Games) täckte 117 av 463 livematcher 2026-07-25, men de nationella
# träningsturneringarna låg helt utanför radarn: England 20 live, Bulgarien 11,
# Polen 8, Serbien 8, Kroatien 5, Tyskland 5. Alla går genom samma spärr som 853
# (`_known_friendly`) — endast matcher som redan finns i Oddset släpps in.
for _friendly_ut in (853, 35960, 27113, 27120, 32053, 32366, 27118):
    TARGET_UT[_friendly_ut] = "friendlies"
FRIENDLY_UT = frozenset({853, 35960, 27113, 27120, 32053, 32366, 27118})

# Europacuperna (2026-07-28): kvalet delar huvudturneringens UT hos Sofascore
# (verifierat: Maccabi TA–Sheriff ut=679, Austria Wien–Liepaja ut=17015), så
# ett id per cup täcker även kvalrundorna. Medvetet DIREKT här och inte via
# SOFA_UT: SOFA_UT ingår i wp9c-POLICY-fingeravtrycket och cuperna ska inte
# fraktuera V2.2-manifestet (samma skäl som Besta deild hölls utanför).
for _cup_ut, _cup_key in ((7, "champions_league"), (679, "europa_league"),
                          (17015, "conference_league")):
    TARGET_UT[_cup_ut] = _cup_key

# Taket delas av ALLA ligor, så en lördag med 43 behöriga träningsmatcher kunde
# tränga ut Allsvenskan helt — och urvalet blev det Sofascore råkade returnera
# först. Riktiga ligor går därför före träningsmatcher, och inom gruppen väljs
# de matcher som har mest kvar att spela (en match i 85:e minuten kan inte längre
# ge en signal).
LEAGUE_PRIORITY = {"allsvenskan": 0, "superettan": 0, "eliteserien": 0,
                   "obosligaen": 0, "bestadeild": 0, "mls": 0,
                   "premier_league": 0, "serie_a": 0,
                   "la_liga": 0, "bundesliga": 0,
                   "champions_league": 0, "europa_league": 0,
                   "conference_league": 0, "friendlies": 1}

STAT_KEYS = {
    "expectedGoals": ("xg_home", "xg_away"),
    "bigChanceCreated": ("big_chances_home", "big_chances_away"),
    "totalShotsOnGoal": ("shots_home", "shots_away"),
    "shotsOnGoal": ("shots_on_home", "shots_on_away"),
    "totalShotsInsideBox": ("shots_inside_home", "shots_inside_away"),
    "touchesInOppBox": ("touches_box_home", "touches_box_away"),
    "cornerKicks": ("corners_home", "corners_away"),
}


def _iso(timestamp: Optional[int]) -> Optional[str]:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(
        int(timestamp), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def record_presence(store: Storage, key: str, active_ids, observed_at: str) -> None:
    """Spara verifierade övergångar från aktiv till ej längre live.

    Frånvaro i EN lista räcker inte ensam: eventet måste finnas i föregående
    lyckade live-lista och saknas i den nya. Det gör att ett tomt/cachat svar
    vid uppstart inte kan radera färska kort. Vid nätfel anropas funktionen
    inte alls och den vanliga 12-minuters-TTL:n fortsätter vara skyddsnät.
    """
    # Id:t hanteras som en ogenomskinlig STRÄNG per provider — Flashscores är
    # alfanumeriskt ('SKg88Q3T'), Sofascores och FotMobs heltal.
    active = {str(value) for value in active_ids if value is not None}
    previous_active: set[str] = set()
    ended_at: dict[str, str] = {}
    previous_observed: Optional[dt.datetime] = None
    raw = store.meta_get(key)
    if raw:
        try:
            saved = json.loads(raw)
            previous_active = {
                str(value) for value in saved.get("active_ids") or []}
            ended_at = {
                str(event_id): str(ended)
                for event_id, ended in (saved.get("ended_at") or {}).items()}
            previous_observed = _parse_iso(saved["observed_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            previous_active, ended_at, previous_observed = set(), {}, None

    observed = _parse_iso(observed_at)
    # En CDN-cache får aldrig skriva en äldre roster ovanpå en nyare.
    if previous_observed and observed < previous_observed:
        return
    for event_id in previous_active - active:
        ended_at.setdefault(event_id, observed_at)
    for event_id in active:
        ended_at.pop(event_id, None)

    # Slutmarkeringarna behövs bara medan en capture fortfarande kan visas.
    keep_after = observed - dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN)
    ended_at = {
        event_id: ended
        for event_id, ended in ended_at.items()
        if _parse_iso(ended) >= keep_after
    }
    store.meta_set(key, json.dumps({
        "observed_at": observed_at,
        "active_ids": sorted(active),
        "ended_at": {str(event_id): ended
                     for event_id, ended in sorted(ended_at.items())},
    }, separators=(",", ":"), sort_keys=True))


def _recently_ended(store: Storage, key: str,
                    now: dt.datetime) -> dict[str, dt.datetime]:
    """Läs endast färska, välformade slutövergångar; annars säkert tomt.

    Nycklarna är STRÄNGAR: presence lagras redan så i JSON, och Flashscores
    event-id är alfanumeriskt (2026-08-01). En heltalstolkning här sprängde
    hela payloaden på första Flashscore-serien.
    """
    raw = store.meta_get(key)
    if not raw:
        return {}
    try:
        saved = json.loads(raw)
        observed = _parse_iso(saved["observed_at"])
        if (now - observed > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN) or
                observed - now > dt.timedelta(minutes=1)):
            return {}
        return {
            str(event_id): _parse_iso(ended)
            for event_id, ended in (saved.get("ended_at") or {}).items()
            if now - _parse_iso(ended) <= dt.timedelta(
                minutes=MAX_DISPLAY_AGE_MIN)
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _ended_after_capture(current: dict, id_key: str,
                         ended: dict[str, dt.datetime]) -> bool:
    event_id = str(current[id_key])
    ended_at = ended.get(event_id)
    if ended_at is None:
        return False
    return ended_at >= _parse_iso(current["captured_at"])


def _score(event: dict, side: str) -> int:
    value = (event.get(f"{side}Score") or {}).get("current")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _minute(event: dict, now: dt.datetime) -> Optional[int]:
    status = (event.get("status") or {}).get("description") or ""
    label = status.casefold()
    if "halftime" in label or "half time" in label:
        return 45
    if "finished" in label or "ended" in label:
        return 90
    period_start = (event.get("time") or {}).get("currentPeriodStartTimestamp")
    if period_start is None:
        return None
    elapsed = max(0, int(now.timestamp()) - int(period_start)) // 60
    if "2nd" in label or "second" in label:
        return min(90, 45 + elapsed)
    if "extra" in label:
        return min(120, 90 + elapsed)
    return min(45, elapsed)


def _all_stats(payload: dict) -> dict[str, tuple[float | int, float | int]]:
    out = {}
    periods = payload.get("statistics") or []
    all_period = next((period for period in periods
                       if period.get("period") == "ALL"), None)
    for group in (all_period or {}).get("groups") or []:
        for item in group.get("statisticsItems") or []:
            key = item.get("key")
            if key not in STAT_KEYS or key in out:
                continue
            home, away = item.get("homeValue"), item.get("awayValue")
            if home is not None and away is not None:
                out[key] = (home, away)
    return out


def _known_empty_events(store: Storage,
                        now: dt.datetime) -> dict[int, int]:
    """{event_id: 0 har haft chansmått · 2 bevisat tom} ur vår EGEN historik.

    Används bara för att sortera taket rättvist. Matcher som inte finns i
    svaret är okända (tier 1) och behandlas som möjliga — en tidig match utan
    statistik får aldrig straffas för att den är tidig, därför kravet på
    minut > EMPTY_AFTER_MIN i den tomma kategorin.
    """
    since = (now - dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[int, int] = {}
    for event_id, had, late_empty in store.conn.execute(
            "SELECT event_id, "
            "  MAX(CASE WHEN shots_on_home IS NOT NULL "
            "        OR big_chances_home IS NOT NULL "
            "        OR shots_inside_home IS NOT NULL "
            "        OR xg_home IS NOT NULL THEN 1 ELSE 0 END), "
            "  MAX(CASE WHEN minute > ? AND shots_on_home IS NULL "
            "        AND big_chances_home IS NULL "
            "        AND shots_inside_home IS NULL "
            "        AND xg_home IS NULL THEN 1 ELSE 0 END) "
            "FROM oddset_live_capture WHERE captured_at >= ? GROUP BY event_id",
            (EMPTY_AFTER_MIN, since)):
        if had:
            out[int(event_id)] = 0
        elif late_empty:
            out[int(event_id)] = 2
    return out


def known_friendly(home: str, away: str, start_ts: Optional[int],
                   known: list[dict]) -> bool:
    """Oddset-spärren för globala träningsturneringar. DELAS av båda
    insamlarna (Sofascore här, FotMob i fotmob.py) — spärren ska bedöma en
    match likadant oavsett vilken källa som såg den.

    Jämförelsen accepterar spegelvänd hemma/borta (2026-07-28): odds-källorna
    och statskällorna är ofta oense om hemmalaget på turné-/neutralplans-
    matcher (Oddset: "WSW–Chelsea", Sofascore: "Chelsea–WSW" — samma avspark),
    och den strikta jämförelsen dolde matchen helt. Samma spegling 1↔2 som
    Pinnacle-matchningen på poolsidan. Tidsfönstret nedan skyddar mot att
    returmötet i en dubbelmatch länkas fel.

    Lagjämförelsen är `_same_team` (prefix ≥4 tecken), inte exakt likhet:
    FotMob kortar namnen ("Western Sydney" för "Western Sydney Wanderers"),
    precis som genitivfallet Djurgården/Djurgårdens IF som regeln byggdes för.
    """
    for match in known:
        known_home, known_away = match.get("home"), match.get("away")
        if not ((_same_team(known_home, home) and
                 _same_team(known_away, away)) or
                (_same_team(known_home, away) and
                 _same_team(known_away, home))):
            continue
        if start_ts is None or not match.get("start"):
            return True
        try:
            known_start = dt.datetime.fromisoformat(
                match["start"].replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return True
        if abs(known_start - int(start_ts)) <= 2 * 3600:
            return True
    return False


def _known_friendly(event: dict, known: list[dict]) -> bool:
    """Tränings-UT 853 är global: ta bara matcher som redan finns i Oddset."""
    return known_friendly(
        (event.get("homeTeam") or {}).get("name") or "",
        (event.get("awayTeam") or {}).get("name") or "",
        event.get("startTimestamp"), known)


def parse_capture(event: dict, stats_payload: Optional[dict], *,
                  captured_at: str,
                  now: Optional[dt.datetime] = None) -> dict:
    """Normalisera ett liveevent och dess kumulativa ALL-statistik."""
    now = now or dt.datetime.now(dt.timezone.utc)
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    tournament_id = unique.get("id")
    capture = {
        "event_id": int(event["id"]),
        "captured_at": captured_at,
        "capture_version": CAPTURE_VERSION,
        "league": TARGET_UT[int(tournament_id)],
        "tournament": unique.get("name") or tournament.get("name"),
        "home": (event.get("homeTeam") or {}).get("name") or "?",
        "away": (event.get("awayTeam") or {}).get("name") or "?",
        "start_at": _iso(event.get("startTimestamp")),
        "status": (event.get("status") or {}).get("description") or "Live",
        "minute": _minute(event, now),
        "home_score": _score(event, "home"),
        "away_score": _score(event, "away"),
    }
    parsed_stats = _all_stats(stats_payload or {})
    for source_key, (home_key, away_key) in STAT_KEYS.items():
        values = parsed_stats.get(source_key)
        capture[home_key] = values[0] if values else None
        capture[away_key] = values[1] if values else None
    return capture


def _num(row: dict, key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None else 0.0


def radar_signal(current: dict, previous: Optional[dict] = None) -> dict:
    """Härled en tydligt shadow-märkt radarflagga ur observerad statistik."""
    minute = current.get("minute")
    if minute is None:
        return {"level": "info", "kind": "no_clock", "score": 0.0,
                "reason": "Matchklockan saknas i källan."}
    if (current.get("home_score") is None or
            current.get("away_score") is None):
        return {"level": "info", "kind": "no_score", "score": 0.0,
                "remaining_min": max(0, 90 - int(minute)),
                "reason": "Ställningen saknas i källan; inget chansgap räknas."}
    remaining = max(0, 90 - int(minute))
    goals = [_num(current, "home_score"), _num(current, "away_score")]
    xg = [current.get("xg_home"), current.get("xg_away")]
    sides = ("home", "away")

    if all(value is not None for value in xg):
        xg_values = [float(value) for value in xg]
        gaps = [xg_values[i] - goals[i] for i in range(2)]
        index = 0 if gaps[0] >= gaps[1] else 1
        recent_xg = 0.0
        if previous and previous.get(f"xg_{sides[index]}") is not None:
            recent_xg = max(
                0.0, xg_values[index] -
                float(previous[f"xg_{sides[index]}"]))
        total_gap = sum(xg_values) - sum(goals)
        score = max(gaps[index], total_gap * 0.65) + recent_xg * 0.5
        active = (15 <= minute <= 78 and remaining >= 12 and
                  (gaps[index] >= 0.65 or total_gap >= 1.0))
        level = ("strong" if active and
                 (gaps[index] >= 1.15 or total_gap >= 1.65)
                 else "watch" if active else "info")
        team = current["home"] if index == 0 else current["away"]
        return {
            "level": level, "kind": "xg", "team": team,
            "side": sides[index], "score": round(score, 3),
            "chance_gap": round(gaps[index], 2),
            "total_gap": round(total_gap, 2),
            "recent_xg": round(recent_xg, 2),
            "remaining_min": remaining,
            "reason": (
                f"{team}: {xg_values[index]:.2f} xG men "
                f"{int(goals[index])} mål"
                + (f" · +{recent_xg:.2f} xG senaste {RECENT_MINUTES} min"
                   if recent_xg > 0 else "")),
        }

    proxy_keys = (
        "big_chances_home", "big_chances_away",
        "shots_on_home", "shots_on_away",
        "shots_inside_home", "shots_inside_away",
        "touches_box_home", "touches_box_away",
    )
    if all(current.get(key) is None for key in proxy_keys):
        # EN rad, inte två. "Källan saknar chansmått" + "därför räknas ingen
        # signal" sa samma sak dubbelt, och kortets statsrad visar redan
        # "xG saknas · stora chanser –––". Kvar blir det enda som INTE syns
        # ovanför: att detta är källans gräns, inte vår.
        return {
            "level": "info", "kind": "no_stats", "score": 0.0,
            "remaining_min": remaining,
            "reason": "Källan rapporterar inga skott- eller chansmått.",
        }

    # Allsvenskan saknar ofta xG. Proxyflaggan är medvetet strikt och märks
    # som observationssignal; Claudes 220-matcherstest gav inget stöd för att
    # rena skott förutsäger mål i nästa 15 minuter.
    proxy = []
    for side in sides:
        proxy.append(
            _num(current, f"big_chances_{side}") * 0.40
            + _num(current, f"shots_on_{side}") * 0.12
            + _num(current, f"shots_inside_{side}") * 0.025
            + _num(current, f"touches_box_{side}") * 0.008)
    gaps = [proxy[i] - goals[i] for i in range(2)]
    index = 0 if gaps[0] >= gaps[1] else 1
    side = sides[index]
    big = int(_num(current, f"big_chances_{side}"))
    on_target = int(_num(current, f"shots_on_{side}"))
    inside = int(_num(current, f"shots_inside_{side}"))
    active = (20 <= minute <= 78 and remaining >= 12 and
              (big - goals[index] >= 1.5 or
               (on_target - goals[index] >= 5 and inside >= 8)))
    team = current["home"] if index == 0 else current["away"]
    return {
        "level": "watch" if active else "info",
        "kind": "proxy", "team": team, "side": side,
        # EGET fältnamn: xG-varianten rapporterar `chance_gap` i MÅL. Proxyn
        # är ett enhetslöst index och får därför `proxy_index` — samma namn
        # för olika enheter inbjöd till felläsning.
        "score": round(gaps[index], 3),
        "proxy_index": round(gaps[index], 2),
        "remaining_min": remaining,
        # TEXTEN SKA MATCHA SIGNALEN (2026-07-25). "Trycker på" stod på varje
        # kort, även när nivån var FÖLJER — en match i 9:e minuten med ett skott
        # fick alltså en dramatisk mening om ingenting. Nu talar raden bara när
        # det finns ett utstick, och den namnger gapet i stället för att upprepa
        # statsraden. Ordet "proxy" är borta ur korttexten: det är vårt
        # internord, och att xG saknas står redan ovanför. Förbehållet om att
        # skottmåttet är oprövat hör i radarns fotnot, en gång.
        "reason": (
            f"{team}: {big} stora chanser, {on_target} skott på mål "
            f"men {int(goals[index])} mål"
            if active else
            f"{team} leder chansräkningen — inget utstick ännu"),
    }


def collect(store: Storage, *, now: Optional[dt.datetime] = None) -> dict:
    """Samla ett snapshot för alla pågående matcher i projektets ligor."""
    fixed_now = now
    now = now or dt.datetime.now(dt.timezone.utc)
    started = time.monotonic()
    # `captured_at` för varvet används bara till hälsorad och meta. VARJE
    # capture får sin EGEN observationstid längre ner — annars stämplas sista
    # matchen med loopens starttid. Samma fel som pit-v1 (förändringstid ≠
    # observationstid) och Pinnacles CDN-Age (hämtningstid ≠ pristid); det ska
    # inte återuppstå i varje ny insamlare.
    try:
        listing = _live_get("/sport/football/events/live")
        if (not isinstance(listing, dict) or "events" not in listing or
                not isinstance(listing["events"], list)):
            raise ValueError("Sofascores livefeed saknar events-lista")
        events = listing["events"]
    except Exception as exc:  # noqa: BLE001 — inget falskt slutbesked vid källfel
        checked_at = (fixed_now or dt.datetime.now(dt.timezone.utc)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        error = f"{type(exc).__name__}: {str(exc)[:80]}"
        store.oddset_record_source_health(
            "sofascore", "-", "live", checked_at, False, 0, error)
        return {"at": checked_at, "live": 0, "stats_ok": 0, "saved": 0,
                "skipped": 0, "error": error, "partial_errors": []}
    # Observationstid sätts EFTER rosteranropet. Ett explicit `now` används
    # bara av deterministiska tester/rekonstruktioner; driftvägen tar ny tid.
    roster_at = fixed_now or dt.datetime.now(dt.timezone.utc)
    captured_at = roster_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Spara hela football-rosterlistan, inte bara våra ligor. Då kan en ändrad
    # turneringsmappning aldrig misstolkas som att matchen tog slut. En
    # validerad tom `events`-lista är ett positivt slutbesked; en trasig feed
    # returnerar redan ovan utan att röra presence.
    record_presence(
        store, SOFA_PRESENCE_KEY,
        [item.get("id") for item in events
         if (item.get("status") or {}).get("type") == "inprogress"],
        captured_at)
    known = store.oddset_matches(
        (now - dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        (now + dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    known_friendlies = [
        match for match in known if match.get("league") == "friendlies"]
    scoped = []
    for event in events:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        if (unique.get("id") in TARGET_UT and
                (event.get("status") or {}).get("type") == "inprogress"):
            if unique.get("id") in FRIENDLY_UT and not _known_friendly(
                    event, known_friendlies):
                continue
            scoped.append(event)

    # Tak per varv: en lördagseftermiddag kan ge fler livematcher än vi hinner
    # med inom tickens fem minuter. Hellre ett ärligt redovisat urval än ett
    # varv som drar över och blockerar nästa poolinsamling.
    # URVALET är dock inte längre "de 14 Sofascore råkade lista först" (uppmätt
    # 2026-07-25: 43 behöriga träningsmatcher kunde tränga ut Allsvenskan).
    # Riktiga ligor först, därefter mest återstående speltid.
    known_empty = _known_empty_events(store, now)

    def _rank(event: dict) -> tuple:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        league = TARGET_UT.get(unique.get("id"), "friendlies")
        # 0 = har haft chansmått, 1 = ännu okänt (ny match — får inte straffas
        # för att den är tidig), 2 = bevisat tom efter EMPTY_AFTER_MIN.
        tier = known_empty.get(int(event["id"]), 1)
        return (tier, LEAGUE_PRIORITY.get(league, 9), _minute(event, now) or 0)

    scoped.sort(key=_rank)
    dropped_by_league: dict[str, int] = {}
    for event in scoped[MAX_MATCHES:]:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        league = TARGET_UT.get(unique.get("id"), "friendlies")
        dropped_by_league[league] = dropped_by_league.get(league, 0) + 1
    skipped = max(0, len(scoped) - MAX_MATCHES)
    scoped = scoped[:MAX_MATCHES]

    saved, stats_ok, errors = 0, 0, []
    budget_hit = False
    for event in scoped:
        if time.monotonic() - started > BUDGET_S:
            budget_hit = True
            skipped += 1
            continue
        stats = None
        try:
            stats = _live_get(f"/event/{event['id']}/statistics")
            stats_ok += 1
        except Exception as exc:  # noqa: BLE001 — coverage varierar per liga
            errors.append(f"{event['id']}: {type(exc).__name__}")
        # Observationstid per event, satt EFTER anropet.
        event_at = dt.datetime.now(dt.timezone.utc)
        capture = parse_capture(
            event, stats,
            captured_at=event_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now=event_at)
        saved += store.oddset_save_live_capture(capture)

    partial = "; ".join(errors[:5]) if errors else None
    if scoped and stats_ok == 0:
        partial = partial or "ingen live-match hade läsbar statistik"
    if skipped:
        # INGA TYSTA TAK: vad som föll bort, och ur vilken liga, ska stå i
        # källhälsan. Ett dolt urval läser som "det här var allt som fanns".
        detail = ", ".join(f"{league} {n}"
                           for league, n in sorted(dropped_by_league.items()))
        note = (f"{skipped} matcher hoppade"
                + (" (tidsbudget)" if budget_hit else " (matchtak)")
                + (f": {detail}" if detail else ""))
        partial = f"{partial}; {note}" if partial else note
    # `ok` betyder ett komplett rent varv. Tidigare räckte ett enda lyckat
    # statsanrop för grönt trots fel på resten; då doldes partialfelet i UI.
    health_ok = (not scoped or stats_ok > 0) and partial is None
    store.oddset_record_source_health(
        "sofascore", "-", "live", captured_at, health_ok, len(scoped), partial)
    store.meta_set("live_radar_last_run", captured_at)
    store.meta_set("live_radar_dropped", ", ".join(
        f"{league} {n} över taket"
        for league, n in sorted(dropped_by_league.items())))
    return {"at": captured_at, "live": len(scoped), "stats_ok": stats_ok,
            "saved": saved, "skipped": skipped, "health_ok": health_ok,
            "partial_errors": errors}


def previous_capture(earlier: list[dict],
                     current_at: dt.datetime) -> Optional[dict]:
    """Jämförelsepunkten ~RECENT_MINUTES före observationen, inom tolerans.

    DELAD av API-payloaden och settlementet (app/live_settlement.py): signalens
    15-minutersdelta ska väljas på exakt samma sätt var den än räknas — en
    andra implementation hade förr eller senare divergerat.
    """
    target = current_at - dt.timedelta(minutes=RECENT_MINUTES)
    candidate = min(
        earlier,
        key=lambda row: abs((
            dt.datetime.fromisoformat(
                row["captured_at"].replace("Z", "+00:00")) - target
        ).total_seconds()),
        default=None)
    if candidate is None:
        return None
    candidate_at = dt.datetime.fromisoformat(
        candidate["captured_at"].replace("Z", "+00:00"))
    if abs(candidate_at - target) > dt.timedelta(
            minutes=RECENT_TOLERANCE_MIN):
        return None
    return candidate


def _same_team(a: str, b: str) -> bool:
    """Konservativ namnlänkning mellan livekällorna.

    `norm_team` klarar 'Degerfors' ↔ 'Degerfors IF' men inte svensk genitiv:
    'Djurgården' ↔ 'Djurgårdens IF' blir djurgarden ↔ djurgardens. Prefixregeln
    med minst fyra tecken täcker det utan att öppna för allmän likhetsmatchning.
    Ingen träff = matchen visas utan FotMob-data; vi gissar aldrig.
    """
    def live_norm(value: str) -> str:
        normalized = norm_team(value or "")
        # Flashscore märker klubbar i globala träningsmatcher med landkod,
        # t.ex. `Chelsea (Eng)`. Det är providerpresentation, inte lagidentitet.
        tokens = [token for token in normalized.split()
                  if not (token.startswith("(") and token.endswith(")") and
                          2 <= len(token[1:-1]) <= 3 and
                          token[1:-1].isalpha())]
        return " ".join(tokens)

    x, y = live_norm(a), live_norm(b)
    x, y = LIVE_TEAM_ALIASES.get(x, x), LIVE_TEAM_ALIASES.get(y, y)
    # Bekräftat olika klubbar stoppas FÖRE all likhetslogik. Hellre två kort
    # än att två verkliga matcher smälter ihop.
    if frozenset({x, y}) in LIVE_TEAM_REJECTED:
        return False
    # Truppmarkörer är IDENTITET, inte föreningsform. Den gamla prefixregeln
    # gjorde t.ex. `Inter` och `Inter U23` till samma lag. Hellre två kort än
    # att statistik och ställning från skilda matcher blandas.
    squad_markers = {"b", "ii", "reserve", "reserves", "academy",
                     "youth", "women", "damer"}

    def qualifiers(value: str) -> set[str]:
        return {token for token in value.split()
                if token in squad_markers
                or (token.startswith("u") and token[1:].isdigit())}

    if qualifiers(x) != qualifiers(y):
        return False
    if len(x) < 4 or len(y) < 4:
        return x == y and bool(x)
    if x == y:
        return True
    # Svensk genitiv är det enda tillåtna enords-prefixet. Det bevarar
    # Djurgården↔Djurgårdens men stoppar Inter↔Inter Miami.
    if " " not in x or " " not in y:
        return x + "s" == y or y + "s" == x
    return x.startswith(y + " ") or y.startswith(x + " ")


def _start_at(row: dict) -> Optional[dt.datetime]:
    """Provideroberoende avspark; en live-länk kräver ett läsbart värde."""
    raw = row.get("start_at")
    if not raw:
        return None
    try:
        return _parse_iso(str(raw))
    except (TypeError, ValueError):
        return None


def _same_start(a: dict, b: dict) -> bool:
    """Avspark är en obligatorisk del av provideridentiteten."""
    left, right = _start_at(a), _start_at(b)
    return bool(left and right and abs(left - right) <= dt.timedelta(
        minutes=LINK_START_TOLERANCE_MIN))


def _fotmob_series(store: Storage, since: str) -> list[list[dict]]:
    """FotMob-captures grupperade per match, i tidsordning."""
    from .fotmob import CAPTURE_VERSION as FOTMOB_VERSION
    grouped: dict[int, list[dict]] = {}
    for row in store.live_fotmob_captures(since, FOTMOB_VERSION):
        grouped.setdefault(int(row["fotmob_id"]), []).append(row)
    return list(grouped.values())


def _flashscore_series(store: Storage, since: str) -> list[list[dict]]:
    """Flashscore-captures grupperade per match, i tidsordning."""
    from .flashscore import CAPTURE_VERSION as FS_VERSION
    grouped: dict[str, list[dict]] = {}
    for row in store.live_flashscore_captures(since, FS_VERSION):
        grouped.setdefault(str(row["flashscore_id"]), []).append(row)
    return list(grouped.values())


def _fotmob_for(match: dict, series: list[list[dict]],
                claimed: Optional[set[int]] = None) -> Optional[list[dict]]:
    """Hitta FotMob-serien för en Sofascore-match: samma liga, samma två lag.

    En provider-match får bara kopplas en gång. Om Sofascore råkar innehålla
    dubbletter blir den kvarvarande FotMob-serien i stället ett eget kort,
    aldrig statistik på två olika matcher.
    """
    candidates = []
    for captures in series:
        head = captures[-1]
        fotmob_id = int(head["fotmob_id"])
        if head.get("league") != match.get("league"):
            continue
        if (_same_start(head, match) and
                _same_team(head.get("home"), match.get("home")) and
                _same_team(head.get("away"), match.get("away"))):
            candidates.append(captures)
    # En unik kandidat krävs FÖRE claimed-filtret. Om två provider-events har
    # samma identitet får det första kortet aldrig godtyckligt "ta" den ena
    # och därmed göra den andra skenbart unik för nästa kort.
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if claimed is not None and int(candidate[-1]["fotmob_id"]) in claimed:
        return None
    return candidate


def _series_for(match: dict, series: list[list[dict]], id_key: str,
                claimed: set) -> Optional[list[dict]]:
    """Samma konservativa länkning som `_fotmob_for`, för valfri provider.

    Spegelvänd hemma/borta accepteras inte här: en länk som byter sida skulle
    göra lagens statistik omvänd. Ingen träff = matchen står på egna ben.
    """
    candidates = []
    for captures in series:
        head = captures[-1]
        key = str(head[id_key])
        if head.get("league") != match.get("league"):
            continue
        if (_same_start(head, match) and
                _same_team(head.get("home"), match.get("home")) and
                _same_team(head.get("away"), match.get("away"))):
            candidates.append(captures)
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    return None if str(candidate[-1][id_key]) in claimed else candidate


_FOTMOB_VIEW_KEYS = (
    "fotmob_id", "capture_version", "league", "tournament",
    "home", "away", "start_at", "home_score", "away_score",
    "xg_home", "xg_away", "xgot_home", "xgot_away",
    "big_chances_home", "big_chances_away",
    "shots_home", "shots_away",
    "shots_on_home", "shots_on_away",
    "shots_inside_home", "shots_inside_away",
    "minute", "captured_at",
)

_FLASHSCORE_VIEW_KEYS = (
    "flashscore_id", "capture_version", "league", "tournament",
    "home", "away", "start_at", "home_score", "away_score",
    "xg_home", "xg_away", "xgot_home", "xgot_away",
    "big_chances_home", "big_chances_away",
    "shots_home", "shots_away",
    "shots_on_home", "shots_on_away",
    "shots_inside_home", "shots_inside_away",
    "corners_home", "corners_away",
    "minute", "captured_at",
)


def _stats_rank(row: dict) -> tuple[int, int]:
    """Ranka fälttäckning, aldrig signalvärdet eller utfallet.

    Ett ensamt skottfält är inte likvärdigt med en komplett proxy. Den gamla
    `any(...)`-rankningen lät därför en partiell Flashscore-rad dölja en
    signalbar FotMob-rad. Nivåerna beskriver bara vilka par som finns:
    xG > komplett kärnproxy > komplett signalgren > partiell > inget.
    """
    if row.get("xg_home") is not None and row.get("xg_away") is not None:
        return (4, 0)

    def pair(name: str) -> bool:
        return (row.get(f"{name}_home") is not None and
                row.get(f"{name}_away") is not None)

    big = pair("big_chances")
    on_target = pair("shots_on")
    inside = pair("shots_inside")
    touches = pair("touches_box")
    complete_pairs = sum((big, on_target, inside, touches))
    if big and on_target and inside:
        return (3, complete_pairs)
    if big or (on_target and inside):
        return (2, complete_pairs)
    proxy_keys = ("big_chances_home", "big_chances_away",
                  "shots_on_home", "shots_on_away",
                  "shots_inside_home", "shots_inside_away",
                  "touches_box_home", "touches_box_away")
    reported = sum(row.get(key) is not None for key in proxy_keys)
    return (1, reported) if reported else (0, 0)


_SOURCE_PRIORITY = {"sofascore": 0, "fotmob": 1, "flashscore": 2}


def _best_source(candidates: list[tuple[str, list[dict]]]
                 ) -> tuple[str, list[dict]]:
    """Välj källa på schema/täckning + fast prioritet, aldrig på signalvärde."""
    return max(candidates, key=lambda item: (
        _stats_rank(item[1][-1]), _SOURCE_PRIORITY[item[0]]))


def _signal_with_basis(provider: str, captures: list[dict], view_keys,
                       match_fallback: Optional[dict] = None
                       ) -> tuple[dict, dict]:
    """Signal och exakt per-fält-proveniens ur en providerserie.

    Chansmåtten kommer alltid från `provider`. Bara saknad minut/ställning får
    lånas från den verifierade ankarraden, och UI:t får både det effektiva
    värdet och dess källa så att en fallback aldrig ser providerspecifik ut.
    """
    current = captures[-1]
    current_at = _parse_iso(current["captured_at"])
    previous = previous_capture(captures[:-1], current_at)
    signal_row = dict(current)
    basis = {}
    for key in ("minute", "home_score", "away_score"):
        value = current.get(key)
        source = provider
        if value is None and match_fallback is not None:
            value = match_fallback.get(key)
            if value is not None:
                source = "sofascore"
        signal_row[key] = value
        basis[key] = value
        basis[f"{key}_source"] = source if value is not None else None
    signal = radar_signal(signal_row, previous)
    signal["stats_source"] = provider
    signal["xg_source"] = provider if signal.get("kind") == "xg" else None
    signal["basis"] = basis
    view = {key: current.get(key) for key in view_keys}
    return signal, view


def _fotmob_signal(captures: list[dict],
                   match_fallback: Optional[dict] = None) -> tuple[dict, dict]:
    """Signal + visningsfält ur en enda, sammanhängande FotMob-serie."""
    return _signal_with_basis(
        "fotmob", captures, _FOTMOB_VIEW_KEYS, match_fallback)


def _flashscore_signal(captures: list[dict],
                       match_fallback: Optional[dict] = None
                       ) -> tuple[dict, dict]:
    """Signal + visningsfält ur en enda, sammanhängande Flashscore-serie.

    Samma kontrakt som FotMob-vägen: chansmåtten kommer UTESLUTANDE ur den
    egna serien, medan klocka/ställning får lånas per fält från den redan
    verifierade Sofascore-länken när Flashscores stadieklocka är okänd
    (halvtid, förlängning). Lånet påverkar aldrig xG eller skott.
    """
    return _signal_with_basis(
        "flashscore", captures, _FLASHSCORE_VIEW_KEYS, match_fallback)


def _sofascore_signal(captures: list[dict]) -> dict:
    """Sofascore-signal med samma explicita bas/proveniens som övriga."""
    signal, _view = _signal_with_basis(
        "sofascore", captures, tuple(captures[-1].keys()))
    return signal


def _fresh_series(captures: list[dict], now: dt.datetime) -> bool:
    """En länkbar serie måste vara lika färsk som ett fristående livekort."""
    if not captures:
        return False
    try:
        observed = _parse_iso(captures[-1]["captured_at"])
    except (KeyError, TypeError, ValueError):
        return False
    age = now - observed
    return (-dt.timedelta(minutes=1) <= age <=
            dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN))


def payload(store: Storage, *,
            now: Optional[dt.datetime] = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    # Läs även äldre historik för 15-minutersdeltat, men visa bara matcher vars
    # SENASTE observation är färsk. Annars försvinner jämförelsepunkten just
    # när den behövs eller en femminuterspunkt felmärks som "senaste 15 min".
    since = (now - dt.timedelta(
        minutes=MAX_DISPLAY_AGE_MIN + RECENT_MINUTES +
        RECENT_TOLERANCE_MIN)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = store.oddset_live_captures(since, CAPTURE_VERSION)
    fotmob_series = _fotmob_series(store, since)
    flashscore_series = _flashscore_series(store, since)
    sofa_ended = _recently_ended(store, SOFA_PRESENCE_KEY, now)
    fotmob_ended = _recently_ended(store, FOTMOB_PRESENCE_KEY, now)
    from .flashscore import PRESENCE_KEY as FS_PRESENCE_KEY
    flashscore_ended = _recently_ended(store, FS_PRESENCE_KEY, now)
    fotmob_series = [
        captures for captures in fotmob_series
        if not _ended_after_capture(
            captures[-1], "fotmob_id", fotmob_ended)]
    flashscore_series = [
        captures for captures in flashscore_series
        if not _ended_after_capture(
            captures[-1], "flashscore_id", flashscore_ended)]
    # Samma färskhetsgrind gäller INNAN providerlänkning. Förr kunde en
    # 30-minutersserie länkas till ett färskt Sofascore-kort och bära signalen,
    # trots att samma serie hade dolts som fristående kort.
    fotmob_series = [captures for captures in fotmob_series
                     if _fresh_series(captures, now)]
    flashscore_series = [captures for captures in flashscore_series
                         if _fresh_series(captures, now)]
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["event_id"]), []).append(row)
    matches = []
    claimed_fotmob: set[int] = set()
    claimed_flashscore: set[str] = set()
    for captures in grouped.values():
        current = captures[-1]
        if _ended_after_capture(current, "event_id", sofa_ended):
            continue
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        extra: dict = {}
        candidates = [("sofascore", captures)]
        fm = _fotmob_for(current, fotmob_series, claimed_fotmob)
        if fm:
            fm_current = fm[-1]
            claimed_fotmob.add(int(fm_current["fotmob_id"]))
            extra["fotmob"] = {
                key: fm_current.get(key) for key in _FOTMOB_VIEW_KEYS}
            candidates.append(("fotmob", fm))
        fs = _series_for(current, flashscore_series, "flashscore_id",
                         claimed_flashscore)
        if fs:
            fs_current = fs[-1]
            claimed_flashscore.add(str(fs_current["flashscore_id"]))
            extra["flashscore"] = {
                key: fs_current.get(key) for key in _FLASHSCORE_VIEW_KEYS}
            candidates.append(("flashscore", fs))

        # Valet görs enbart på rapporterad fälttäckning och fast källprioritet.
        # Signalen räknas FÖRST EFTER valet, så ett dramatiskt värde kan aldrig
        # få en sämre provider att vinna.
        source, chosen = _best_source(candidates)
        if source == "flashscore":
            signal, _ = _flashscore_signal(chosen, current)
        elif source == "fotmob":
            signal, _ = _fotmob_signal(chosen, current)
        else:
            signal = _sofascore_signal(chosen)
        matches.append({**current, **extra, "signal": signal,
                        "is_signal": signal["level"] in {"watch", "strong"}})

    # FotMob står på egna ben (och är sedan 2026-07-28 primär källa). Om
    # Sofascore helt saknar en match men FotMob har en färsk serie ska
    # matchen ändå synas.
    # Detta stänger den sista luckan i löftet "stats finns → kort visas".
    # Det namespacade event-id:t kan aldrig krocka med Sofascores heltals-id.
    for fm in fotmob_series:
        current = fm[-1]
        fotmob_id = int(current["fotmob_id"])
        if fotmob_id in claimed_fotmob:
            continue
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        signal, view = _fotmob_signal(fm)
        extra = {"fotmob": view}
        # Flashscore (primär) prövas även på FotMobs egna kort, med samma
        # kvalitetsregel: vinner vid lika, nedgraderar aldrig.
        fs = _series_for(current, flashscore_series, "flashscore_id",
                         claimed_flashscore)
        if fs:
            fs_current = fs[-1]
            claimed_flashscore.add(str(fs_current["flashscore_id"]))
            extra["flashscore"] = {
                key: fs_current.get(key) for key in _FLASHSCORE_VIEW_KEYS}
            source, chosen = _best_source(
                [("fotmob", fm), ("flashscore", fs)])
            if source == "flashscore":
                signal, _ = _flashscore_signal(chosen, current)
        matches.append({
            **current,
            "event_id": f"fotmob:{fotmob_id}",
            **extra,
            "signal": signal,
            "is_signal": signal["level"] in {"watch", "strong"},
        })

    # Flashscore står också på egna ben — och är sedan 2026-08-01 ofta den
    # ENDA källan med chansdata (Chelsea–Tottenham 2026-08-01: full xG hos
    # Flashscore, ingenting hos de andra två). En match som varken Sofascore
    # eller FotMob bär ska därför synas på Flashscores egen serie. Prefixet
    # gör id:t entydigt mot både Sofascores heltal och fotmob-nycklarna.
    for fs in flashscore_series:
        current = fs[-1]
        flashscore_id = str(current["flashscore_id"])
        if flashscore_id in claimed_flashscore:
            continue
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        signal, view = _flashscore_signal(fs)
        matches.append({
            **current,
            "event_id": f"flashscore:{flashscore_id}",
            "flashscore": view,
            "signal": signal,
            "is_signal": signal["level"] in {"watch", "strong"},
        })
    # SORTERING (2026-07-25): xG-signalen mäts i MÅL, proxyn är ett enhetslöst
    # viktat index — att ranka dem mot varandra på samma `score` jämför äpplen
    # med päron. Grupperna hålls därför isär: xG-matcher först, proxy under,
    # och sortering på score sker bara INOM en grupp.
    matches.sort(key=lambda row: (
        not row["is_signal"],
        0 if row["signal"]["level"] == "strong" else 1,
        0 if row["signal"].get("kind") == "xg" else 1,
        -float(row["signal"].get("score") or 0),
    ))
    # DÖLJ MATCHER UTAN MÄTBAR CHANSINFORMATION (Samans beslut 2026-07-25).
    # Skillnaden som gör detta säkert: `no_stats` sätts bara när ALLA
    # chansfält är None, dvs källan rapporterar dem inte alls. En match i
    # 4:e minuten med noll skott har värdet 0, inte None, och får en
    # proxysignal — den döljs alltså aldrig för att den är tidig.
    # Uppmätt: 0 av 56 träningsmatcher har xG och bara 4 har skott, så det här
    # är främst 50-talet försäsongsmatcher som bara rapporterar hörnor.
    # Captures fortsätter samlas — filtret gäller VISNINGEN, inte insamlingen,
    # så täckningsmätningar och framtida facit påverkas inte.
    hidden = [row for row in matches if row["signal"].get("kind") == "no_stats"]
    matches = [row for row in matches if row["signal"].get("kind") != "no_stats"]
    hidden_leagues: dict[str, int] = {}
    for row in hidden:
        league = row.get("league") or "?"
        hidden_leagues[league] = hidden_leagues.get(league, 0) + 1
    live_health = [row for row in store.oddset_source_health()
                   if row.get("scope") == "live" and
                   row.get("source") in {"flashscore", "fotmob", "sofascore"}]
    source_runs = {}
    for source in ("flashscore", "fotmob", "sofascore"):
        checked = [row.get("checked_at") for row in live_health
                   if row.get("source") == source and row.get("checked_at")]
        if checked:
            source_runs[source] = max(checked)
    # `last_run` betyder att hela källgruppen har kontrollerats, inte bara att
    # den sist körda Sofascore-loopen är färsk. Minsta av varje källas senaste
    # kontroll är den konservativa gemensamma vattenstämpeln.
    if len(source_runs) == 3:
        combined_last_run = min(source_runs.values())
    else:
        # En delkällas färska tid får inte se ut som att HELA radarn körts.
        # De enskilda tiderna finns kvar i source_runs; gemensam watermark
        # förblir okänd tills alla tre faktiskt har kontrollerats.
        combined_last_run = None
    return {
        "version": RADAR_VERSION,
        "mode": "shadow",
        "last_run": combined_last_run,
        "source_runs": source_runs,
        "source_health": live_health,
        "matches": matches,
        "signal_count": sum(row["is_signal"] for row in matches),
        # inga tysta filter: antalet dolda och ur vilka ligor redovisas
        "hidden_no_stats": len(hidden),
        "hidden_by_league": ", ".join(f"{lg} {n}" for lg, n
                                      in sorted(hidden_leagues.items())),
        "coverage": {
            "xg": sum(row["signal"]["kind"] == "xg" for row in matches),
            "proxy": sum(row["signal"]["kind"] == "proxy" for row in matches),
            "fotmob_xg": sum(row["signal"].get("xg_source") == "fotmob"
                             for row in matches),
            "flashscore_xg": sum(
                row["signal"].get("xg_source") == "flashscore"
                for row in matches),
            # vilken källa som faktiskt BÄR signalen, per provider
            "by_source": ", ".join(
                f"{src} {sum(1 for row in matches if row['signal'].get('stats_source') == src)}"
                for src in ("flashscore", "fotmob", "sofascore")),
        },
        # INGA TYSTA TAK: står här av samma skäl som i källhälsan — ett dolt
        # urval läser som "det här var allt som fanns live".
        "dropped": store.meta_get("live_radar_dropped") or "",
        "disclaimer": (
            "Informationsradar. Påverkar inte tips, Kelly, facit eller notiser."),
    }
