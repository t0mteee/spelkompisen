"""Flashscore — live-radarns PRIMÄRA statistikkälla (Samans beslut 2026-08-01).

Bakgrunden är mätt, inte antagen: 2026-08-01 hade Flashscore full xG för
matcher där FotMob bara hade skott (Hillerød–Esbjerg, FC Tokyo–Dortmund) eller
ingenting alls (Chelsea–Tottenham, kinesiska Jia League), och var aldrig sämre
i urvalet. Källan är därför primär — men urvalsregeln i `live_radar` rankar
fortfarande DATAKVALITET först (xG > skott > inget) och låter Flashscore vinna
vid LIKA. En match där FotMob har xG och Flashscore bara skott nedgraderas
alltså aldrig.

**Källgränsen** (CLAUDE.md): feeden svarar på publika konstanter — ett statiskt
headervärde ur sidans egen JavaScript, samma klass som Pinnacles gästnyckel som
gränsen uttryckligen tillåter. Ingen utmaning löses, ingen session/cookie/
WAF-token återspelas, ingen inloggning sker. Svaret är brotli-kodat, så
`brotli` i venv:et är ett HÅRT krav (transportregeln — utan paketet kommer
kroppen tillbaka som binärt skräp med status 200).

**Providerseparation (WP9a):** captures hamnar i en EGEN tabell och en
Flashscore-serie är självbärande — egen klocka, egen ställning, egna
chansmått. Rader från olika providrar blandas ALDRIG inom en serie.

Feedformatet är Flashscores egna pipe-separerade text: poster avdelas med
``~``, fält med ``¬`` och nyckel/värde med ``÷``. Formatet är odokumenterat och
kan ändras utan förvarning; parsern är därför defensiv och en tolkning som
misslyckas ger tom lista i stället för gissade värden.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

import httpx

BASE = "https://local-global.flashscore.ninja/2/x/feed"
# Frånvarande spelare ligger INTE i pipe-feeden utan i sidans egen publika
# GraphQL-väg med persisted query. Hashen är en statisk publik konstant,
# observerad i Flashscores egen nätverkstrafik 2026-08-01 (samma klass som
# `x-fsign` och Pinnacles gästnyckel — inom källgränsen, ingen utmaning löses).
GRAPHQL = "https://23.ds.lsapp.eu/pq_graphql"
ABSENCE_HASH = "dmpe2"
PROJECT_ID = 23
GRAPHQL_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
                   "Safari/537.36"),
    "Accept": "*/*",
    "Origin": "https://www.flashscore.se",
    "Referer": "https://www.flashscore.se/",
}
# Dagens matcher, fotboll (sport 1), dagoffset 0. Wire-storlek uppmätt
# 2026-08-01: 173 kB brotli-komprimerat (1,4 MB avkodat) — en begäran per
# varv, alltså ingen anledning att cachea och riskera en inaktuell ställning.
DAY_FEED = "f_1_0_{day}_se_1"
DAY_VARIANT = 3
STATS_FEED = "df_st_1_{match_id}"
# Statisk publik konstant ur sidans JS (se källgränsen i modulens docstring).
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
                   "Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
    "Referer": "https://www.flashscore.se/",
    "x-fsign": "SW9D1eZo",
}
TIMEOUT_S = 10.0
MAX_MATCHES = 60          # samma tak som FotMob-varvet
BUDGET_S = 45.0           # väggklocka; radarn får aldrig äta tickens budget
CAPTURE_VERSION = "flashscore-live-v2"
PRESENCE_KEY = "live_radar_flashscore_presence"
# Dagsfeeden bär klocka/ställning och statistikfeeden chansmåtten. Utan en
# separat DB-kolumn för metadataobservationen sparas bara par som observerats
# nära nog för att representera samma matchögonblick. Annars kan ett mål mellan
# anropen fabricera ett positivt chansgap.
MAX_SCORE_STATS_SKEW_S = 20

# Flashscores ligarubriker ("LAND: Namn") → projektets liganycklar. Explicit
# tabell, aldrig fuzzy (handbolls-läxan). Verifierade mot dagsfeeden
# 2026-08-01; cupnamnen är antagna tills ligafasen startar i september och
# ska verifieras mot feeden då — precis som FotMob-tabellens motsvarighet.
LEAGUE_NAMES = {
    "SWEDEN: Allsvenskan": "allsvenskan",
    "SWEDEN: Superettan": "superettan",
    "NORWAY: Eliteserien": "eliteserien",
    "NORWAY: OBOS-ligaen": "obosligaen",
    "ICELAND: Besta deild karla": "bestadeild",
    "ICELAND: Besta deild": "bestadeild",
    "USA: MLS": "mls",
    "ENGLAND: Premier League": "premier_league",
    "ITALY: Serie A": "serie_a",
    "SPAIN: LaLiga": "la_liga",
    "SPAIN: La Liga": "la_liga",
    "GERMANY: Bundesliga": "bundesliga",
    "WORLD: Club Friendly": "friendlies",
    "EUROPE: Champions League": "champions_league",
    "EUROPE: Champions League - Qualification": "champions_league",
    "EUROPE: Europa League": "europa_league",
    "EUROPE: Europa League - Qualification": "europa_league",
    "EUROPE: Conference League": "conference_league",
    "EUROPE: Conference League - Qualification": "conference_league",
}

# Flashscores statistiketiketter → våra kolumner. Bara kumulativa helmatchsmått.
STAT_NAMES = {
    "Expected goals (xG)": ("xg_home", "xg_away"),
    "xG on target (xGOT)": ("xgot_home", "xgot_away"),
    "Big chances": ("big_chances_home", "big_chances_away"),
    "Total shots": ("shots_home", "shots_away"),
    "Shots on target": ("shots_on_home", "shots_on_away"),
    "Shots inside the box": ("shots_inside_home", "shots_inside_away"),
    "Corner kicks": ("corners_home", "corners_away"),
}

# Matchstatus (AB) och spelstadium (AC) i feeden. Minuten HÄRLEDS ur stadiets
# starttid (AO) — validerat 2026-08-01 mot FotMobs klocka på sju samtidiga
# matcher (Chelsea 87′ exakt, Laos 69′, avvikelse ≤3 min i övriga). Endast de
# två kända stadierna härleds; halvtid och förlängning ger None, vilket är
# ärlig censur i stället för en gissad klocka.
STATUS_SCHEDULED = "1"
STATUS_LIVE = "2"
STATUS_FINISHED = "3"
STAGE_OFFSET = {"12": 0, "13": 45}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _observed_at(response: httpx.Response,
                 requested_at: dt.datetime) -> dt.datetime:
    """Observationstid = hämtningstid − HTTP Age (🕐-regeln, punkt 2)."""
    try:
        age = int(response.headers.get("age") or 0)
    except ValueError:
        age = 0
    return requested_at - dt.timedelta(seconds=max(0, age))


def _f(value) -> Optional[float]:
    """'1.76' → 1.76. '42%' och '85% (271/319)' är inga rena mått → None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or "%" in text or "(" in text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _records(text: str) -> list[dict]:
    """Feedens poster som ordnade nyckel/värde-uppslag."""
    out = []
    for chunk in text.split("~"):
        fields = {}
        for part in chunk.split("¬"):
            if "÷" in part:
                key, value = part.split("÷", 1)
                fields.setdefault(key, value)
        if fields:
            out.append(fields)
    return out


