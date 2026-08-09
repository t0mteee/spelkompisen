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
# v4 (2026-08-02): ställningen räddas ur per-match-feeden `df_sur` när
# dagsfeeden är CDN-gammal; minuten censureras vid stadiebyte i stället för
# att ticka vidare i fel stadium. v3 slopade hela klockan; v2 kastade raden.
CAPTURE_VERSION = "flashscore-live-v4"
PRESENCE_KEY = "live_radar_flashscore_presence"
# Dagsfeeden bär klocka/ställning och statistikfeeden chansmåtten. Utan en
# separat DB-kolumn för metadataobservationen sparas bara par som observerats
# nära nog för att representera samma matchögonblick.
#
# VAKTEN ÄR RIKTAD (2026-08-02). De två feedarna är CDN-cachade oberoende av
# varandra — uppmätt låg dagsfeeden 51 s bak medan statobjekten låg 3–235 s
# bak. Att mäta |skillnaden| gjorde då cachejitter till samma sak som verklig
# inkoherens, och kastade 29 av 69 varv. Riktningen är inte symmetrisk:
#
#   stats NYARE än ställningen  → ställningen är gammal. Ett mål kan ha gjorts
#                                 som ställningen inte visar, vilket FABRICERAR
#                                 "hög xG men inget mål". Farligt: 20 s.
#   ställningen NYARE än stats  → ett mål i den nyare ställningen kan bara
#                                 krympa chansgapet, aldrig skapa ett. Redan
#                                 kodens eget resonemang; konservativt: 180 s.
#
# Nedströms gäller ändå `live_radar.MAX_DISPLAY_AGE_MIN`, så en gammal men
# konservativ rad kan inte visas som färsk.
MAX_SCORE_STATS_SKEW_S = 20        # stats nyare än ställning (farlig riktning)
MAX_STALE_STATS_SKEW_S = 180       # ställning nyare än stats (konservativ)


def skew_rejected(skew_s: float) -> bool:
    """Sant när stats/ställning ligger för långt isär åt sitt håll.

    ``skew_s`` är TECKNAT: positivt = statistiken observerades efter
    ställningen.
    """
    return skew_s > MAX_SCORE_STATS_SKEW_S or skew_s < -MAX_STALE_STATS_SKEW_S

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
    # Verifierade mot Flashscores dagsfeed 2026-08-09.
    "DENMARK: Superliga": "danish_superliga",
    "BELGIUM: Jupiler Pro League": "belgian_pro_league",
    "PORTUGAL: Liga Portugal": "primeira_liga",
    "BOLIVIA: Division Profesional": "bolivian_primera",
    "WORLD: Club Friendly": "friendlies",
    "EUROPE: Champions League": "champions_league",
    "EUROPE: Champions League - Qualification": "champions_league",
    "EUROPE: Europa League": "europa_league",
    "EUROPE: Europa League - Qualification": "europa_league",
    "EUROPE: Conference League": "conference_league",
    "EUROPE: Conference League - Qualification": "conference_league",
}

# Flashscores statistiketiketter → våra kolumner. Bara kumulativa helmatchsmått.
# Uppmätt 2026-08-06 över 12 samtidiga livematcher: feeden levererar två
# helt olika paket. 8 av 12 (europacupkval) bar bara baspaketet — possession,
# skott, skott på mål/utanför, blockerade, hörnor, offside, fouls — medan 2 av
# 12 bar det fulla paketet med xG, xGOT, stora chanser och skott i boxen.
# Skillnaden ligger hos providern, inte hos oss; parsern läser det som finns.
#
# Raderna nedanför `Corner kicks` fanns i VARJE matchs feed men lästes aldrig.
# `touches_box` är den dyraste av dem: den ingick redan i radarns
# täckningsrankning (`_stats_rank`), så rankningen räknade på ett fält ingen
# källa kunde fylla.
STAT_NAMES = {
    "Expected goals (xG)": ("xg_home", "xg_away"),
    "xG on target (xGOT)": ("xgot_home", "xgot_away"),
    "Big chances": ("big_chances_home", "big_chances_away"),
    "Total shots": ("shots_home", "shots_away"),
    "Shots on target": ("shots_on_home", "shots_on_away"),
    "Shots inside the box": ("shots_inside_home", "shots_inside_away"),
    "Corner kicks": ("corners_home", "corners_away"),
    "Shots off target": ("shots_off_home", "shots_off_away"),
    "Blocked shots": ("shots_blocked_home", "shots_blocked_away"),
    "Touches in opposition box": ("touches_box_home", "touches_box_away"),
    "Goalkeeper saves": ("saves_home", "saves_away"),
    "Ball possession": ("possession_home", "possession_away"),
}
# Etiketter vars värde är en andel i procent ('54%'), inte ett antal.
PERCENT_STATS = frozenset({"Ball possession"})

