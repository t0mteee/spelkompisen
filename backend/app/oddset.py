"""Oddset-delen: enskilda matcher per liga — sharp (Pinnacle) vs Svenska Spel (Kambi).

Insamlingen hämtar per liga Pinnacles matchups + raka marknader (1X2/AH/ÖU, huvudlina)
och Kambis listView + betoffer, matchar ihop källorna på normaliserat klubbnamn +
avsparkstid och sparar odds-snapshots med dedup (skriv bara vid förändring).

Liga-id:n och Kambi-vägar verifierade 2026-07-12 (docs/plan.md, "Prober").
"""
from __future__ import annotations

import datetime as dt
import functools
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from . import kambi
from . import oddset_value
from .derive import derive_1x2
from .pinnacle import Pinnacle, american_to_decimal, cache_adjusted_iso
from .storage import Storage

LEAGUES = [
    {"key": "allsvenskan", "name": "Allsvenskan", "pin_id": 1728,
     "kambi": "football/sweden/allsvenskan", "altenar": 3537},
    {"key": "superettan", "name": "Superettan", "pin_id": 2476,
     "kambi": "football/sweden/superettan", "altenar": 4825},
    {"key": "eliteserien", "name": "Eliteserien", "pin_id": 2333,
     "kambi": "football/norway/eliteserien", "altenar": 3458},
    {"key": "obosligaen", "name": "OBOS-ligaen", "pin_id": 2331,
     "kambi": "football/norway/obos-ligaen", "altenar": None},
    # Besta deild (2026-07-27, Samans beställning). Recon: Pinnacle 2102
    # ("Iceland - Premier League", 22 matchups), Kambi kör GAMLA namnet
    # urvalsdeild (besta_deildin = 404), Ninja/Altenar saknar ligan.
    # Sofascore ut 188 är VERIFIERAD (fotboll) men medvetet INTE inlagd i
    # SOFA_UT: den ingår i wp9c-POLICY-fingeravtrycket och hade fraktuerat
    # V2.2-manifestet — xG/frånvaro/WP9c för Island kopplas vid nästa
    # naturliga omfrysning. Ingen modell (ingen football-data) — ren
    # sharp-ankrad väg; facitgruppen är ny och utforskande (BH-FDR) tills
    # egen volym finns. Smarkets/Matchbook omappade tills slug observerats.
    {"key": "bestadeild", "name": "Besta deild", "pin_id": 2102,
     "kambi": "football/iceland/urvalsdeild", "altenar": None},
    {"key": "mls", "name": "MLS", "pin_id": 2663,
     "kambi": "football/usa/mls", "altenar": None},
    {"key": "friendlies", "name": "Träningsmatcher", "pin_id": 1863,
     "kambi": "football/club_friendly_matches", "altenar": None},
    # Europacuperna (Samans beställning 2026-07-28): CL/EL/Conference INKL.
    # kval. Varje cup är TVÅ ligor hos Pinnacle och TVÅ vägar hos Kambi
    # (huvudturnering + kval) — `pin_ids`/`kambi_paths` listar båda och slås
    # ihop i collect (_pin_ids/_kambi_paths). Kambis huvudvägar finns redan
    # men är tomma tills ligafasen startar i september; kvalvägarna bär
    # matcherna nu (verifierat 28/7: 12+9+46 kvalmatcher med odds).
    # Sharp-ankrad väg som Besta deild: ingen modell (ingen football-data),
    # och Sofascore-UT medvetet INTE i SOFA_UT (wp9c-POLICY-fingeravtrycket) —
    # live-radarn scope:ar cuperna direkt i TARGET_UT i stället.
    {"key": "champions_league", "name": "Champions League",
     "pin_ids": [2627, 205451],
     "kambi_paths": ["football/champions_league",
                     "football/champions_league_qualification"],
     "altenar": None},
    {"key": "europa_league", "name": "Europa League",
     "pin_ids": [2630, 2632],
     "kambi_paths": ["football/europa_league",
                     "football/europa_league_qualification"],
     "altenar": None},
    {"key": "conference_league", "name": "Conference League",
     "pin_ids": [214101, 271382],
     "kambi_paths": ["football/conference_league",
                     "football/conference_league_qualification"],
     "altenar": None},
    # De fyra stora Europaligorna. FULLT FÖLJDA sedan 2026-08-07 (Samans
    # beslut inför säsongsstarten): sidoböcker, deep-marknader, värdesignaler,
    # CLV och notiser — precis som Allsvenskan.
    #
    # De var `research_only` fram till dess, vilket spärrade sidoböcker och
    # actionability medan V2.2-experimentet ägde modellspåret. Spärren behövdes
    # aldrig för SHARP-tiern: den är ren oddsjämförelse (Pinnacle mot bok) och
    # har inget med V2.2:s modellhypotes att göra. V2.2 kör vidare oförändrad
    # på sin EGEN `SCOPE_LEAGUES` och sitt eget manifest — capturen berörs inte.
    #
    # OBSERVERA att de saknar xG i resultathistoriken (0 av 2 897 matcher), så
    # de ligger med flit UTANFÖR `MODEL_LEAGUES`: en xG-viktad modell utan xG
    # vore sämre än ingen. xG samlas framåt via flashscore_data och bakfylls
    # aldrig.
    {"key": "premier_league", "name": "Premier League", "pin_id": 1980,
     "kambi": "football/england/premier_league", "altenar": None,},
    # Championship (2026-09-02, Samans beställning). Tidigare fanns ligan
    # bara som football-data-matarliga till V2.2 och kunde därför varken
    # visas i Oddset eller länka liveradarns statistik till ett prematchpris.
    # Alla tre identiteter är avlästa ur källornas aktuella egna svar:
    # Pinnacle `England - Championship` 1977, Kambi-vägen nedan (16 event)
    # och Ninja/Altenar 2937 (engelska lag; 2962 är Skottland).
    {"key": "championship", "name": "Championship", "pin_id": 1977,
     "kambi": "football/england/the_championship", "altenar": 2937},
    {"key": "serie_a", "name": "Serie A", "pin_id": 2436,
     "kambi": "football/italy/serie_a", "altenar": None,},
    {"key": "la_liga", "name": "La Liga", "pin_id": 2196,
     "kambi": "football/spain/la_liga", "altenar": None,},
    {"key": "bundesliga", "name": "Bundesliga", "pin_id": 1842,
     "kambi": "football/germany/bundesliga", "altenar": None,},
    # Tre nya toppligor (2026-08-09, Samans beställning). Pinnacle-id och
    # Kambi-vägar är verifierade mot aktuellt utbud, inte mönsterhärledda.
    # De är fullt synliga/actionable för ren sharp-värdering men står utanför
    # MODEL_LEAGUES tills egen xG-/closehistorik har mätts och kalibrerats.
    {"key": "danish_superliga", "name": "Danska Superliga", "pin_id": 1913,
     "kambi": "football/denmark/superligaen", "altenar": None},
    {"key": "belgian_pro_league", "name": "Belgiska Pro League", "pin_id": 1817,
     "kambi": "football/belgium/jupiler_pro_league", "altenar": None},
    {"key": "primeira_liga", "name": "Primeira Liga", "pin_id": 2386,
     "kambi": "football/portugal/primeira_liga", "altenar": None},
    # Bolivia (2026-08-09). Pinnacle, Sofascore, Flashscore, FotMob och
    # Smarkets är verifierade mot aktuella event. Kambi har ingen egen
    # ligaväg i nuvarande index men den giltiga landsvägen gör att ett
    # eventuellt SvS-utbud fångas utan att ett 404 gör ligainsamlingen röd.
    # Sharp/actionable som ligorna ovan, men ingen målmodell innan egen
    # xG-/closehistorik finns.
    {"key": "bolivian_primera", "name": "Bolivianska Primera División",
     "pin_id": 5595, "kambi": "football/bolivia", "altenar": None},
    # Ligue 1 (2026-08-21, Samans beställning). Alla källor verifierade mot
    # aktuellt utbud, inte mönsterhärledda: Pinnacle `France - Ligue 1` id
    # 2036 (420 matchups), Kambi `football/france/ligue_1` (9 event med 1X2
    # hos Svenska Spel), Sofascore unique-tournament 34, football-data `F1`
    # (306 rader/säsong = 18 lag × 34 omgångar).
    #
    # Ligue 2 samlas som RESULTATLIGA via football-data `F2`, precis som
    # Segunda/Serie B/2. Bundesliga — den ligger utanför `LEAGUES` eftersom
    # vi inte handlar på den. Championship var tidigare likadan men är fullt
    # följd sedan 2026-09-02. Ligue 1 poolas INTE med Ligue 2:
    # uppmätt försämrar matarligepoolning modellen i alla fyra Europaligor
    # (+0,0036 till +0,0125 logloss), och Ligue 2 saknar dessutom xG.
    {"key": "ligue_1", "name": "Ligue 1", "pin_id": 2036,
     "kambi": "football/france/ligue_1", "altenar": None},
]
# Actionable = får skapa spelbar signal, Kelly, notis och CLV-/value_log-rader.
ACTIONABLE_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES if not league.get("research_only"))