def parse_day_feed(text: str, status: str = STATUS_LIVE) -> list[dict]:
    """Matcher i VÅRA ligor ur dagsfeeden, filtrerade på status.

    Ligarubriken (ZA) gäller tills nästa rubrik — matchposter ärver den. En
    okänd rubrik nollställer ligan så att matcher aldrig ärver fel nyckel.
    """
    out: list[dict] = []
    league: Optional[str] = None
    tournament: Optional[str] = None
    for fields in _records(text):
        if "ZA" in fields:
            tournament = fields["ZA"]
            league = LEAGUE_NAMES.get(tournament)
            continue
        if "AA" not in fields or not league:
            continue
        if fields.get("AB") != status:
            continue
        out.append({
            "flashscore_id": fields["AA"],
            "league": league,
            "tournament": tournament,
            "home": fields.get("AE"),
            "away": fields.get("AF"),
            "start_ts": _int(fields.get("AD")),
            "stage": fields.get("AC"),
            "stage_started_ts": _int(fields.get("AO")),
            "home_score": _int(fields.get("AG")),
            "away_score": _int(fields.get("AH")),
        })
    return out


def _int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def minute_at(match: dict, observed_at: dt.datetime) -> Optional[int]:
    """Matchminut vid observationsögonblicket, härledd ur stadiets starttid.

    None när stadiet är okänt (halvtid, förlängning, avbrott) eller när
    stadieklockan saknas — radarn censurerar hellre än gissar.
    """
    offset = STAGE_OFFSET.get(str(match.get("stage")))
    started = match.get("stage_started_ts")
    if offset is None or not started:
        return None
    elapsed = (observed_at.timestamp() - started) / 60
    if elapsed < 0:
        return None
    return max(1, min(120, int(offset + elapsed)))