# Matchstatus (AB) och spelstadium (AC) i feeden. Minuten HÄRLEDS ur stadiets
# starttid (AO) — validerat 2026-08-01 mot FotMobs klocka på sju samtidiga
# matcher (Chelsea 87′ exakt, Laos 69′, avvikelse ≤3 min i övriga). Endast de
# två kända stadierna härleds; halvtid och förlängning ger None, vilket är
# ärlig censur i stället för en gissad klocka.
STATUS_SCHEDULED = "1"
STATUS_LIVE = "2"
STATUS_FINISHED = "3"
STAGE_OFFSET = {"12": 0, "13": 45}
# Stadier där klockan STÅR STILLA men den spelade tiden är känd exakt.
# Halvtidspaus inträffar per definition efter 45 spelade minuter — det är
# inte en gissning, och att censurera minuten där kostade signalen: en match
# med 1,4 xG och 0 mål föll ur "starkt chansgap" i det ögonblick domaren blåste
# av, för att `radar_signal` returnerar `no_clock` utan minut. Gapet finns
# kvar i pausen; det är just då det är intressant.
# Minuten TICKAR INTE här — pausens längd får aldrig läggas på spelad tid.
#
# Etikett och minut bor i SAMMA tabell med flit. UI:t visar etiketten i
# klockans ställe just när klockan står stilla, så två skilda tabeller hade
# kunnat glida isär till ett kort som säger "45′" om en match i paus (eller
# "Paus" om en match där klockan går). `38` är driftmätt 2026-08-06 på sex
# samtidiga matcher: stadiet började 45–50 min efter avspark, båda källorna
# slutade rapportera minut, och matcherna gick vidare till `13`.
STAGE_FROZEN = {"38": ("Paus", 45)}
STAGE_FROZEN_MINUTE = {code: minute for code, (_, minute) in STAGE_FROZEN.items()}
# Etikett att visa I KLOCKANS STÄLLE — alltså bara för stadier där klockan
# står stilla. Under `12`/`13` går klockan och minuten är sannare än ordet
# "1:a halvlek", så de har med flit ingen etikett här.
STAGE_LABEL = {code: label for code, (label, _) in STAGE_FROZEN.items()}

# Beskrivande namn för ALLA kända stadier. Används bara som RESERV när
# minuten saknas — aldrig i stället för en minut som finns.
#
# Behovet: koherensvakten nollställer `stage_started_ts` när `df_sur` visar
# ett annat stadium än dagsfeeden, och då kan minuten inte härledas. Vi vet
# ändå VAR matchen är, och "2:a halvlek" är oändligt mycket mer användbart än
# ett tomt fält — Samans krav 2026-08-06: matchminuten ska aldrig bara saknas.
STAGE_NAME = {"12": "1:a halvlek", "13": "2:a halvlek",
              **{code: label for code, (label, _) in STAGE_FROZEN.items()}}


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