def _pin_ids(league: dict) -> list[int]:
    """Pinnacle-id:n för en liga. Cuperna listar huvudturnering + kval i
    `pin_ids`; vanliga ligor har ett enda `pin_id`."""
    return league.get("pin_ids") or [league["pin_id"]]


def _kambi_paths(league: dict) -> list[str]:
    """Kambi-vägar för en liga — samma mönster som _pin_ids."""
    return league.get("kambi_paths") or [league["kambi"]]
# Synlig i ordinarie UI-payload (/api/oddset/matches utan interna flaggor).
VISIBLE_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES
    if not league.get("research_only") or league.get("visible_in_ui"))
RESEARCH_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES if league.get("research_only"))

# Fler böcker (jämförelse + hitta boken som hänger efter). Kambi-operatörer delar
# event-id:n med svenskaspel (trivial matchning); Altenar-böcker matchas fuzzy på
# namn+avspark. Kambi-sidoboken hämtar bara 1X2; Altenars listvy ger dessutom
# Ö/U och eventdetaljen ger totalhörnor i deep-/snabbfönstret.
# Expekt kör Kambi via LeoVegas-avtalet (verifierat: Kambi-pressrelease, t.o.m. 2027).
BOOKS = [
    {"key": "expekt", "name": "Expekt", "kambi_op": "expektse"},
    # Altenar är EN prisfeed med olika marginalpåslag per skin. Kartläggningen
    # 2026-07-24 (docs/bookmakers-kartlaggning-2026-07-24.md) mätte elva skins;
    # `betinia` (som vi körde) hade SÄMST marginal av alla. Uppmätt overround
    # på plats, samma event och linjer överallt:
    #   betinia 1,0949 · ninjacasino 1,0645/Superettan 1,0834
    #   ninjacasinose = betiniase 1,0645/1,0664 (svensklicensierade skins)
    # De två SE-skinnen är identiska; ninjacasinose är equal-best i alla tre
    # ligor. Byt aldrig skin utan att mäta overrounden först.
    {"key": "ninjacasino", "name": "Ninja Casino", "altenar": "ninjacasinose"},
]


@functools.lru_cache(maxsize=1)
def active_sources() -> frozenset[str]:
    """Källor som FAKTISKT samlas i dag — härlett, aldrig uppräknat.

    `oddset_source_health` städas aldrig (PK skriver över sig själv), så en
    urkopplad källa ligger kvar och åldras tyst till "fel" i UI:t. Att räkna
    upp de aktiva för hand hade bara flyttat problemet: listan glöms nästa
    gång en källa kopplas bort. Härledningen ur de listor som redan styr
    insamling och värdering håller sig själv aktuell.
    """
    from .oddset_value import ANCHOR_SOURCES, SHADOW_SOURCES
    from .live_radar import LIVE_SOURCES
    return frozenset(
        {"pinnacle", "svenskaspel"}                    # sharp + huvudbok
        | {book["key"] for book in BOOKS}              # mjuka böcker
        | set(ANCHOR_SOURCES) | set(SHADOW_SOURCES)    # ankare/skugga
        | set(LIVE_SOURCES))                           # live-radarn


def passive_sources() -> frozenset[str]:
    """Källor som SAMLAS men inte matar något beslut i dag.

    Skillnaden är inte kosmetisk: ett fel hos Pinnacle stoppar värde, steam
    och notiser, medan ett fel hos en passiv källa inte påverkar en enda
    siffra i appen. UI:t sa "behöver tillsyn" om båda, vilket gjorde varningen
    till brus — Smarkets 503 på ligan `friendlies` såg lika allvarligt ut som
    ett sharp-avbrott.

    * `matchbook` är per förregistrering ren skuggjämförelse (SHADOW_SOURCES).
    * `smarkets` är kvar i ANCHOR_SOURCES som SÄKERHETSSPÄRR — utan den blir
      den en spelbar bok igen (184 av 476 felaktiga flaggor 2026-07-25) — men
      andra ankaret är bortkopplat sedan 2026-08-07 och `anchor2_*` skrivs som
      NULL. Serien samlas vidare enbart för den förregistrerade
      promotionsregeln i `docs/tva-ankare-2026-07-25.md`.

    Spärren och användningen hålls alltså isär: den här listan säger något om
    KONSUMTION, inte om huruvida källan får vara en bok.
    """
    from .oddset_value import ANCHOR2_SOURCE, SHADOW_SOURCES
    return frozenset(set(SHADOW_SOURCES) | {ANCHOR2_SOURCE})


DEEP_MARKETS_DAYS = 7      # Kambi AH/ÖU per event bara för matcher inom N dygn
LIST_WINDOW_H_BACK = 2     # visa matcher som startat för < 2 h sedan
LIST_WINDOW_D_FWD = 10

# Snabbpoll (backlog A1): 30-min-pollen är för långsam för lag-fönstret — när
# avspark närmar sig körs lätta varv (Pinnacle + böckernas 1X2 samt SvS-deep
# för matcherna i 3h-fönstret; ingen modelldata) i samma launchd-pass.
# OBS: backloggen skrev "<36 h" men det vore i praktiken kontinuerlig polling
# dygnet runt (Pinnacle Cloudflare-blockar på IP-nivå) — 3 h täcker lineup-
# fönstret + sena steamen och håller volymen nere. Bara ligor med match i
# fönstret pollas.
FAST_WITHIN_H = 3.0        # snabbvarv när nästa avspark är inom N h
FAST_SLEEP_S = 240         # 4 min mellan snabbvarven (A1: 3–5 min)
# Ett lyckat svar från en CDN-cache är inte automatiskt "sett i detta varv".
# Äldre objekt sparas med sin korrigerade tid men öppnar inte notisgrinden.
PINNACLE_PRESENT_MAX_AGE_S = 300

# Forskningsligor under säsongsuppehåll: 10-dagarsfönstret är tomt ända fram
# till premiären — ordinarie UI-payloaden visar då ligans NÄSTA omgång
# (matcher inom några dygn från första kommande avspark) så att en synlig
# liga inte ser trasig ut. Gäller BARA UI-vägen; insamlings-payloaden
# (include_research=True) behåller det strikta fönstret.
RESEARCH_NEXT_ROUND_SPAN_D = 4
RESEARCH_LOOKAHEAD_D = 45


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- klubbnamnsmatchning -----------------------------------------------------

# vanliga föreningssuffix som skiljer källorna åt ("Hammarby IF" vs "Hammarby")
_NOISE = {"if", "ff", "fk", "bk", "sk", "ik", "ib", "is", "fc", "afc", "aif",
          "gif", "cf", "ac", "sc", "bp", "kff",
          # Europacupernas föreningsformer (2026-07-28): samma klass som
          # fc/fk ovan. Källorna är oense om prefixet (Sofascore "GNK Dinamo
          # Zagreb", FotMob/Pinnacle "Dinamo Zagreb") vilket gav dubbelkort i
          # radarn när _same_team inte länkade providrarna. Identitetsnamn
          # som AEK/CSKA hör INTE hit — bara juridisk form.
          "nk", "gnk", "hnk", "kf", "ks", "pfc"}
_CHARMAP = str.maketrans({"ø": "o", "Ø": "o", "æ": "a", "Æ": "a", "đ": "d", "ð": "d",
                          "ł": "l", "ß": "ss", "/": " ", "-": " ", ".": " ", "'": ""})
# Ett perfekt lag på ena sidan får aldrig väga upp ett orelaterat lag på den
# andra. Det hände när "Inter" gav 1,00 mot "Internazionale U23" medan
# "Karlsruher" bara gav 0,25 mot "Novara"; medelvärdet 0,625 passerade då den
# gamla gränsen 0,55. Hellre en olänkad källrad än två matcher i samma identitet.
MIN_TEAM_SIDE_SIM = 0.55
MIN_MATCH_SCORE = 0.75