def parse_stats(text: str) -> dict:
    """Helmatchens kumulativa mått ur statistikfeeden.

    Feeden inleds med hela matchen (``SE÷Match``) och kan följas av
    halvleksavsnitt; endast det första avsnittet läses. Samma etikett
    förekommer i flera grupper (t.ex. xG under både *Top stats* och *Shots*) —
    första kompletta paret vinner, och en ofullständig rad skriver aldrig över.
    """
    out: dict[str, float] = {}
    seen_first_section = False
    for fields in _records(text):
        if "SE" in fields:
            if seen_first_section:
                break            # nästa period (halvlek) — sluta läsa
            seen_first_section = True
        mapping = STAT_NAMES.get((fields.get("SG") or "").strip())
        if not mapping:
            continue
        home, away = _f(fields.get("SH")), _f(fields.get("SI"))
        if home is None or away is None:
            continue
        for column, value in zip(mapping, (home, away)):
            out.setdefault(column, value)
    return out


class Flashscore:
    """Egen HTTP-väg — delas medvetet inte med någon spelbar pipeline."""

    def __init__(self, timeout: float = TIMEOUT_S):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS,
                                    follow_redirects=True)

    def __enter__(self) -> "Flashscore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str) -> tuple[str, dt.datetime]:
        requested_at = _now()
        response = self._client.get(f"{BASE}/{path}")
        response.raise_for_status()
        text = response.text
        # TRANSPORTREGELN: 200 med otolkbar kropp är ett transportfel (saknad
        # brotli-avkodning), aldrig ett tecken på att sidan ändrats.
        if text and "÷" not in text:
            raise ValueError(
                "otolkbar Flashscore-kropp — kontrollera brotli i venv:et "
                f"(content-encoding: {response.headers.get('content-encoding')})")
        return text, _observed_at(response, requested_at)

    def matches(self) -> tuple[list[dict], dt.datetime]:
        """Pågående matcher i våra ligor + listans observationstid."""
        text, observed_at = self._get(DAY_FEED.format(day=DAY_VARIANT))
        # En giltig tom roster innehåller fortfarande feedens globala SA-huvud.
        # ZA är bara en ligarubrik och kan finnas i ett avhugget svar; den får
        # därför aldrig ensam tolkas som "inga live" och tömma presence.
        if "SA÷" not in text:
            raise ValueError("Flashscores dagsfeed saknar strukturhuvud")
        return parse_day_feed(text), observed_at

    def day(self, offset: int, status: str) -> tuple[list[dict], dt.datetime]:
        """Matcher med given status för ett dygnsoffset (0 = i dag, −1 i går).

        Dagsfeeds når ~7–8 dygn bakåt (uppmätt 2026-08-01); längre bak finns
        säsongsfeeds, men de används medvetet INTE — historiska rader ska inte
        bakfyllas, bara samlas framåt.
        """
        text, observed_at = self._get(DAY_FEED.format(day=DAY_VARIANT)
                                      if offset == 0
                                      else f"f_1_{offset}_{DAY_VARIANT}_se_1")
        return parse_day_feed(text, status), observed_at

    def stats(self, match_id: str) -> tuple[dict, dt.datetime]:
        """Kumulativ helmatchsstatistik + dess EGNA observationstid."""
        text, observed_at = self._get(STATS_FEED.format(match_id=match_id))
        return parse_stats(text), observed_at

    def absences(self, match_id: str) -> tuple[list[dict], dt.datetime]:
        """Frånvarande spelare per sida + observationstid.

        Publik persisted query; svaret bär spelarnamn och orsak på svenska
        ("Ryggskada", "Gula kort"). Saknad lineup ⇒ tom lista, aldrig gissning.
        """
        requested_at = _now()
        response = self._client.get(
            GRAPHQL, params={"_hash": ABSENCE_HASH, "eventId": match_id,
                             "projectId": PROJECT_ID},
            headers=GRAPHQL_HEADERS)
        response.raise_for_status()
        payload = response.json()
        return (parse_absences(payload),
                _observed_at(response, requested_at))

    def absence_observation(self, match_id: str) -> tuple[dict, dt.datetime]:
        """Frånvaro med explicit tillgänglighetsstatus.

        En tom, publicerad ``missingPlayers``-lista betyder observerat noll.
        Saknad lineup betyder däremot ``unavailable`` och får aldrig skrivas
        som om källan bekräftat att ingen spelare saknas.
        """
        requested_at = _now()
        response = self._client.get(
            GRAPHQL, params={"_hash": ABSENCE_HASH, "eventId": match_id,
                             "projectId": PROJECT_ID},
            headers=GRAPHQL_HEADERS)
        response.raise_for_status()
        return (parse_absence_observation(response.json()),
                _observed_at(response, requested_at))