def _share(value) -> Optional[float]:
    """'54%' → 54.0, för de mått som ÄR en andel.

    Skild från `_f` med flit: den avvisar procent därför att de flesta
    procenttal i feeden är härledda kvoter med råa tal i parentes
    ('85% (271/319)'), där andelen inte är måttet. Bollinnehav har ingen
    parentes och är en direkt observation — men bara etiketter i
    `PERCENT_STATS` läses så här, aldrig procent i allmänhet.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text.endswith("%") or "(" in text:
        return None
    try:
        return float(text[:-1].strip().replace(",", "."))
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
    """SPELAD tid vid observationsögonblicket, härledd ur stadiet.

    Två fall, och skillnaden mellan dem är hela poängen:

    * Stadier där klockan går (`STAGE_OFFSET`) — minuten räknas ur stadiets
      starttid.
    * Stadier där klockan står stilla men spelad tid ÄNDÅ är känd
      (`STAGE_FROZEN_MINUTE`, i dag halvtidspaus = 45). Pausens längd läggs
      aldrig på: minuten fryses.

    None bara när stadiet är genuint okänt eller stadieklockan saknas —
    radarn censurerar hellre än gissar. Att censurera i PAUS var däremot fel:
    signalen dog just när chansgapet var som mest intressant.
    """
    stage = str(match.get("stage"))
    frozen = STAGE_FROZEN_MINUTE.get(stage)
    if frozen is not None:
        return frozen
    offset = STAGE_OFFSET.get(stage)
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
        label = (fields.get("SG") or "").strip()
        mapping = STAT_NAMES.get(label)
        if not mapping:
            continue
        read = _share if label in PERCENT_STATS else _f
        home, away = read(fields.get("SH")), read(fields.get("SI"))
        if home is None or away is None:
            continue
        for column, value in zip(mapping, (home, away)):
            out.setdefault(column, value)
    return out


SUMMARY_FEED = "df_sur_1_{match_id}"


def parse_summary(text: str) -> Optional[dict]:
    """Färsk ställning + stadium ur per-match-sammanfattningen (`df_sur`).

    Dagsfeeden är CDN-fryst uppåt två minuter medan `df_sur` är sekundfärsk.
    Fältregeln verifierades i drift 2026-08-02 mot 19 samtidiga livematcher,
    inklusive det diskriminerande andrahalvleksfallet Cappellen–Lierse 0–6
    (`BA/BB`=(0,2) + `BC/BD`=(0,4)):

    * ``BA/BB`` = första halvlekens mål, ``BC/BD`` = andra halvlekens;
      löpande ställning är summan. I andra halvlek är BC/BD alltid med, även
      vid 0–0 — så en saknad BC/BD betyder första halvlek, inte noll.
    * ``AT/AU`` = löpande ställning i matcher utan halvleksuppdelning
      (observerat i träningsmatch med stadiekod 2).
    * ``AC`` = stadiekod, samma taxonomi som dagsfeedens ``stage``.

    Okänd struktur ⇒ None — en gissad ställning kan fabricera en signal.
    """
    records = _records(text)
    if not records:
        return None
    # `BC/BD` ligger i en EGEN post efter `~` (observerat: `...BA÷2¬BB÷0¬~BC÷0
    # ¬BD÷0¬~...`), så huvudfälten samlas över alla poster med första
    # förekomsten som vinnare — samma regel som `_records` använder inom en post.
    head: dict[str, str] = {}
    for fields in records:
        for key, value in fields.items():
            head.setdefault(key, value)
    stage = head.get("AC")
    p1 = (_i(head.get("BA")), _i(head.get("BB")))
    p2 = (_i(head.get("BC")), _i(head.get("BD")))
    total = (_i(head.get("AT")), _i(head.get("AU")))
    if None not in p1 and None not in p2:
        score = (p1[0] + p2[0], p1[1] + p2[1])
    elif None not in p1:
        score = p1
    elif None not in total:
        score = total
    else:
        return None
    return {"home_score": score[0], "away_score": score[1], "stage": stage}


def _i(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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

    def summary(self, match_id: str) -> tuple[Optional[dict], dt.datetime]:
        """Färsk ställning/stadium ur `df_sur` + dess egen observationstid."""
        text, observed_at = self._get(SUMMARY_FEED.format(match_id=match_id))
        return parse_summary(text), observed_at

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
            clock_ok = True
            skew_s = (observed_at - listed_at).total_seconds()
            if skew_rejected(skew_s):
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
                    skew_s = (observed_at - listed_at).total_seconds()
                if refreshed_match is None or skew_rejected(skew_s):
                    if skew_s < 0:
                        # Statistiken själv är för gammal — inget att rädda.
                        errors.append(
                            f"{match['home']}: stats {int(-skew_s)} s äldre "
                            "än ställningen")
                        continue
                    # Ställningen i dagsfeeden är gammal men STATISTIKEN är
                    # färsk. Rädda ställningen ur per-match-feeden `df_sur`
                    # (sekundfärsk, verifierad fältregel 2026-08-02) i stället
                    # för att slopa den — olänkade kort visade annars
                    # "resultat saknas" på matcher Flashscore bevisligen har.
                    clock_ok = False
                    try:
                        fresh, fresh_at = api.summary(match["flashscore_id"])
                    except Exception as exc:              # noqa: BLE001
                        fresh, fresh_at = None, None
                        errors.append(
                            f"{match['home']}: summary {type(exc).__name__}")
                    # SAMMA riktade vakt som mot dagsfeeden: positiv skew =
                    # statistiken nyare än summary-ställningen = ett osett mål
                    # kan fabricera gapet (20 s). Negativ = summaryn nyare än
                    # statistiken = ett mål kan bara krympa gapet (180 s). En
                    # symmetrisk vakt här föll på CDN-jitter åt det ofarliga
                    # hållet (Egersund/Kongsvinger 2026-08-02).
                    sur_skew = ((observed_at - fresh_at).total_seconds()
                                if fresh_at is not None else None)
                    if fresh is not None and sur_skew is not None \
                            and not skew_rejected(sur_skew):
                        match = {**match,
                                 "home_score": fresh["home_score"],
                                 "away_score": fresh["away_score"]}
                        if fresh.get("stage") != str(match.get("stage")):
                            # Stadiet har bytt sedan dagsfeeden frös (t.ex.
                            # halvtid). Ny starttid saknas ⇒ minuten censureras
                            # hellre än tickar vidare i fel stadium.
                            match = {**match, "stage": fresh.get("stage"),
                                     "stage_started_ts": None}
                        clock_ok = True
                    else:
                        errors.append(
                            f"{match['home']}: klocka slopad (ställningen "
                            f"{int(skew_s)} s äldre än stats, summary "
                            f"{'saknas' if fresh is None else 'för gammal'})")
            # Klocka/ställning och statistik kommer från två feedanrop. Statens
            # tid gäller alltid; klockan följer bara med när den är koherent.
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
                # MINUTEN överlever alltid. Den härleds ur stadiets STARTTID,
                # ett statiskt värde som inte ruttnar med feedens cacheålder —
                # bara ställningen gör det. Att slopa båda var en överkorrigering
                # som dolde matchminuten i onödan (Samans iakttagelse
                # 2026-08-02). Enda felkällan är ett stadiebyte inom
                # cachefönstret, vilket ger några minuters fel i visningen — inte
                # en fabricerad signal.
                "minute": minute_at(match, observed_at),
                # Stadiet är en OBSERVATION, inte en härledning: det säger
                # varför minuten kan saknas (paus) utan att fabricera en.
                # `stage_label` visas i klockans ställe (fryst klocka),
                # `stage_name` bara som reserv när minuten saknas helt.
                "stage_label": STAGE_LABEL.get(str(match.get("stage"))),
                "stage_name": STAGE_NAME.get(str(match.get("stage"))),
                "home_score": match.get("home_score") if clock_ok else None,
                "away_score": match.get("away_score") if clock_ok else None,
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