# Förkortningsalias (2026-07-28, backlog-småpunkten): normaliserat källnamn
# → kanoniskt namn, tillämpat SIST i norm_team så alla jämförelser (exakta,
# fuzzy, radar) ser samma identitet. ENDAST observerade par — identitets-
# saneringens läxa är att hellre lämna en rad olänkad än felmerga, så listan
# växer per bekräftat fall och ALDRIG via generella regler.
# IBV-fallet: Pinnacle "IBV" ↔ Kambi "ÍB Vestmennaeyjar" (Kambi stavar
# dessutom med e) mergade aldrig → dubblettrad i drift för 1/8-matchen.
TEAM_ALIASES = {
    "ibv": "vestmannaeyjar",
    "vestmennaeyjar": "vestmannaeyjar",
    # 2026-08-02: football-data och Sofascore stavar samma klubb olika, vilket
    # lade IN VARJE match TVÅ gånger i resultathistoriken — 588 dubblettpar.
    # Alla tolv paren är BEVISADE: samma liga, samma datum, samma motståndare
    # och identiskt resultat i båda raderna (noll oense). Kanonisk form är den
    # entydiga: `Göteborg` ensamt är en stad, `IFK Göteborg` en klubb.
    # Fem 1×-par från samma sökning avvisades som olika klubb (Málaga ≠
    # Mallorca, Barnsley ≠ Doncaster) — träningsmatchdagar med två motstånd.
    # Svensk/norsk genitiv:
    "halmstads": "halmstad",
    "djurgardens": "djurgarden",
    "osters": "oster",
    "aalesunds": "aalesund",
    "odds": "odd",
    # Föreningsprefix/-suffix som inte ryms i _NOISE (`ifk` är identitetsbärande
    # i vardagligt tal men samma juridiska klass som `if`/`gif`):
    "goteborg": "ifk goteborg",
    "norrkoping": "ifk norrkoping",
    "varnamo": "ifk varnamo",
    "tromso il": "tromso",
    "sandefjord fotball": "sandefjord",
    "landskrona": "landskrona bois",
    # Förkortningar:
    "la galaxy": "los angeles galaxy",
    "atlanta utd": "atlanta united",
    # 2026-08-05, samma klass som 588-radersfyndet ovan: football-data skriver
    # `Leicester` (84 rader), Sofascore `Leicester City` (2 rader,
    # träningsmatcher). Kanonisk form är den entydigt dominerande i
    # `oddset_results`. `oddset_result_stats` var redan ren — bara `leicester`.
    "leicester city": "leicester",
}


def norm_team(name: str) -> str:
    """Normalisera klubbnamn för källmatchning: gemener, inga diakriter,
    föreningssuffix borta (om något annat blir kvar), känt alias sist."""
    s = (name or "").translate(_CHARMAP)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    toks = [t for t in s.split() if t]
    kept = [t for t in toks if t not in _NOISE]
    out = " ".join(kept or toks)
    return TEAM_ALIASES.get(out, out)