def parse_absences(payload: dict) -> list[dict]:
    """[{side, name, reason}] ur GraphQL-svaret. Okänd form ⇒ tom lista."""
    out: list[dict] = []
    event = ((payload or {}).get("data") or {}).get("findEventById") or {}
    for participant in event.get("eventParticipants") or []:
        side = ((participant.get("type") or {}).get("side") or "").lower()
        if side not in {"home", "away"}:
            continue
        for entry in ((participant.get("lineup") or {})
                      .get("missingPlayers") or []):
            player = entry.get("player") or {}
            name = player.get("name") or player.get("listName")
            if not name:
                continue
            out.append({"side": side, "name": name,
                        "reason": entry.get("reason"),
                        "player_id": player.get("participantId")})
    return out


def parse_absence_observation(payload: dict) -> dict:
    """Skilj ett giltigt tomt svar från ett ännu opublicerat svar."""
    event = ((payload or {}).get("data") or {}).get("findEventById")
    participants = ((event or {}).get("eventParticipants")
                    if isinstance(event, dict) else None)
    available = bool(participants) and any(
        isinstance(participant.get("lineup"), dict)
        for participant in participants
        if isinstance(participant, dict))
    return {
        "status": "observed" if available else "unavailable",
        "players": parse_absences(payload) if available else [],
    }


def _scope_friendlies(store, live: list[dict],
                      known_matches: Optional[list[dict]]) -> list[dict]:
    """Släpp bara in träningsmatcher som finns i Oddset — SAMMA delade spärr
    (inkl. spegelvänd hemma/borta) som Sofascore- och FotMob-varven, tillämpad
    FÖRE statistikanropen så att bortfiltrerade matcher inte kostar trafik."""
    from .live_radar import known_friendly
    if not any(m["league"] == "friendlies" for m in live):
        return live
    if known_matches is None:
        now = _now()
        known_matches = store.oddset_matches(
            _iso(now - dt.timedelta(hours=6)),
            _iso(now + dt.timedelta(hours=6)))
    friendlies = [m for m in known_matches if m.get("league") == "friendlies"]
    return [m for m in live
            if m["league"] != "friendlies"
            or known_friendly(m.get("home") or "", m.get("away") or "",
                              m.get("start_ts"), friendlies)]


def _rank(match: dict, observed_at: dt.datetime) -> tuple:
    """Riktiga ligor före friendlies, mest kvarvarande speltid först — taket
    ska klippa det som betyder minst (samma princip som övriga varv)."""
    from .live_radar import LEAGUE_PRIORITY
    return (LEAGUE_PRIORITY.get(match["league"], 9),
            minute_at(match, observed_at) or 0)


def collect(store, known_matches: Optional[list[dict]] = None) -> dict:
    """Ett radarvarv mot Flashscore — radarns primära statistikkälla.

    Sparar bara PÅGÅENDE matcher i våra ligor + Oddset-spärrade
    träningsmatcher, och bara när källan faktiskt rapporterar chansmått:
    ingen statistik = ingen rad, aldrig gissade nollor.
    """
    started_at = time.monotonic()
    saved = skipped = stats_ok = 0
    errors: list[str] = []
    with Flashscore() as api:
        try:
            live, listed_at = api.matches()
        except Exception as exc:                      # noqa: BLE001
            checked_at = _iso(_now())
            error = f"{type(exc).__name__}: {str(exc)[:80]}"
            store.oddset_record_source_health(
                "flashscore", "-", "live", checked_at, False, 0, error)
            return {"saved": 0, "skipped": 0, "live": 0,
                    "health_ok": False, "error": error}
        live = _scope_friendlies(store, live, known_matches)
        # Även en validerad TOM lista är ett positivt besked. Den måste få
        # markera tidigare aktiva matcher som slutade, annars hänger sista
        # Flashscore-kortet kvar hela TTL-fönstret.
        from .live_radar import record_presence
        record_presence(store, PRESENCE_KEY,
                        [m["flashscore_id"] for m in live],
                        _iso(listed_at))
        live.sort(key=lambda m: _rank(m, listed_at))
        live_by_id = {str(m["flashscore_id"]): m for m in live}
        for queued_match in live[:MAX_MATCHES]:
            match_id = str(queued_match["flashscore_id"])
            # En roster-refresh längre upp i samma varv ersätter metadata för
            # ALLA ännu ej behandlade matcher. En match som lämnat den färska
            # rostern ska inte sparas med sin gamla ställning.
            match = live_by_id.get(match_id)
            if match is None:
                continue
            if time.monotonic() - started_at > BUDGET_S:
                skipped += 1
                continue
            try:
                stats, observed_at = api.stats(match["flashscore_id"])
                stats_ok += 1
            except Exception as exc:                  # noqa: BLE001
                errors.append(f"{match['home']}: {type(exc).__name__}")
                continue
            if not stats:
                continue        # ingen statistik = ingen rad, aldrig nollor
            skew_s = abs((observed_at - listed_at).total_seconds())
            if skew_s > MAX_SCORE_STATS_SKEW_S:
                # Ett långt 60-matchersvarv ska inte offra de sena matcherna.
                # Förnya roster EN gång när vakten slår; den nyare ställningen
                # är dessutom konservativ mot en något äldre statrad (ett mål
                # kan minska gapet, aldrig fabricera ett positivt gap).
                try:
                    refreshed, refreshed_at = api.matches()
                    refreshed = _scope_friendlies(
                        store, refreshed, known_matches)
                    live_by_id = {
                        str(m["flashscore_id"]): m for m in refreshed}
                    record_presence(
                        store, PRESENCE_KEY,
                        [m["flashscore_id"] for m in refreshed],
                        _iso(refreshed_at))
                    refreshed_match = live_by_id.get(match_id)
                except Exception as exc:              # noqa: BLE001
                    refreshed_match = None
                    errors.append(
                        f"{match['home']}: roster-refresh {type(exc).__name__}")
                if refreshed_match is not None:
                    match, listed_at = refreshed_match, refreshed_at
                    skew_s = abs((observed_at - listed_at).total_seconds())
                if refreshed_match is None or skew_s > MAX_SCORE_STATS_SKEW_S:
                    errors.append(
                        f"{match['home']}: metadata {int(skew_s)} s från stats")
                    continue
            # Klocka/ställning och statistik kommer från två feedanrop. Bara
            # par inom konsistensvakten sparas och får då statistikens tid.
            store.live_flashscore_save({
                "flashscore_id": match["flashscore_id"],
                "captured_at": _iso(observed_at),
                "capture_version": CAPTURE_VERSION,
                "league": match["league"],
                "tournament": match["tournament"],
                "home": match["home"], "away": match["away"],
                "start_at": _iso(dt.datetime.fromtimestamp(
                    match["start_ts"], dt.timezone.utc))
                if match.get("start_ts") else None,
                "minute": minute_at(match, observed_at),
                "home_score": match.get("home_score"),
                "away_score": match.get("away_score"),
                **stats})
            saved += 1
        skipped += max(0, len(live) - MAX_MATCHES)
    checked_at = _iso(_now())
    health_error = "; ".join(errors[:5]) or None
    if live and stats_ok == 0:
        health_error = health_error or "ingen live-match hade läsbar statistik"
    if skipped:
        note = f"{skipped} matcher hoppade över (tidsbudget/matchtak)"
        health_error = f"{health_error}; {note}" if health_error else note
    # Grönt betyder att hela det behandlade varvet var rent. Ett enda lyckat
    # statsanrop får aldrig gömma att andra livematcher misslyckades.
    health_ok = (not live or stats_ok > 0) and health_error is None
    store.oddset_record_source_health(
        "flashscore", "-", "live", checked_at, health_ok, len(live),
        health_error)
    store.meta_set("live_radar_flashscore_last_run", checked_at)
    return {"saved": saved, "skipped": skipped, "live": len(live),
            "stats_ok": stats_ok, "health_ok": health_ok,
            "partial_errors": errors}