def _team_sim(a: str, b: str) -> float:
    na, nb = norm_team(a), norm_team(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _team_pair_score(home_a: str, away_a: str,
                     home_b: str, away_b: str) -> float:
    home_score = _team_sim(home_a, home_b)
    away_score = _team_sim(away_a, away_b)
    if min(home_score, away_score) < MIN_TEAM_SIDE_SIM:
        return 0.0
    return (home_score + away_score) / 2


def _match_score(home_a: str, away_a: str, start_a: Optional[str],
                 home_b: str, away_b: str, start_b: Optional[str]) -> float:
    ta, tb = _parse_ts(start_a), _parse_ts(start_b)
    if ta and tb and abs((ta - tb).total_seconds()) > 2 * 3600:
        return 0.0
    return _team_pair_score(home_a, away_a, home_b, away_b)


def _resolve(cands: list[dict], home: str, away: str, start: Optional[str],
             min_score: float = MIN_MATCH_SCORE) -> Optional[dict]:
    """Hitta befintlig match (samma liga) för ett källevent — bästa fuzzy-träff."""
    best, best_s = None, min_score
    for c in cands:
        s = _match_score(home, away, start, c["home"], c["away"], c["start"])
        if s > best_s:
            best, best_s = c, s
    return best


def _resolve_source(cands: list[dict], home: str, away: str,
                    start: Optional[str], source_id, id_field: str) -> Optional[dict]:
    """Länka ett källevent utan att någonsin byta en redan låst identitet.

    Exakt externt id vinner. Fuzzy-matchning får bara använda kandidater där
    källans id ännu saknas; en match med ett ANNAT id från samma källa är redan
    upptagen och kan inte tas över. `pin:<id>`/`svs:<id>` är dessutom en
    självbärande identitet och en korrupt suffix/id-kombination räknas inte som
    en exakt träff.
    """
    source_id = str(source_id)
    prefix = {"pinnacle_id": "pin:", "kambi_id": "svs:"}.get(id_field)
    for cand in cands:
        existing = cand.get(id_field)
        if existing is None or str(existing) != source_id:
            continue
        if prefix and str(cand.get("id") or "").startswith(prefix):
            if str(cand["id"])[len(prefix):] != source_id:
                continue
        return cand
    available = [cand for cand in cands if not cand.get(id_field)]
    return _resolve(available, home, away, start)


def _resolve_team_pair(cands: list[dict], home: str, away: str,
                       min_score: float = 0.80) -> Optional[dict]:
    """Entydig lagparslänk utan tid.

    Används bara för research-only höst/vår-ligor där Kambi publicerar hela
    premiäromgången på en gemensam placeholdertid innan TV-tiderna är satta.
    Hemma/borta-paret förekommer bara en gång per ligasäsong; oentydighet ger
    alltid None i stället för en gissning.
    """
    ranked = sorted((
        (_team_pair_score(home, away, cand["home"], cand["away"]), cand)
        for cand in cands
    ), key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < min_score:
        return None
    if len(ranked) > 1 and abs(ranked[0][0] - ranked[1][0]) < 0.05:
        return None
    return ranked[0][1]


# --- Pinnacle per liga ---------------------------------------------------------

def _alt_pairs(prices: list[dict], key_a: str, key_b: str) -> list[dict]:
    """ALLA kompletta linjepar ur sharpens svar (inte bara huvudlinan).
    Alternativlinjerna gör samma-linje-jämförelse möjlig när boken visar en
    annan lina än sharpens huvudlina — utan dem dog 67 % av AH- och ~40 % av
    Ö/U-jämförelserna på olika-linje-regeln (mätt 2026-07-20)."""
    groups: dict[float, dict] = {}
    for p in prices:
        if p.get("points") is None:
            continue
        groups.setdefault(abs(p["points"]), {})[p.get("designation")] = p
    out = []
    for _, g in groups.items():
        if key_a not in g or key_b not in g:
            continue
        da, db = american_to_decimal(g[key_a]["price"]), american_to_decimal(g[key_b]["price"])
        if not da or not db:
            continue
        out.append({"a": da, "b": db, "line": g[key_a]["points"]})
    out.sort(key=lambda r: r["line"])
    return out


def _main_pair(prices: list[dict], key_a: str, key_b: str) -> Optional[dict]:
    """Huvudlinan bland alternativa linjer: båda decimaloddsen närmast jämnt 2.0."""
    best, best_score = None, 1e9
    for pair in _alt_pairs(prices, key_a, key_b):
        score = abs(pair["a"] - 2) + abs(pair["b"] - 2)
        if score < best_score:
            best, best_score = pair, score
    return best


def pinnacle_league_index(pin: Pinnacle, league_id: int) -> list[dict]:
    """Ligans matcher i decimalodds (2 anrop). Moneyline i första hand; saknas den
    härleds 1X2 ur spread+total (odds_source='derived'). AH/ÖU/hörnor = huvudlinan.
    Hörn-specials är barn-matchups (units='Corners') som mappas till föräldern."""
    matchups = pin._get(f"/leagues/{league_id}/matchups")
    markets = pin._get(f"/leagues/{league_id}/markets/straight")
    cor_parent = {m["id"]: m.get("parentId") for m in matchups
                  if m.get("units") == "Corners" and m.get("parentId")}
    ml: dict = {}
    spread: dict[int, list] = {}
    total: dict[int, list] = {}
    cor_total: dict[int, list] = {}
    for x in markets:
        if x.get("period") != 0:
            continue
        mid, t = x.get("matchupId"), x.get("type")
        if mid in cor_parent:
            if t == "total":
                cor_total.setdefault(cor_parent[mid], []).extend(x.get("prices", []))
            continue
        if t == "moneyline":
            ml[mid] = x
        elif t == "spread":
            spread.setdefault(mid, []).extend(x.get("prices", []))
        elif t == "total":
            total.setdefault(mid, []).extend(x.get("prices", []))

    out: list[dict] = []
    for m in matchups:
        if m.get("parent") is not None or m.get("type") != "matchup":
            continue
        parts = {p.get("alignment"): p.get("name") for p in m.get("participants", [])}
        home, away = parts.get("home"), parts.get("away")
        if not home or not away:
            continue
        mid = m["id"]
        mk = ml.get(mid)
        if mk:
            prices = {p.get("designation"): american_to_decimal(p.get("price"))
                      for p in mk.get("prices", []) if p.get("designation")}
            odds = {"1": prices.get("home"), "X": prices.get("draw"), "2": prices.get("away")}
            source = "pinnacle"
        else:
            odds = derive_1x2(spread.get(mid, []), total.get(mid, []))
            source = "derived" if odds else None
            odds = odds or {"1": None, "X": None, "2": None}
        ah = _main_pair(spread.get(mid, []), "home", "away")
        ou = _main_pair(total.get(mid, []), "over", "under")
        co = _main_pair(cor_total.get(mid, []), "over", "under")
        out.append({
            "id": str(mid), "home": home, "away": away,
            "start": m.get("startTime"), "status": m.get("status"),
            "odds": odds, "odds_source": source,
            "ah": {"H": ah["a"], "A": ah["b"], "line": ah["line"]} if ah else None,
            "ou": {"O": ou["a"], "U": ou["b"], "line": ou["line"]} if ou else None,
            "cor": {"O": co["a"], "U": co["b"], "line": co["line"]} if co else None,
            "alt": {"ah": _alt_pairs(spread.get(mid, []), "home", "away"),
                    "ou": _alt_pairs(total.get(mid, []), "over", "under"),
                    "cor": _alt_pairs(cor_total.get(mid, []), "over", "under")},
        })
    out.sort(key=lambda r: r.get("start") or "")
    return out


def pinnacle_known_moneylines(pin: Pinnacle, league_id: int,
                              cands: list[dict]) -> list[dict]:
    """Ett enda Pinnacle-anrop för kända researchmatcher i snabbfönstret.

    Fullvarvet har redan fryst matchup-ID, lag och avspark. Vid 4-minutersvarv
    behövs därför bara marknadssvaret; det halverar Pinnacle-trafiken för de
    fyra nya ligorna. Endast direkt moneyline accepteras eftersom V2.2 ändå
    förbjuder härledd sharp-1X2.
    """
    known = {
        str(cand["pinnacle_id"]): cand for cand in cands
        if cand.get("pinnacle_id")
    }
    moneylines = {}
    for market in pin._get(f"/leagues/{league_id}/markets/straight"):
        matchup_id = str(market.get("matchupId"))
        if (matchup_id in known and market.get("period") == 0 and
                market.get("type") == "moneyline"):
            moneylines[matchup_id] = market
    out = []
    for matchup_id, market in moneylines.items():
        cand = known[matchup_id]
        prices = {
            price.get("designation"): american_to_decimal(price.get("price"))
            for price in market.get("prices", [])
        }
        out.append({
            "id": matchup_id, "home": cand["home"], "away": cand["away"],
            "start": cand["start"], "status": cand.get("status"),
            "odds": {
                "1": prices.get("home"), "X": prices.get("draw"),
                "2": prices.get("away"),
            },
            "odds_source": "pinnacle", "ah": None, "ou": None, "cor": None,
            "alt": {},
        })
    return out


# --- insamling -----------------------------------------------------------------

_PAIR_KEYS = {"ah": ("H", "A"), "ou": ("O", "U"), "cor": ("O", "U")}


def _observe_pair_market(store: Storage, mid: str, source: str, market: str,
                         value: Optional[dict], at: str) -> int:
    """Registrera en enskild parmarknad efter ett lyckat källsvar."""
    k1, k2 = _PAIR_KEYS[market]
    rows = ({
            k1: {"odds": value[k1], "line": value["line"]},
            k2: {"odds": value[k2], "line": value["line"]}}
            if value else {})
    return store.oddset_save_market(mid, source, market, rows, at)


def _observe_pair_markets(store: Storage, mid: str, source: str,
                          row: dict, at: str) -> int:
    """Registrera alla parmarknader efter ett lyckat källsvar.

    Även en saknad marknad är information: en tidigare rad ska då markeras
    unavailable i stället för att ligga kvar som ett spelbart spökpris.
    """
    n = 0
    for market in _PAIR_KEYS:
        n += _observe_pair_market(
            store, mid, source, market, row.get(market), at)
    return n


def collect(store: Storage, leagues: Optional[list[dict]] = None,
            deep: bool = True) -> dict:
    """Hämta odds för alla ligor från båda källorna. Returnerar rapport per liga.

    deep=False är snabbvarvet (A1): Pinnacle + böckernas 1X2, samt Kambi-deep
    endast för matcher i 3h-fönstret. Modelldata/modellfit hoppas över. leagues
    begränsar till ligor med match i snabbfönstret."""
    at = _now_iso()
    now = dt.datetime.now(dt.timezone.utc)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    list_until = (now + dt.timedelta(days=LIST_WINDOW_D_FWD)).strftime("%Y-%m-%dT%H:%M:%SZ")
    deep_until = (now + dt.timedelta(days=DEEP_MARKETS_DAYS)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    fast_until = (now + dt.timedelta(hours=FAST_WITHIN_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: dict = {"at": at, "leagues": {}, "errors": []}
    # Notisvakten (WP2-mini, granskningen runda 2): allt som faktiskt sågs i
    # DETTA varvs lyckade svar — (match_id, källa, marknad). Misslyckad källa
    # eller saknad marknad hamnar aldrig här → notiser kan inte citera priser
    # som kan vara plockade/suspenderade. Gamla priser i DB räcker inte.
    present: set[tuple] = set()
    pin = Pinnacle()
    # Smarkets-ankaret: ETT anrop ger alla kommande fotbollsevent, som sedan
    # delas mellan ligorna. Fel här får aldrig fälla insamlingen — ankaret är
    # ett tillägg, inte en förutsättning.
    from . import smarkets
    smarkets_client = smarkets.Smarkets()
    smarkets_events: Optional[list[dict]] = None
    try:
        smarkets_events = smarkets_client.upcoming_events()
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"smarkets events: {exc}")
        store.oddset_record_source_health(
            "smarkets", "-", "events", at, False, 0, str(exc))
    # TREDJE MARKNADSREFERENSEN (2026-07-27): Matchbook — ENDAST skugg-
    # insamling i snabbfönstret (kallplanens reservspår). Eventen hämtas
    # LAT: först när en mappad liga faktiskt har en match som startar inom
    # FAST_WITHIN_H — utanför fönstret rör vi inte källan alls (artighet +
    # rule 6: en källa vi inte frågade är ingen observation). Ett anrop ger
    # pris OCH likviditet för hela fönstret och delas mellan ligorna.
    from . import matchbook
    matchbook_client = matchbook.Matchbook()
    matchbook_events: Optional[list[dict]] = None
    matchbook_tried = False
    matchbook_at = at   # sätts om EFTER lyckad hämtning (observationstidsregeln)
    try:
        for lg in (LEAGUES if leagues is None else leagues):
            research_only = bool(lg.get("research_only"))
            cands = [m for m in store.oddset_matches(since=since, until=list_until)
                     if m["league"] == lg["key"]]
            rows_saved, n_pin, n_kambi = 0, 0, 0

            pin_ok, pin_error = True, None
            pin_cache_age_s = 0
            pin_observed_at = at
            pin_rows = []
            try:
                # Cuperna är TVÅ Pinnacle-ligor (huvudturnering + kval). Varje
                # id hämtas separat och raderna stämplas med sitt EGET anrops
                # observationstid (_observed_at/_age_s): batcharna kan ligga
                # olika i Pinnacles CDN-cache (max-age 905), så en gemensam
                # stämpel hade daterat ena batchens priser upp till ~15 min fel.
                for pin_league_id in _pin_ids(lg):
                    reset_age = getattr(pin, "reset_cache_age", None)
                    if reset_age:
                        reset_age()
                    batch = (
                        pinnacle_known_moneylines(pin, pin_league_id, cands)
                        if not deep and research_only and any(
                            cand.get("pinnacle_id") for cand in cands)
                        else pinnacle_league_index(pin, pin_league_id)
                    )
                    # Båda insamlingsvägarna hämtar marknader sist; det är
                    # prisendpointens Age som ska korrigera prisets observation.
                    # ÖVERKORRIGERINGSFIX (2026-07-25): Age måste dras från det
                    # EGNA anropets tid, inte från varvets start `at`. Ligaloopen
                    # kan pågå i upp till 25 min, så sena ligor bakåtdaterades
                    # tidigare med Age PLUS hela den förflutna insamlingstiden.
                    pin_fetch_at = _now_iso()
                    age_s = int(getattr(pin, "last_age_s", 0) or 0)
                    observed = cache_adjusted_iso(pin_fetch_at, age_s)
                    for r in batch:
                        r["_observed_at"], r["_age_s"] = observed, age_s
                    pin_rows.extend(batch)
            except Exception as e:  # noqa: BLE001 — Arcadia Cloudflare-blockar ibland
                pin_ok, pin_error = False, str(e)
                report["errors"].append(f"pinnacle {lg['key']}: {e}")
            store.oddset_record_source_health(
                "pinnacle", lg["key"], "markets", at, pin_ok, len(pin_rows), pin_error)
            pin_seen: set[str] = set()
            for r in pin_rows:
                pin_observed_at = r.get("_observed_at") or pin_observed_at
                pin_cache_age_s = r.get("_age_s", pin_cache_age_s)
                locked = store.oddset_match_by_source_id(
                    "pinnacle_id", r["id"])
                ex = (_resolve_source(
                    [locked], r["home"], r["away"], r["start"],
                    r["id"], "pinnacle_id") if locked else None) or _resolve_source(
                    cands, r["home"], r["away"], r["start"],
                    r["id"], "pinnacle_id")
                mid = ex["id"] if ex else f"pin:{r['id']}"
                m = {"id": mid, "league": lg["key"], "home": r["home"], "away": r["away"],
                     "start": r["start"], "pinnacle_id": r["id"], "status": r.get("status")}
                store.oddset_upsert_match(m, prefer_names=False)
                if not ex:
                    cands.append(m)
                elif not ex.get("pinnacle_id"):
                    ex["pinnacle_id"] = r["id"]
                if (r.get("start") or "9") <= at:
                    continue   # startad match = live-odds — förorena inte serierna
                pin_seen.add(str(r["id"]))
                if r["odds_source"]:
                    rows_saved += store.oddset_save_odds(
                        mid, r["odds_source"], r["odds"], pin_observed_at)
                    other = "derived" if r["odds_source"] == "pinnacle" else "pinnacle"
                    store.oddset_mark_market_unavailable(mid, other, "1x2")
                    if (pin_cache_age_s <= PINNACLE_PRESENT_MAX_AGE_S and
                            all(r["odds"].get(s) for s in ("1", "X", "2"))):
                        present.add((mid, "pinnacle", "1x2"))
                else:
                    store.oddset_mark_market_unavailable(mid, "pinnacle", "1x2")
                    store.oddset_mark_market_unavailable(mid, "derived", "1x2")
                if not research_only:
                    rows_saved += _observe_pair_markets(
                        store, mid, "pinnacle", r, pin_observed_at)
                    for mk_ in _PAIR_KEYS:
                        if (pin_cache_age_s <= PINNACLE_PRESENT_MAX_AGE_S and
                                r.get(mk_)):
                            present.add((mid, "pinnacle", mk_))
                        # sharpens ALLA linjer (tom lista efter lyckat svar =
                        # tidigare linjer markeras plockade)
                        store.oddset_save_sharp_alt(
                            mid, mk_, (r.get("alt") or {}).get(mk_) or [],
                            pin_observed_at)
                n_pin += 1

            if pin_ok:
                for c in cands:
                    pid = c.get("pinnacle_id")
                    if not pid or str(pid) in pin_seen or (c.get("start") or "9") <= at:
                        continue
                    store.oddset_mark_market_unavailable(c["id"], "pinnacle", "1x2")
                    store.oddset_mark_market_unavailable(c["id"], "derived", "1x2")
                    if not research_only:
                        for market in _PAIR_KEYS:
                            store.oddset_mark_market_unavailable(
                                c["id"], "pinnacle", market)

            kambi_ok, kambi_error = True, None
            # Pristid = det EGNA anropets tid, inte varvets start. Ligaloopen
            # kan pågå i 25 min; `at` som pristid daterar sena ligors priser
            # upp till en halvtimme fel i rörelseserierna.
            kambi_at = _now_iso()
            kambi_rows = []
            try:
                # Cupernas två vägar (huvudturnering + kval): varje batch
                # stämplas med sin EGEN pristid (_at), samma skäl som
                # Pinnacle-batcharna ovan.
                for kambi_path in _kambi_paths(lg):
                    batch = kambi.league_events(kambi_path, strict=True)
                    batch_at = cache_adjusted_iso(_now_iso(), kambi.last_age_s)
                    for e in batch:
                        e["_at"] = batch_at
                    kambi_rows.extend(batch)
            except Exception as e:  # noqa: BLE001
                kambi_ok, kambi_error = False, str(e)
                report["errors"].append(f"kambi {lg['key']}: {e}")
            store.oddset_record_source_health(
                "svenskaspel", lg["key"], "1x2", at, kambi_ok,
                len(kambi_rows), kambi_error)
            kambi_seen: set[str] = set()
            deep_errors: list[str] = []
            deep_checked = 0
            for e in kambi_rows:
                kambi_at = e.get("_at") or kambi_at
                locked = store.oddset_match_by_source_id(
                    "kambi_id", e["id"])
                id_match = (_resolve_source(
                    [locked], e["home"], e["away"], e["start"],
                    e["id"], "kambi_id") if locked else None) or _resolve_source(
                    cands, e["home"], e["away"], e["start"],
                    e["id"], "kambi_id")
                # Kambis tidiga höst/vår-scheman använder ibland en gemensam
                # placeholdertid för nästan hela omgången. Pinnacle-raden är
                # då starttidskanon; team-only används endast mot en redan
                # verifierad Pinnacle-identitet i researchligor.
                team_match = (
                    _resolve_team_pair(
                        [cand for cand in cands
                         if cand.get("pinnacle_id") and not cand.get("kambi_id")],
                        e["home"], e["away"])
                    if research_only and id_match is None else None
                )
                ex = id_match or team_match
                mid = ex["id"] if ex else f"svs:{e['id']}"
                m = {"id": mid, "league": lg["key"], "home": e["home"], "away": e["away"],
                     "start": e["start"], "kambi_id": e["id"]}
                # Kambis svenska namn vinner som visningsnamn
                store.oddset_upsert_match(m, prefer_names=True)
                if not ex:
                    cands.append(m)
                elif not ex.get("kambi_id"):
                    ex["kambi_id"] = e["id"]
                if (e.get("start") or "9") <= at:
                    continue   # live — spara inte
                kambi_seen.add(str(e["id"]))
                rows_saved += store.oddset_save_odds(mid, "svenskaspel", e["odds"], kambi_at)
                if all(e["odds"].get(s) for s in ("1", "X", "2")):
                    present.add((mid, "svenskaspel", "1x2"))
                market_until = deep_until if deep else fast_until
                if (not research_only and
                        (e.get("start") or "9") <= market_until):
                    deep_checked += 1
                    try:
                        mk = kambi.event_markets(
                            e["id"], e["home"], e["away"], strict=True)
                        # Observationstidsregeln p.3: per-anropstid − Age,
                        # aldrig varvstart — en ligaloop kan pågå 25 min.
                        deep_at = cache_adjusted_iso(_now_iso(), kambi.last_age_s)
                        rows_saved += _observe_pair_markets(
                            store, mid, "svenskaspel", mk, deep_at)
                        for mk_ in _PAIR_KEYS:
                            if mk.get(mk_):
                                present.add((mid, "svenskaspel", mk_))
                    except Exception as exc:  # ett eventfel får inte dölja resten
                        deep_errors.append(f"{e['id']}: {exc}")
                        report["errors"].append(
                            f"kambi-deep {lg['key']} {e['id']}: {exc}")
                    time.sleep(0.25)   # paca CDN:et
                n_kambi += 1

            if kambi_ok:
                market_until = deep_until if deep else fast_until
                for c in cands:
                    kid = c.get("kambi_id")
                    if not kid or str(kid) in kambi_seen or (c.get("start") or "9") <= at:
                        continue
                    store.oddset_mark_market_unavailable(
                        c["id"], "svenskaspel", "1x2")
                    if (not research_only and
                            (c.get("start") or "9") <= market_until):
                        for market in _PAIR_KEYS:
                            store.oddset_mark_market_unavailable(
                                c["id"], "svenskaspel", market)
            store.oddset_record_source_health(
                "svenskaspel", lg["key"], "deep", at,
                kambi_ok and not deep_errors, deep_checked,
                "; ".join(deep_errors) if deep_errors else kambi_error)

            # Sidoböcker: Kambi-operatörer delar event-id:n, Altenar matchas
            # fuzzy. Altenars listvy ger 1X2 + mål; hörnor hämtas ur eventvyn
            # inom samma deep-/snabbfönster som Kambis detaljmarknader.
            n_books = 0
            for book in (() if research_only else BOOKS):
                if not book.get("kambi_op") and not (book.get("altenar") and lg.get("altenar")):
                    continue
                book_ok, book_error = True, None
                book_at = _now_iso()   # fallback; sätts om per lyckat anrop nedan
                try:
                    if book.get("kambi_op"):
                        b_rows = []
                        for kambi_path in _kambi_paths(lg):
                            b_batch = kambi.league_events(
                                kambi_path, operator=book["kambi_op"],
                                strict=True)
                            # pristid = anropets tid − CDN-Age, inte varvets
                            # start; stämplas per batch (cupernas två vägar)
                            b_batch_at = cache_adjusted_iso(
                                _now_iso(), kambi.last_age_s)
                            for e in b_batch:
                                e["_at"] = b_batch_at
                            b_rows.extend(b_batch)
                        book_at = cache_adjusted_iso(_now_iso(), kambi.last_age_s)
                    else:
                        from . import altenar
                        b_rows = altenar.league_events(
                            lg["altenar"], integration=book["altenar"], strict=True)
                        book_at = cache_adjusted_iso(_now_iso(), altenar.last_age_s)
                except Exception as exc:  # noqa: BLE001
                    b_rows = []
                    book_ok, book_error = False, str(exc)
                    report["errors"].append(f"{book['key']} {lg['key']}: {exc}")
                store.oddset_record_source_health(
                    book["key"], lg["key"], "1x2", at, book_ok,
                    len(b_rows), book_error)
                book_seen: set[str] = set()
                book_claims: dict[str, str] = {}
                book_deep_errors: list[str] = []
                book_deep_checked = 0
                for e in b_rows:
                    book_at = e.get("_at") or book_at
                    ex = next((c for c in cands if c.get("kambi_id") == e["id"]), None) \
                        if book.get("kambi_op") else None
                    ex = ex or _resolve(cands, e["home"], e["away"], e["start"])
                    if not ex or (e.get("start") or "9") <= at:
                        continue   # skapa inga matcher från sidoböcker; hoppa live
                    claim = str(e.get("id"))
                    if (ex["id"] in book_claims
                            and book_claims[ex["id"]] != claim):
                        report["errors"].append(
                            f"{book['key']} identity collision {lg['key']}: "
                            f"{book_claims[ex['id']]} och {claim} -> {ex['id']}")
                        continue
                    book_claims[ex["id"]] = claim
                    rows_saved += store.oddset_save_odds(ex["id"], book["key"], e["odds"], book_at)
                    book_seen.add(ex["id"])
                    if all(e["odds"].get(s) for s in ("1", "X", "2")):
                        present.add((ex["id"], book["key"], "1x2"))
                    # TOTALT ANTAL MÅL FRÅN ALTENAR (2026-07-25). Låg gratis i
                    # samma svar men slängdes. Det spelar roll för att Ö/U annars
                    # bara fanns hos SvS och Pinnacle: Expekts deep-priser är
                    # IDENTISKA med SvS (samma Kambi-feed), medan Altenar
                    # prissätter själv — uppmätt Brommapojkarna–Hammarby
                    # 2,25/1,57 @3,5 mot SvS 1,71/1,97 @3,0.
                    if book.get("altenar"):
                        # Även en SAKNAD Ö/U i ett lyckat listsvar är
                        # information: en plockad marknad får inte ligga kvar
                        # som spelbart spökpris i upp till 45 min (samma
                        # mönster som cor-vägen nedan; granskningsfix F1).
                        rows_saved += _observe_pair_market(
                            store, ex["id"], book["key"], "ou", e.get("ou"),
                            book_at)
                        if e.get("ou"):
                            present.add((ex["id"], book["key"], "ou"))
                    elif e.get("ou"):
                        rows_saved += _observe_pair_market(
                            store, ex["id"], book["key"], "ou", e["ou"], book_at)
                        present.add((ex["id"], book["key"], "ou"))
                    market_until = deep_until if deep else fast_until
                    if (book.get("altenar")
                            and (e.get("start") or "9") <= market_until):
                        book_deep_checked += 1
                        try:
                            from . import altenar
                            mk = altenar.event_markets(
                                e["id"], integration=book["altenar"], strict=True)
                            detail_at = cache_adjusted_iso(
                                _now_iso(), altenar.last_age_s)
                            rows_saved += _observe_pair_market(
                                store, ex["id"], book["key"], "cor",
                                mk.get("cor"), detail_at)
                            if mk.get("cor"):
                                present.add((ex["id"], book["key"], "cor"))
                        except Exception as exc:  # ett eventfel får inte dölja resten
                            book_deep_errors.append(f"{e['id']}: {exc}")
                            report["errors"].append(
                                f"{book['key']}-deep {lg['key']} {e['id']}: {exc}")
                        time.sleep(0.25)
                    n_books += 1
                if book_ok:
                    market_until = deep_until if deep else fast_until
                    for c in cands:
                        if c["id"] in book_seen or (c.get("start") or "9") <= at:
                            continue
                        store.oddset_mark_market_unavailable(
                            c["id"], book["key"], "1x2")
                        if book.get("altenar"):
                            # Mål ligger i det lyckade listsvaret. Saknas
                            # matchen där är ett tidigare målpris inte spelbart.
                            store.oddset_mark_market_unavailable(
                                c["id"], book["key"], "ou")
                            if (c.get("start") or "9") <= market_until:
                                store.oddset_mark_market_unavailable(
                                    c["id"], book["key"], "cor")
                if book.get("altenar"):
                    store.oddset_record_source_health(
                        book["key"], lg["key"], "deep", at,
                        book_ok and not book_deep_errors, book_deep_checked,
                        ("; ".join(book_deep_errors)
                         if book_deep_errors else book_error))

            # ANDRA SHARP-ANKARET (2026-07-24): Smarkets är en BÖRS, inte en
            # bok vi letar värde hos — uppmätt overround ~1,00 mot Svenska
            # Spels 2,6 %. Den ligger därför medvetet UTANFÖR `BOOKS`
            # (max-över-böcker-jakten) och sparas som egen källa. Syftet är
            # metodiskt: idag mäts varje edge bara mot vår egen power-devig av
            # Pinnacle, och metodvalet rör ~3 pp medan flaggtröskeln är 2 pp.
            # Ett börs-mid behöver knappt devigas och validerar därför devigen.
            # Insamlas nu, används först när serien vuxit (samma ordning som
            # PIT-datat). Se docs/forbattringar.md.
            n_anchor = 0
            if smarkets_events is not None and lg["key"] in smarkets.LEAGUE_SLUGS:
                anchor_ok, anchor_error = True, None
                anchor_at = _now_iso()   # pristid = anropets tid
                try:
                    a_rows = smarkets_client.league_events(
                        lg["key"], strict=True, events=smarkets_events)
                except Exception as exc:  # noqa: BLE001
                    a_rows = []
                    anchor_ok, anchor_error = False, str(exc)
                    report["errors"].append(f"smarkets {lg['key']}: {exc}")
                store.oddset_record_source_health(
                    "smarkets", lg["key"], "1x2", at, anchor_ok,
                    len(a_rows), anchor_error)
                anchor_seen: set[str] = set()
                anchor_claims: dict[str, str] = {}
                for e in a_rows:
                    ex = _resolve(cands, e["home"], e["away"], e["start"])
                    if not ex or (e.get("start") or "9") <= at:
                        continue   # börsen får aldrig skapa matchidentiteter
                    claim = str(e.get("id"))
                    if (ex["id"] in anchor_claims
                            and anchor_claims[ex["id"]] != claim):
                        report["errors"].append(
                            f"smarkets identity collision {lg['key']}: "
                            f"{anchor_claims[ex['id']]} och {claim} -> {ex['id']}")
                        continue
                    anchor_claims[ex["id"]] = claim
                    rows_saved += store.oddset_save_odds(
                        ex["id"], "smarkets", e["odds"], anchor_at)
                    anchor_seen.add(ex["id"])
                    n_anchor += 1
                if anchor_ok:
                    for c in cands:
                        if c["id"] in anchor_seen or (c.get("start") or "9") <= at:
                            continue
                        store.oddset_mark_market_unavailable(
                            c["id"], "smarkets", "1x2")

            # TREDJE MARKNADSREFERENSEN (2026-07-27): Matchbook-börsen, ENDAST
            # skugginsamling i snabbfönstret enligt den förregistrerade planen
            # (docs/bookmaker-kallplan-2026-07-25.md). Bästa back-odds sparas i
            # oddset_odds och tillgänglig likviditet (EUR) i egen tabell — båda
            # ur SAMMA svar, alltså samma observationstid. Matchbook ligger
            # UTANFÖR BOOKS och ANCHOR_SOURCES/ANCHOR2_SOURCE (spärren
            # oddset_value.SHADOW_SOURCES + payload-strippen) och får inte
            # skapa flaggor, notiser, CLV, steam eller matchidentiteter.
            # >= 28 dagar ren skugga innan någon runtimeroll ens prövas; tunn
            # likviditet får aldrig bekräfta/underkänna en edge.
            n_matchbook = 0
            if lg["key"] in matchbook.LEAGUE_TAGS:
                fast_cands = [c for c in cands
                              if at < (c.get("start") or "") <= fast_until]
                if fast_cands and not matchbook_tried:
                    matchbook_tried = True
                    try:
                        # API-fönstret = exakt kandidatfönstret (at..fast_until)
                        # så att ett lyckat svar bevisar närvaro/frånvaro för
                        # just de matcher vi frågade om — inga andra.
                        matchbook_events = matchbook_client.upcoming_events(
                            after_iso=at, until_iso=fast_until)
                        matchbook_at = cache_adjusted_iso(
                            _now_iso(), matchbook_client.last_age_s)
                    except Exception as exc:  # noqa: BLE001
                        report["errors"].append(f"matchbook events: {exc}")
                        store.oddset_record_source_health(
                            "matchbook", "-", "events", at, False, 0, str(exc))
                if fast_cands and matchbook_events is not None:
                    mb_ok, mb_error = True, None
                    try:
                        # delat eventsvar — inget nytt anrop; observationstiden
                        # är eventhämtningens (matchbook_at), inte "nu".
                        mb_rows = matchbook_client.league_events(
                            lg["key"], strict=True, events=matchbook_events)
                    except Exception as exc:  # noqa: BLE001
                        mb_rows = []
                        mb_ok, mb_error = False, str(exc)
                        report["errors"].append(f"matchbook {lg['key']}: {exc}")
                    store.oddset_record_source_health(
                        "matchbook", lg["key"], "1x2", at, mb_ok,
                        len(mb_rows), mb_error)
                    # Lazy-hämtningen kan ske minuter in i varvet: en match kan
                    # ha hunnit starta efter `at` — live-odds sparas aldrig.
                    live_guard = max(at, matchbook_at)
                    mb_seen: set[str] = set()
                    mb_claims: dict[str, str] = {}
                    for e in mb_rows:
                        ex = _resolve(fast_cands, e["home"], e["away"], e["start"])
                        if not ex or (e.get("start") or "9") <= live_guard:
                            continue   # referensen skapar ALDRIG matchidentiteter
                        claim = str(e.get("id"))
                        if (ex["id"] in mb_claims
                                and mb_claims[ex["id"]] != claim):
                            report["errors"].append(
                                f"matchbook identity collision {lg['key']}: "
                                f"{mb_claims[ex['id']]} och {claim} -> {ex['id']}")
                            continue
                        mb_claims[ex["id"]] = claim
                        rows_saved += store.oddset_save_odds(
                            ex["id"], "matchbook", e["odds"], matchbook_at)
                        store.oddset_save_matchbook_liquidity(
                            ex["id"], e["liquidity"], matchbook_at)
                        mb_seen.add(ex["id"])
                        n_matchbook += 1
                    if mb_ok:
                        # Frånvaro bevisas BARA för fönstret vi frågade om.
                        for c in fast_cands:
                            if (c["id"] in mb_seen
                                    or (c.get("start") or "9") <= live_guard):
                                continue
                            store.oddset_mark_market_unavailable(
                                c["id"], "matchbook", "1x2")

            report["leagues"][lg["key"]] = {
                "pinnacle": n_pin, "kambi": n_kambi, "books": n_books,
                "smarkets": n_anchor, "matchbook": n_matchbook,
                "saved_rows": rows_saved,
                "pinnacle_cache_age_s": pin_cache_age_s if pin_ok else None,
                "pinnacle_observed_at": pin_observed_at if pin_ok else None}
    finally:
        pin.close()
        if smarkets_client is not None:
            smarkets_client.close()
        matchbook_client.close()
    store.meta_set("oddset_last_run", at)
    if deep:
        # Kontrollhistoriken beskärs på djupvarvet (var 30:e min), inte i
        # skrivvägen: en DELETE per hälsorad hade kostat mer än den sparar.
        try:
            store.oddset_prune_source_health_log()
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"source_health_prune: {e}")
    # Etapp 3: resultat/xG/Elo till modellen (throttlat i modulen — oftast no-op)
    if deep:
        try:
            from . import oddset_data
            report["data"] = oddset_data.refresh_all(store)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"modeldata: {e}")
    # Etapp 2/WP5: samma point-in-time-payload driver både handlingsloggen och
    # forskningsledgern. Snabbvarvet fittar modellen ENDAST när en ny fast
    # horisont öppnas; annars förblir det lätt.
    try:
        payload = matches_payload(store, light=not deep, include_research=True)
        from . import oddset_ledger
        safe_matches = [
            match for match in payload["matches"]
            if not match.get("data_conflict")
        ]
        if deep:
            report["ledger_capture"] = oddset_ledger.capture_predictions(
                store, safe_matches)
        else:
            # V2.2:s forskningsligor ingår inte i produktmodellens ordinarie
            # due-lista. Fitta bara de matcher vars fasta shadowhorisont är ny,
            # innan sharp + feature + shadow fryses atomärt.
            from . import oddset_model, oddset_v22
            due_v22 = oddset_v22.due_matches(store, safe_matches)
            if due_v22:
                oddset_model.attach_model(
                    store, due_v22,
                    allowed_leagues=set(oddset_v22.SCOPE_LEAGUES),
                    fit_pools=oddset_v22.FIT_POOLS)
            sharp_capture = oddset_ledger.capture_predictions(
                store, safe_matches, tiers=("sharp",))
            due_model = oddset_ledger.due_model_matches(store, safe_matches)
            missing_model = [match for match in due_model if not match.get("model")]
            if missing_model:
                oddset_model.attach_model(store, missing_model)
            model_capture = oddset_ledger.capture_predictions(
                store, due_model, tiers=("model",))
            report["ledger_capture"] = {
                key: sharp_capture[key] + model_capture[key]
                for key in sharp_capture}
        actionable = [
            match for match in safe_matches
            if match.get("league") in ACTIONABLE_LEAGUE_KEYS
        ]
        vs = oddset_value.log_and_notify(store, actionable, present=present)
        vs["closings"] = oddset_value.resolve_closings(store)
        # utfalls-facitet (P2): settla 1X2-flaggor mot resultat när de finns
        vs["outcomes"] = oddset_value.resolve_outcomes(store)
        report["value"] = vs
    except Exception as e:  # noqa: BLE001 — får inte fälla insamlingen
        report["errors"].append(f"värde/notiser: {e}")
    try:
        from . import oddset_ledger
        report["ledger_closings"] = oddset_ledger.resolve_closings(store)
        oddset_ledger.prediction_report(store, update_states=True)
    except Exception as e:  # noqa: BLE001 — ledgern får inte fälla insamlingen
        report["errors"].append(f"prediction-ledger: {e}")
    return report


def hours_to_next_start(store: Storage) -> Optional[float]:
    """Timmar till nästa framtida avspark (styr snabbpollen)."""
    now = dt.datetime.now(dt.timezone.utc)
    ms = store.oddset_matches(since=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    starts = [_parse_ts(m.get("start")) for m in ms]
    hrs = [(t - now).total_seconds() / 3600 for t in starts if t]
    return min(hrs) if hrs else None


def fast_leagues(store: Storage) -> list[dict]:
    """Ligorna med avspark inom FAST_WITHIN_H — bara de pollas i snabbvarven."""
    now = dt.datetime.now(dt.timezone.utc)
    ms = store.oddset_matches(
        since=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        until=(now + dt.timedelta(hours=FAST_WITHIN_H)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    keys = {m["league"] for m in ms}
    return [lg for lg in LEAGUES if lg["key"] in keys]


# --- läs-API ---------------------------------------------------------------------

def _next_round_for_empty_leagues(store: Storage, windowed: list[dict],
                                  now: dt.datetime) -> list[dict]:
    """Nästa omgång för synliga ligor som saknar match i listfönstret.

    Gällde tidigare bara forskningsligor. När de fyra stora gjordes fullt
    följda 2026-08-07 blev mängden tom och funktionen tyst död — men problemet
    den löser är allmänt: under säsongsuppehåll ligger premiären utanför
    10-dagarsfönstret och ligan såg tom ut trots att omgången var satt. Under
    pågående säsong har varje liga matcher i fönstret, så villkoret slår
    aldrig till då.
    """
    empty = VISIBLE_LEAGUE_KEYS - {m["league"] for m in windowed}
    if not empty:
        return []
    future = store.oddset_matches(
        since=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        until=(now + dt.timedelta(days=RESEARCH_LOOKAHEAD_D))
        .strftime("%Y-%m-%dT%H:%M:%SZ"))
    extra: list[dict] = []
    for key in sorted(empty):
        rows = sorted((m for m in future if m["league"] == key),
                      key=lambda r: r.get("start") or "9")
        first = _parse_ts(rows[0].get("start")) if rows else None
        if not first:
            continue
        cutoff = (first + dt.timedelta(days=RESEARCH_NEXT_ROUND_SPAN_D)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        extra.extend(m for m in rows if (m.get("start") or "9") <= cutoff)
    return extra


# KÄLLOR SOM INTE SKA VISAS (2026-08-10). Smarkets är varken spelbar bok
# (utanför BOOKS) eller ankare — andra ankaret kopplades bort 2026-08-07 och
# `anchor2_*` skrivs som NULL, så ⚓-chipet kan inte längre utlösas. Kvar var
# ett `S`-pris i matchraden som ingen kan spela och som inte ankrar någon
# signal, till en kostnad av 116 kB (10,1 %) i varje listhämtning.
#
# Det här är ett VISNINGSVAL och inget annat. Spärren i
# `oddset_value.ANCHOR_SOURCES` står kvar — utan den blir Smarkets en spelbar
# bok igen (184 av 476 felaktiga flaggor 2026-07-25). Insamlingen står också
# kvar: serien matar den förregistrerade promotionsregeln i
# `docs/tva-ankare-2026-07-25.md`, och `attach_value` räknar sitt anchor2-skugg-
# mått FÖRE strippningen. Därför sätts flaggan bara av API:t — den INTERNA
# payloaden till WP5-ledgern fryser oförändrat innehåll.
UI_HIDDEN_SOURCES = frozenset({"smarkets"})


def matches_payload(store: Storage, light: bool = False,
                    include_research: bool = False,
                    compact_movement: bool = False,
                    include_movement: bool = True,
                    hide_sources: frozenset = frozenset(),
                    limit: int | None = None) -> dict:
    """Matchlistan i tidsordning med senaste odds + rörelseserier per källa.
    light=True (snabbvarven) hoppar frånvaro + modell — modellfitten är dyr
    och amber-flaggorna är inte tidskritiska; 30-min-varvet tar dem.
    compact_movement=True behåller first/last/linjeskift men tar bort de råa
    punkterna; UI hämtar dem separat först när en matchdetalj öppnas.
    include_movement=False tar bort även summeringen efter att `steam` räknats.
    limit begränsar bara API-listan efter att globala ligaantal räknats. Klienten
    kan därför måla de första raderna med ett litet svar men ändå visa korrekt
    totalantal och korrekta ligafilter medan resten berikas i bakgrunden.
    include_research=True är den INTERNA insamlings-payloaden (alla ligor,
    V2.2-forskningsmodell, ofiltrerat värde-underlag). Ordinarie API:t kör
    False: forskningsligor med visible_in_ui visas då med odds, prisålder
    och rörelser, märkta research=True, men utan värde-/modellfält —
    synlighet och actionability är två oberoende egenskaper. Är list-
    fönstret tomt för en forskningsliga (säsongsuppehåll) visas ligans
    nästa omgång i stället (_next_round_for_empty_leagues)."""
    now = dt.datetime.now(dt.timezone.utc)
    frm = (now - dt.timedelta(hours=LIST_WINDOW_H_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to = (now + dt.timedelta(days=LIST_WINDOW_D_FWD)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ms = store.oddset_matches(since=frm, until=to)
    if not include_research:
        ms = [match for match in ms if match["league"] in VISIBLE_LEAGUE_KEYS]
        ms.extend(_next_round_for_empty_leagues(store, ms, now))
    ids = [m["id"] for m in ms]
    latest = store.oddset_latest(ids)
    movement = store.oddset_movement(ids)
    alt = store.oddset_sharp_alt_latest(ids)
    conflicts = store.oddset_identity_conflicts(ids)
    out = []
    for m in ms:
        row = {**m, "odds": latest.get(m["id"], {}),
               "movement": movement.get(m["id"], {}),
               "sharp_alt": alt.get(m["id"], {})}
        # Skuggkällor (Matchbook) når aldrig payloaden: inte värdemotorn
        # (som annars hade räknat dem som bok), inte steam/notiser/ledger,
        # inte UI:t. Serien ligger kvar i DB för det frysta shadow-facitet.
        for shadow_src in oddset_value.SHADOW_SOURCES:
            row["odds"].pop(shadow_src, None)
            row["movement"].pop(shadow_src, None)
        if m["id"] in conflicts:
            row["data_conflict"] = {
                "kind": "identity",
                "reasons": conflicts[m["id"]],
                "message": (
                    "Källidentiteten är i karantän. Odds visas för felsökning "
                    "men inga signaler, modeller eller facitrader skapas."),
            }
        if m["league"] in RESEARCH_LEAGUE_KEYS:
            row["research"] = True
        out.append(row)
    out.sort(key=lambda r: (r.get("start") or "9", r["id"]))
    oddset_value.attach_value(out)
    oddset_value.attach_steam(out)
    for m in out:   # internt underlag för värdemotorn — inte API-last
        # Synlig ≠ actionable: ordinarie payloaden bär inga värde-/Kelly-
        # underlag för forskningsligor (V2.2:s dom är inte fälld).
        if not include_research and m.get("research"):
            m.pop("value", None)
    if not light:
        try:
            from . import oddset_data
            for mid, ab in oddset_data.get_absences(store, ids).items():
                next(m for m in out if m["id"] == mid)["absences"] = ab
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import oddset_data, oddset_model
            oddset_model.attach_model(
                store, [m for m in out if not m.get("data_conflict")],
                allowed_leagues=oddset_data.MODEL_LEAGUES)
            if include_research:
                from . import oddset_v22
                oddset_model.attach_model(
                    store, [m for m in out if not m.get("data_conflict")],
                    allowed_leagues=oddset_data.RESEARCH_MODEL_LEAGUES,
                    fit_pools=oddset_v22.FIT_POOLS)
        except Exception:  # noqa: BLE001 — modellen (amber) får aldrig fälla listan
            pass
    for m in out:
        # Alt-linjerna behövs ovan för samma-linje-transparensen, men hela
        # rålagret ska inte blåsa upp API-payloaden.
        m.pop("sharp_alt", None)
        if compact_movement:
            for markets in (m.get("movement") or {}).values():
                for signs in (markets or {}).values():
                    for series in (signs or {}).values():
                        if isinstance(series, dict):
                            series.pop("pts", None)
        if not include_movement:
            m.pop("movement", None)
        # Efter att värde/anchor2 räknats ovan — se UI_HIDDEN_SOURCES.
        for source in hide_sources:
            (m.get("odds") or {}).pop(source, None)
            (m.get("movement") or {}).pop(source, None)
        # Per-tecken-presence behövs när värdet räknas ovan men duplicerar
        # marknadens tider/status i JSON och används inte av klienten.
        for markets in (m.get("odds") or {}).values():
            for market in (markets or {}).values():
                if isinstance(market, dict):
                    market.pop("selections", None)
    visible_leagues = [
        league for league in LEAGUES
        if include_research or league["key"] in VISIBLE_LEAGUE_KEYS
    ]
    # `oddset_source_health` har PK (source, league, scope) och skriver över
    # sig själv — den städas ALDRIG. En urkopplad källa ligger därför kvar för
    # evigt och åldras tyst till "fel" i UI:t: Sofascore stod som livekälla
    # med sin sista kontroll 16:34Z timmar efter att den kopplats bort
    # (2026-08-06), och Betinia låg kvar sedan 2026-07-24 då den ersattes av
    # ninjacasino. Filtret härleds ur källistorna i stället för att räknas upp,
    # så nästa bortkoppling städar sig själv.
    health = [row for row in store.oddset_source_health()
              if row.get("source") in active_sources()]
    if not include_research:
        health = [
            row for row in health
            if (row.get("league") in VISIBLE_LEAGUE_KEYS or
                row.get("scope") == "live")
        ]
    leagues_out = []
    for lg in visible_leagues:
        entry = {"key": lg["key"], "name": lg["name"]}
        if lg.get("research_only"):
            entry["research"] = True
        leagues_out.append(entry)
    total_matches = len(out)
    league_counts: dict[str, int] = {}
    for match in out:
        league = match.get("league")
        if league:
            league_counts[league] = league_counts.get(league, 0) + 1
    if limit is not None:
        out = out[:max(0, limit)]
    return {"matches": out,
            "total_matches": total_matches,
            "league_counts": league_counts,
            "leagues": leagues_out,
            "last_run": store.meta_get("oddset_last_run"),
            "source_health": health,
            # Vilka källor som FÖRVÄNTAS finnas. UI:t hade en egen hårdkodad
            # lista och syntetiserade en "saknas"-rad (ok:false) för varje
            # källa backend inte skickade — så en urkopplad källa gick från
            # "gammal" till "FEL" i stället för att försvinna. Två listor som
            # ska hållas synkade för hand är samma bugg en gång till; backend
            # äger listan och UI:t följer den.
            "active_sources": sorted(active_sources()),
            "passive_sources": sorted(passive_sources())}


def dashboard_payload(store: Storage) -> dict:
    """Litet Idag-underlag utan modellfit, frånvaro eller råa prisserier.

    Dashboarden behöver bara kunna välja de tre bästa värdesignalerna och
    rörelserna samt visa forskningsligornas antal. Att skicka Oddset-vyns
    fulla payload dit kostade ~2,4 MB och tvingade mobilen att parsa tusentals
    historiska prispunkter som aldrig renderades på startsidan.
    """
    payload = matches_payload(store, light=True)
    matches = []
    for match in payload["matches"]:
        matches.append({
            key: match.get(key)
            for key in ("id", "home", "away", "start", "league",
                        "research", "value", "steam")
            if match.get(key) is not None
        })
    return {
        "matches": matches,
        "leagues": payload["leagues"],
        "last_run": payload.get("last_run"),
    }
