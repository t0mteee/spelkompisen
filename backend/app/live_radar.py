"""Shadow-radar för livefotboll: chansskapande som överstiger utdelningen.

Radarn är informationsstöd, inte en spelmodell. Den läser separata,
kumulativa serier från Flashscore, FotMob och Sofascore och visar en försiktig
xG- eller proxyflagga. Modulen läser inga liveodds; den separata
``live_signal_ledger`` observerar Kambi, Ninja och Pinnacle när en synlig
signal först uppstår. Inga automatiska spel/notiser skapas.
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
# v5 (2026-08-02): LAGIDENTITETEN ändrades tre gånger under v4:s första halvdygn
# och resultathistoriken under modellen byttes ut. Trösklarna är orörda, men
# vilka matcher som kan ge signal — och vilka som får odds och facit — är en
# annan datagenererande process än den v4 startade med:
#   1. `_same_team` slog ihop Los Angeles FC med Los Angeles Galaxy (falsk merge
#      av två MLS-klubbar som spelar samtidigt); spärrad i LIVE_TEAM_REJECTED.
#   2. MLS-alias (LA Galaxy, Atlanta Utd) och svenska IFK-klubbar länkade inte,
#      vilket gav dubbla journalkort där odds hamnade på den ena raden och facit
#      på den andra — matchen bidrog med noll trots att båda delarna fanns.
#   3. 588 dubblerade resultatrader slogs ihop i `oddset_results`.
# v4:s 16 rader (varav 4 kända dubbletter) behålls som historik och blandas
# aldrig med v5. Koherensvakten är OFÖRÄNDRAD — den mättes 2026-08-02 och gör
# rätt: skewen ligger mest åt hållet där ställningen är äldre än statistiken,
# vilket skulle fabricera "hög xG men inget mål".
RADAR_V1_VERSION = "chance-gap-shadow-v1"
RADAR_V2_VERSION = "chance-gap-shadow-v2"
RADAR_V3_VERSION = "chance-gap-shadow-v3"
RADAR_V4_VERSION = "chance-gap-shadow-v4"
RADAR_V5_VERSION = "chance-gap-shadow-v5"
RADAR_V6_VERSION = "chance-gap-shadow-v6"
RADAR_V7_VERSION = "chance-gap-shadow-v7"
RADAR_V8_VERSION = "chance-gap-shadow-v8"
RADAR_V9_VERSION = "chance-gap-shadow-v9"
RADAR_V10_VERSION = "chance-gap-shadow-v10"
RADAR_VERSION = RADAR_V10_VERSION

# En observation som inte bevisligen hör till någon kohort. Se `cohort_for`.
RADAR_TRANSITIONAL = "transitional"

# DEKLARERADE kohortstarter — avsikt, frysta före driftsstart.
# ÄNDRA ALDRIG en gräns som passerats.
RADAR_V3_STARTED_AT = "2026-08-01T08:00:00Z"
RADAR_V4_STARTED_AT = "2026-08-01T21:00:00Z"
RADAR_V5_STARTED_AT = "2026-08-03T06:00:00Z"
RADAR_V6_STARTED_AT = "2026-08-06T16:45:00Z"
# v7 (2026-08-07): proxysignalens aktivering bytte `skott i box` (43 %
# täckning) mot `farliga skott` = på mål + blockerade (100 %). Tröskelvärdena
# är oförändrade — det är ett fält som byts, inte en ny frihetsgrad. Före
# bytet tillförde proxyn NOLL matcher utöver xG-signalen och 59 % av
# matcherna kunde aldrig få en signal. Förregistrering med mätningar:
# docs/radar-proxy-v7-forregistrering-2026-08-07.md
RADAR_V7_STARTED_AT = "2026-08-06T21:40:00Z"
# v8 (2026-08-09): tre nya ordinarie toppligor ändrar radarns population och
# kan även påverka vilka matcher som ryms under providertaken. Trösklar,
# källval, identitet och signalmått är oförändrade. Scopeändringen är ändå en
# ny datagenererande process, så v7 får inte blandas med de nya ligorna.
# Koden deployades före den runda gränsen; captures före 17:15Z blev då
# transitional enligt cohort_for och den rena v8-kohorten började exakt där.
RADAR_V8_STARTED_AT = "2026-08-09T17:15:00Z"
# v9 (2026-08-09): Bolivias División Profesional läggs till. Island är ingen
# scopeändring — Besta deild fanns redan i hela kedjan och verifierades på
# nytt. Endast populationen ändras; trösklar/providers/identitet är frysta.
RADAR_V9_STARTED_AT = "2026-08-09T18:00:00Z"
# v10 (2026-08-18): ROI-priset byter från enbart SvS/Kambi till högsta öppna
# Över-pris på exakt samma lina bland SvS, Ninja/Altenar och en tillräckligt
# färsk Pinnacle-observation. Varje källsvar sparas separat. Signaltrösklarna
# är oförändrade, men ROI-processen är ny och får därför en ren kohort.
RADAR_VERSION_STARTED_AT = "2026-08-18T00:00:00Z"

# OBSERVERADE växlingar — när koden faktiskt bytte.
#
# Konstanterna ovan är handskrivna och har INGET orsakssamband med deployen:
# insamlingsjobben startar en ny Python-process varje tick och kör ur
# arbetskopian, så en versionsbump gäller i samma sekund filen sparas — inte
# när den committas och inte vid `*_STARTED_AT`. Uppmätt 2026-08-05 hade de
# glidit isär åt båda hållen: v3 bakåtdaterad ~3,5 h (447 v2-producerade
# ögonblick låg i v3) och v5 framåtdaterad ~16 h (2 168 v5-producerade
# ögonblick låg i v4 — 57 % av hela v4-kohorten).
#
# Journalen daterar den verkliga växlingen: den stämplar `RADAR_VERSION` vid
# skrivning och `recorded_at` ligger 1–9 s efter `captured_at`. Paret nedan är
# (sista observation av föregående kod, första av den nya). DÄREMELLAN vet vi
# inte vilken kod som körde — det fönstret är transitional, aldrig gissat.
#
# BEVISHORISONT: journalens första rad är 2026-08-01T01:02:15Z. Allt före den
# (17 272 v2-märkta ögonblick, inklusive en v1→v2-växling) går INTE att
# validera. De behåller sin deklarerade etikett med förbehåll i
# docs/db-atgarder.md — en påhittad transitional-etikett vore inte ärligare.
RADAR_EVIDENCE_FROM = "2026-08-01T01:02:15Z"
RADAR_OBSERVED_SWITCHES = (
    (RADAR_V2_VERSION, RADAR_V3_VERSION,
     "2026-08-01T11:32:20Z", "2026-08-01T11:47:15Z"),
    (RADAR_V3_VERSION, RADAR_V4_VERSION,
     "2026-08-01T18:57:06Z", "2026-08-02T00:22:05Z"),
    (RADAR_V4_VERSION, RADAR_V5_VERSION,
     "2026-08-02T13:32:04Z", "2026-08-02T14:07:05Z"),
    (RADAR_V5_VERSION, RADAR_V6_VERSION,
     "2026-08-06T16:44:19Z", "2026-08-06T16:45:15Z"),
    (RADAR_V6_VERSION, RADAR_V7_VERSION,
     "2026-08-06T21:08:57Z", "2026-08-07T12:06:57Z"),
    (RADAR_V7_VERSION, RADAR_V8_VERSION,
     "2026-08-09T16:54:12Z", "2026-08-09T17:07:03Z"),
    # Ett äldre varv hann skriva v8 efter att första v9-processen startat.
    # Gränsen använder därför sista v8 och första v9 DÄREFTER; hela
    # processöverlappet är transitional, aldrig tilldelat genom gissning.
    (RADAR_V8_VERSION, RADAR_V9_VERSION,
     "2026-08-09T17:24:10Z", "2026-08-09T17:25:07Z"),
)
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
    #
    # KFUM hör däremot HIT: resultathistoriken har bara `kfum oslo` (74 rader,
    # noll `kfum`), så modellidentiteten är hel. Det är FotMob som ensam skriver
    # `KFUM`, och enordsspärren — den som stoppar `Inter`↔`Inter Miami` —
    # blockerade länken. Bevisat par 2026-08-02: samma liga, samma motståndare
    # (Kristiansund) och samma avspark 15:00Z.
    "kfum": "kfum oslo",
    # Poolkupongernas livepris (2026-08-02): SvS skriver `Ålesund` och
    # `Sarpsborg`, Kambi `Aalesund` och `Sarpsborg 08`. Å→Aa är norsk/dansk
    # translitteration som `norm_team` inte kan känna till, och enordsspärren
    # stoppar suffixet. Båda entydiga i norsk fotboll på den här nivån.
    "alesund": "aalesund",
    "sarpsborg": "sarpsborg 08",
    # SvS skriver `PSV Eindhoven`, Kambi/Pinnacle `PSV ` (med blanksteg).
    # Normaliserat blir det `psv` mot `psv eindhoven`, och enords-spärren
    # kräver minst fyra tecken innan prefix tillåts — `psv` är tre. Spärren ska
    # INTE lättas: historiken rymmer `aik`, `odd`, `lyn`, `qpr` där en lösare
    # regel vore farlig. PSV är entydigt. Utan aliaset saknade PSV–AZ livepris
    # och hela Europatipsets chansberäkning uteblev (2026-08-02).
    "psv": "psv eindhoven",
    # Topptipset 4260 (2026-08-11): SvS skriver `Olympiakos`, Kambi
    # `Olympiakos Pireus`. Enordsspärren tillåter bara svensk genitiv, så
    # `olympiakos` mot `olympiakos pireus` föll — och utan länk saknade
    # Nijmegen–Olympiakos livepris mitt under matchen. Samma klass som PSV
    # ovan: entydig klubb, ren presentationsskillnad.
    "olympiakos pireus": "olympiakos",
    # Samma kväll: SvS skriver `Sparta Prag`, Flashscore `Sparta Prague (Cze)`.
    # Svensk, engelsk och tjeckisk stavning av staden; prefixregeln kräver
    # ordgräns och `prag`/`prague`/`praha` delar ingen. `sparta prague` fanns
    # redan mappad till den kanoniska `sparta praha` — det var SvS svenska form
    # som saknades, så den måste peka på SAMMA kanon och inte introducera en
    # tredje. Utan den saknade Lyon–Sparta Prag matchminut mitt i matchen.
    "sparta prag": "sparta praha",
    # Systematisk genomgång 2026-08-02 av ALLA olänkade par med samma liga och
    # samma avspark (13 av 24 kontrollerade). Kanonisk form är den som redan
    # finns i `oddset_results`, så signal↔facit-joinen träffar. Nycklarna är
    # LIVE-normaliserade, alltså efter att landssuffixet `(Cze)` strippats.
    #
    # Norska föreningsformer som `_NOISE` inte rymmer (`il` = idrettslag) och
    # klubbnamn som Flashscore kortar:
    "hodd": "hodd il",
    "ranheim": "ranheim il",
    "sogndal": "sogndal il",
    "sandnes": "sandnes ulf",
    # æ→a i CHARMAP men Flashscore skriver `ae`; aliaset pekar på HELA den
    # kanoniska formen eftersom `stabak` är enordigt och enords-spärren då
    # bara tillåter genitiv.
    "stabaek": "stabak fotball",
    # Europacupernas kvalomgång — källorna använder engelskt, inhemskt och
    # förkortat namn om vartannat:
    "sparta prague": "sparta praha",
    "lyon": "olympique lyonnais",
    "din zagreb": "dinamo zagreb",
    "olympiacos piraeus": "olympiacos",
    "nijmegen": "nec nijmegen",
    "h beer sheva": "hapoel beer sheva",
    "royale union sg": "royale union saint gilloise",
    "union st gilloise": "royale union saint gilloise",
    # 2026-08-06, sedd som dubblett i Live-vyn direkt efter v6-omläggningen:
    # Flashscore skriver klubben på ENGELSKA (`FC Copenhagen`) där FotMob
    # skriver den på danska (`FC København`). Normaliserat blir det
    # `copenhagen` mot `kobenhavn` — två strängar utan gemensam delsträng.
    # En översättning kan aldrig härledas ur tecknen, så det MÅSTE vara ett
    # observerat alias; kontextregeln löser bara kortnamn och förkortningar.
    # Kanonisk form är `kobenhavn` (den enda i `oddset_results`).
    "copenhagen": "kobenhavn",
    # Samma kväll: Flashscore kortar `Győri ETO` till bara `Gyor` (staden).
    # Aliaset `gyori eto` fanns sedan 2026-07-30 men fångar inte stadsformen.
    "gyor": "eto gyor",
    # `Inter Escaldes` ↔ `Inter Club d'Escaldes`: ett insatt ord OCH
    # apostrofen som blir `descaldes`. Varken kortnamns- eller
    # förkortningsregeln når det, och `atletic club escaldes` finns i samma
    # liga — alltså ska ingen generell regel gissa här.
    "inter escaldes": "inter club descaldes",
    # 2026-08-05, funnen av `cli.py lanklucka` efter att detektorn lagats.
    # Flashscore ensam skriver `Varberg`; Sofascore `Varbergs BoIS`, FotMob
    # `Varbergs BoIS FC`. Genitiv-plus-suffix faller mellan reglerna nedan:
    # `varberg` är enordigt, så bara genitivregeln gäller, och `varbergs`
    # räcker inte mot `varbergs bois`. Resulthistoriken är HEL (77 rader
    # `varbergs bois`, noll `varberg`, `oddset_result_stats` likaså), alltså
    # ren providerpresentation och inte en modellidentitetsfråga.
    "varberg": "varbergs bois",
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

# Sharp-/live-ligor utanför modellscopet. Direkt i TARGET_UT i stället för
# SOFA_UT: den senare ingår i V2.2:s frysta featurefingeravtryck.
# Turneringarna är verifierad fotboll med aktuella säsonger och lag hos
# Sofascore; Besta deild lades till explicit vid v9-verifieringen.
for _league_ut, _league_key in ((188, "bestadeild"),
                                (39, "danish_superliga"),
                                (38, "belgian_pro_league"),
                                (238, "primeira_liga"),
                                (16736, "bolivian_primera")):
    TARGET_UT[_league_ut] = _league_key

# Taket delas av ALLA ligor, så en lördag med 43 behöriga träningsmatcher kunde
# tränga ut Allsvenskan helt — och urvalet blev det Sofascore råkade returnera
# först. Riktiga ligor går därför före träningsmatcher, och inom gruppen väljs
# de matcher som har mest kvar att spela (en match i 85:e minuten kan inte längre
# ge en signal).
LEAGUE_PRIORITY = {"allsvenskan": 0, "superettan": 0, "eliteserien": 0,
                   "obosligaen": 0, "bestadeild": 0, "mls": 0,
                   "premier_league": 0, "serie_a": 0,
                   "la_liga": 0, "bundesliga": 0,
                   "danish_superliga": 0, "belgian_pro_league": 0,
                   "primeira_liga": 0, "bolivian_primera": 0,
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

    Räcker inte båda lagen prövas ETT lag entydigt (se `_one_sided_friendly`).
    """
    for match in known:
        known_home, known_away = match.get("home"), match.get("away")
        if ((_same_team(known_home, home) and
             _same_team(known_away, away)) or
            (_same_team(known_home, away) and
             _same_team(known_away, home))) and \
                _friendly_time_ok(match, start_ts):
            return True
    return _one_sided_friendly(home, away, start_ts, known)


FRIENDLY_WINDOW_S = 2 * 3600
# Ett lag är svagare identitetsbevis än två. Argumentet "ett lag spelar en
# match i taget" håller bara runt samma avspark, inte över hela det tvåtimmars-
# fönster som används när BÅDA lagen redan stämmer. 15 minuter täcker källornas
# observerade avrundning/ombokning utan att länka två separata träningsmatcher.
ONE_SIDED_FRIENDLY_WINDOW_S = 15 * 60


def _friendly_time_ok(match: dict, start_ts: Optional[int], *,
                      window_s: int = FRIENDLY_WINDOW_S,
                      require_known: bool = False) -> bool:
    """Ligger Oddset-matchens avspark inom fönstret?

    Två matchande lag får behålla den äldre toleransen att en tid saknas. För
    den ensidiga regeln är tiden däremot själva identitetsbeviset: båda måste
    finnas och gå att tolka. En trasig tid är aldrig samma sak som en känd tid.
    """
    if start_ts is None or not match.get("start"):
        return not require_known
    try:
        parsed = dt.datetime.fromisoformat(
            match["start"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        known_start = parsed.timestamp()
        observed_start = int(start_ts)
    except (TypeError, ValueError, OverflowError):
        return False
    return abs(known_start - observed_start) <= window_s


def _one_sided_friendly(home: str, away: str, start_ts: Optional[int],
                        known: list[dict]) -> bool:
    """ETT lag räcker när avsparken är känd och kandidaten är ENTYDIG.

    Samma resonemang som steg 3 i `_linked_series`: ett lag spelar en match i
    taget, så om exakt en Oddset-träningsmatch i samma tidslucka delar ett lag
    med den här kan de omöjligen vara olika matcher. Det avskaffar aliasjakten
    på providerns kortnamn — och den jakten var oändlig. Uppmätt på dagsfeeden
    2026-08-09: av 27 träningsmatcher föll 15 på tvåsidig namnlikhet, varav 6
    var uppenbart samma match som en Oddset-rad (`Atl. Madrid` mot `Atlético
    Madrid`, `Johor DT` mot `Johor Darul Takzim`, `Ath Bilbao` mot `Athletic
    Bilbao`, `Monaco` mot `AS Monaco`, `Sporting Lokeren` mot `Lokeren-Temse`,
    `Inter U23` mot `Internazionale U23`). Noll av dem var tvetydiga. Bland de
    fällda fanns Manchester City och Chelsea — båda föll på MOTSTÅNDARENS namn,
    aldrig sitt eget.

    Säkerheten ligger i anropsstället och får inte lyftas ut: `known` är redan
    filtrerad till träningsmatcher, avsparken måste vara känd på BÅDA sidor,
    och två kandidater betyder avslag i stället för gissning. Truppmarkörer
    (U23/B/women) spärras av `_same_team` som vanligt.

    Konsekvensen av ett falskt positivt är dessutom liten och känd: spärren
    styr RÄCKVIDD, inte pris. En felsläppt match kostar ett extra statistik-
    anrop och en shadowrad — den kan aldrig länka ett odds till fel match,
    eftersom livekortets odds hämtas i ett separat steg som gör sin egen
    identitetskontroll (`no_canonical_match`).
    """
    if start_ts is None:
        return False
    hits = [match for match in known
            if _friendly_time_ok(
                match, start_ts, window_s=ONE_SIDED_FRIENDLY_WINDOW_S,
                require_known=True)
            and (_same_team(match.get("home"), home)
                 or _same_team(match.get("away"), home)
                 or _same_team(match.get("home"), away)
                 or _same_team(match.get("away"), away))]
    return len(hits) == 1


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
        "shots_blocked_home", "shots_blocked_away",
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
    #
    # v7 (2026-08-07, docs/radar-proxy-v7-forregistrering-2026-08-07.md):
    # villkoret krävde `skott i box`, som bara finns i 43 % av matcherna —
    # exakt de matcher som ändå har xG. Proxyn tillförde därför NOLL matcher
    # utöver xG-signalen, och 59 % av matcherna kunde aldrig få någon signal
    # alls. `farliga skott` = på mål + blockerade har 100 % täckning och är
    # nära utbytbart: korrelation 0,890 mot skott i box, och samma svar vid
    # tröskel ≥8 i 91 % av 1 342 observationer. Tröskelvärdena är OFÖRÄNDRADE
    # — det är ett fält som byts, inte en ny frihetsgrad.
    proxy = []
    for side in sides:
        proxy.append(
            _num(current, f"big_chances_{side}") * 0.40
            + _num(current, f"shots_on_{side}") * 0.12
            # blockerat skott var på väg mot mål: vikt mellan `på mål` och
            # `i box`, inte en egen kalibrering
            + _num(current, f"shots_blocked_{side}") * 0.05
            + _num(current, f"shots_inside_{side}") * 0.025
            + _num(current, f"touches_box_{side}") * 0.008)
    gaps = [proxy[i] - goals[i] for i in range(2)]
    index = 0 if gaps[0] >= gaps[1] else 1
    side = sides[index]
    big = int(_num(current, f"big_chances_{side}"))
    on_target = int(_num(current, f"shots_on_{side}"))
    dangerous = int(_num(current, f"shots_on_{side}")
                    + _num(current, f"shots_blocked_{side}"))
    active = (20 <= minute <= 78 and remaining >= 12 and
              (big - goals[index] >= 1.5 or
               (on_target - goals[index] >= 5 and dangerous >= 8)))
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
            (f"{team}: {big} stora chanser, {on_target} skott på mål "
             f"men {int(goals[index])} mål"
             if big else
             # Utan stora chanser är `farliga skott` det som bär villkoret —
             # då ska texten säga just det, inte ett nollvärde.
             f"{team}: {on_target} skott på mål och {dangerous} farliga "
             f"skott men {int(goals[index])} mål")
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


def declared_version_at(observed_at: str) -> str:
    """Vilken kohort som DEKLARERAT äger observationsögonblicket."""
    observed = _parse_iso(observed_at)
    for version, start in ((RADAR_V10_VERSION, RADAR_VERSION_STARTED_AT),
                           (RADAR_V9_VERSION, RADAR_V9_STARTED_AT),
                           (RADAR_V8_VERSION, RADAR_V8_STARTED_AT),
                           (RADAR_V7_VERSION, RADAR_V7_STARTED_AT),
                           (RADAR_V6_VERSION, RADAR_V6_STARTED_AT),
                           (RADAR_V5_VERSION, RADAR_V5_STARTED_AT),
                           (RADAR_V4_VERSION, RADAR_V4_STARTED_AT),
                           (RADAR_V3_VERSION, RADAR_V3_STARTED_AT)):
        if observed >= _parse_iso(start):
            return version
    return RADAR_V2_VERSION


def produced_by_at(observed_at: str) -> Optional[str]:
    """Vilken KOD som producerade en historisk observation.

    None inne i ett observerat växlingsfönster (vi vet inte) och None före
    bevishorisonten (journalen fanns inte). Används bara för rader som saknar
    `radar_version`; nya rader bär den själva.
    """
    observed = _parse_iso(observed_at)
    if observed < _parse_iso(RADAR_EVIDENCE_FROM):
        return None
    for previous, following, last_old, first_new in RADAR_OBSERVED_SWITCHES:
        if observed <= _parse_iso(last_old):
            return previous
        if observed < _parse_iso(first_new):
            return None                      # inne i växlingen — obestämbart
    return RADAR_OBSERVED_SWITCHES[-1][1]


def cohort_for(observed_at: str,
               produced_by: Optional[str] = None) -> str:
    """Kohorten en observation tillhör — annars ``transitional``.

    En rad hör till vN bara om vN-KODEN producerade den OCH den observerades
    inom vN:s deklarerade fönster. Uppfylls inte båda är den transitional och
    ingår i INGEN kohort.

    Regeln implementerar det framåtfrysningen alltid siktade på: att få
    deploya mitt på dagen och ändå starta en ren kohort på en rund tid. Den
    var bara aldrig kodad — journalen struntade i konstanten och stämplade
    write-time-versionen, medan settlement läste konstanten och märkte samma
    fönster som föregående version. Att flytta sådana rader till FÖREGÅENDE
    kohort vore värre än att lämna dem: det är precis den kontaminering
    versionering finns för att förhindra.

    `produced_by` är radens egen `radar_version` när den finns. Saknas den
    (historik) härleds den ur journalens observerade växlingar; är den
    obestämbar där blir raden transitional.
    """
    declared = declared_version_at(observed_at)
    produced = produced_by or produced_by_at(observed_at)
    if produced is None:
        # Före bevishorisonten finns ingen journal att jämföra mot. Behåll den
        # deklarerade etiketten med förbehåll hellre än att hitta på.
        if _parse_iso(observed_at) < _parse_iso(RADAR_EVIDENCE_FROM):
            return declared
        return RADAR_TRANSITIONAL
    return declared if declared == produced else RADAR_TRANSITIONAL


def live_norm_team(value: str) -> str:
    """`norm_team` plus Flashscores landsetikett.

    Flashscore märker klubbar med landkod i internationella sammanhang, t.ex.
    `Chelsea (Eng)` och `Sparta Prague (Cze)`. Det är providerpresentation,
    inte lagidentitet, och gäller ALLA lag — regeln är generell, aldrig en
    lista över enskilda klubbar.

    MODULNIVÅ sedan 2026-08-05 därför att diagnostiken (`cli.py lanklucka`)
    mätte namnlikhet på rå `norm_team` medan länken kördes på den strippade
    formen. Suffixet drog då ner likheten under åtgärdströskeln, så exakt de
    par regeln var till för föll ur listan: `Mjällby (Swe)` ↔ `Mjällby AIF`
    fick 0,70 mot tröskeln 0,72 trots att namnen är identiska. Detektorn och
    länken MÅSTE se samma normaliserade namn — annars letar vakten efter en
    annan sorts fel än det som uppstår.
    """
    normalized = norm_team(value or "")
    tokens = [token for token in normalized.split()
              if not (token.startswith("(") and token.endswith(")") and
                      2 <= len(token[1:-1]) <= 3 and
                      token[1:-1].isalpha())]
    stripped = " ".join(tokens)
    if stripped == normalized:
        return stripped
    # ALIASET MÅSTE PRÖVAS IGEN EFTER STRIPPNINGEN (2026-08-06).
    # `norm_team` slår upp aliaset på HELA strängen, alltså på
    # `goteborg (swe)` — en nyckel som aldrig finns. Följden var att varje
    # alias tyst slutade gälla så snart providern satte dit en landskod:
    # `Goteborg (Swe)` ↔ `IFK Göteborg` låg som två kort i Conference League
    # samtidigt som testet för samma par var grönt, eftersom det testade
    # namnet UTAN kod. Ett alias får inte bero på om matchen råkar vara
    # internationell.
    return norm_team(stripped)


_SQUAD_MARKERS = frozenset({"b", "ii", "reserve", "reserves", "academy",
                            "youth", "women", "damer"})


def _squad(normalized: str) -> frozenset[str]:
    """Truppmarkörer i ett NORMALISERAT namn (`inter u23` → {'u23'}).

    Markörerna är IDENTITET, inte föreningsform: `Inter` och `Inter U23` är
    skilda lag som kan spela samtidigt. Delad av alla tre länkstegen — även
    det som bara kräver ETT matchande lag, där A-laget annars hade kunnat
    länkas till U23-truppens match mot samma motståndare.
    """
    return frozenset(
        token for token in normalized.split()
        if token in _SQUAD_MARKERS
        or (token.startswith("u") and token[1:].isdigit()))


def _same_team(a: str, b: str) -> bool:
    """Konservativ namnlänkning mellan livekällorna.

    `norm_team` klarar 'Degerfors' ↔ 'Degerfors IF' men inte svensk genitiv:
    'Djurgården' ↔ 'Djurgårdens IF' blir djurgarden ↔ djurgardens. Prefixregeln
    med minst fyra tecken täcker det utan att öppna för allmän likhetsmatchning.
    Ingen träff = matchen visas utan FotMob-data; vi gissar aldrig.
    """
    x, y = live_norm_team(a), live_norm_team(b)
    x, y = LIVE_TEAM_ALIASES.get(x, x), LIVE_TEAM_ALIASES.get(y, y)
    # Bekräftat olika klubbar stoppas FÖRE all likhetslogik. Hellre två kort
    # än att två verkliga matcher smälter ihop.
    if frozenset({x, y}) in LIVE_TEAM_REJECTED:
        return False
    if _squad(x) != _squad(y):
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


def _is_year(token: str) -> bool:
    """Ett rent fyrsiffrigt årtal — grundningsår i klubbnamn (`CFR 1907 Cluj`,
    `Sturm 1909 Graz`). Snävt med flit: `Schalke 04` och `Sarpsborg 08` har
    tvåsiffriga former som ÄR en del av namnet och rörs inte."""
    return len(token) == 4 and token.isdigit() and 1800 <= int(token) <= 2099


def _same_team_in_context(a: str, b: str) -> bool:
    """Svagare namnregel som BARA får användas med oberoende matchbevis.

    Internationellt spel har en egen namnkonvention: Flashscore skriver
    kortnamn + landskod (`Paide (Est)`, `Jagiellonia (Pol)`,
    `Univ. Craiova (Rou)`) där de andra skriver fullnamn (`Paide
    Linnameeskond`, `Jagiellonia Białystok`, `Universitatea Craiova`).
    Landskoden strippas redan av `live_norm_team`, men det som blir kvar är
    då ett ENORDSNAMN som är prefix av det andra — och enords-prefix är
    spärrat av goda skäl (`Inter` ≠ `Inter Miami`).

    Att i stället alias-lista klubbarna är en förlorad kapplöpning: varje ny
    kvalomgång drar in nya lag, och 2026-08-06 låg fyra matcher som dubbletter
    samtidigt. Regeln här löser klassen i stället för fallen.

    Den är säker endast tillsammans med kraven på anropsstället: samma liga,
    exakt samma avspark, en enda kandidat, och att MOTSTÅNDAREN redan matchat
    på den strikta regeln. Ett lag spelar en match i taget, så när allt det är
    uppfyllt finns ingen annan match kandidaten kan vara. `LIVE_TEAM_REJECTED`
    gäller fortfarande och prövas först.
    """
    x, y = live_norm_team(a), live_norm_team(b)
    x, y = LIVE_TEAM_ALIASES.get(x, x), LIVE_TEAM_ALIASES.get(y, y)
    if frozenset({x, y}) in LIVE_TEAM_REJECTED:
        return False
    if not x or not y:
        return False
    if _same_team(a, b):
        return True
    xs, ys = x.split(), y.split()
    # Truppmarkörer är identitet även här (`Inter` ≠ `Inter U23`).
    if _squad(x) != _squad(y):
        return False
    # Grundningsår är inte identitet. `CFR Cluj` ↔ `CFR 1907 Cluj` är samma
    # klass som kortnamnen ovan, bara med det extra ordet i mitten — och två
    # klubbar i SAMMA liga med samma avspark skiljs aldrig åt av ett årtal.
    # Strippas bara här, aldrig i den strikta regeln.
    xs = [t for t in xs if not _is_year(t)] or xs
    ys = [t for t in ys if not _is_year(t)] or ys
    if xs == ys:
        return True
    # Kortnamn: hela namnet är de första orden i det längre (`paide` ⊂
    # `paide linnameeskond`, `rapid` ⊂ `rapid wien`).
    short, long = (xs, ys) if len(xs) <= len(ys) else (ys, xs)
    if short == long[:len(short)]:
        return True
    # Förkortning: lika många ord, där varje ord är prefix av motsvarande
    # (`univ craiova` ⊂ `universitatea craiova`).
    return (len(xs) == len(ys)
            and all(p.startswith(q) or q.startswith(p)
                    for p, q in zip(xs, ys)))


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


def _candidates_for(match: dict, series: list[list[dict]],
                    same) -> list[tuple[list[dict], bool]]:
    """Serier som kan vara samma match, enligt den inskickade namnregeln.

    Liga och exakt avspark är ALLTID krav — `same` avgör bara namnfrågan.
    """
    out: list[tuple[list[dict], bool]] = []
    for captures in series:
        head = captures[-1]
        if head.get("league") != match.get("league"):
            continue
        if not _same_start(head, match):
            continue
        direct = (same(head.get("home"), match.get("home")) and
                  same(head.get("away"), match.get("away")))
        mirrored = (same(head.get("home"), match.get("away")) and
                    same(head.get("away"), match.get("home")))
        if direct or mirrored:
            out.append((captures, mirrored and not direct))
    return out


def _one_side_candidates(match: dict, series: list[list[dict]]
                         ) -> list[tuple[list[dict], bool]]:
    """Kandidater där ETT lag matchar och ligan/avsparken är identiska.

    Sista steget, och det starkaste beviset som inte är ett namn: **ett lag
    spelar en match i taget.** Delar två providerrader liga och exakt
    avsparkstid, och är ett av lagen samma, kan de omöjligen vara olika
    matcher — vad motståndaren råkar heta hos den andra providern spelar
    ingen roll.

    Det som gör steget nödvändigt är att namnklasserna aldrig tar slut:
    `Austria Vienna` ↔ `Austria Wien` är en översättning, och nästa kväll är
    det en translitteration eller en förkortning vi inte sett. Att jaga dem
    en och en med alias var precis det Saman tröttnade på.
    """
    out: list[tuple[list[dict], bool]] = []
    same = _same_team_in_context

    def squads_agree(left: str, right: str) -> bool:
        """Truppmarkörer får ALDRIG överbryggas av kontext.

        `Inter` mot `Como` och `Inter U23` mot `Como` är två skilda matcher
        som kan spelas samtidigt i samma liga. Att `Como` matchar räcker
        alltså inte — det lag som INTE matchar måste vara samma sorts trupp.
        """
        return _squad(live_norm_team(left or "")) == _squad(
            live_norm_team(right or ""))

    for captures in series:
        head = captures[-1]
        if head.get("league") != match.get("league"):
            continue
        if not _same_start(head, match):
            continue
        h_head, a_head = head.get("home"), head.get("away")
        h_match, a_match = match.get("home"), match.get("away")
        direct = ((same(h_head, h_match) or same(a_head, a_match))
                  and squads_agree(h_head, h_match)
                  and squads_agree(a_head, a_match))
        mirrored = ((same(h_head, a_match) or same(a_head, h_match))
                    and squads_agree(h_head, a_match)
                    and squads_agree(a_head, h_match))
        if direct:
            out.append((captures, False))
        elif mirrored:
            out.append((captures, True))
    return out


def _linked_series(match: dict, series: list[list[dict]]
                   ) -> Optional[tuple[list[dict], bool]]:
    """Trestegslänkning — strikt, kontext, ett lag. Entydigt eller ingenting.

    Steg 1 är den vanliga `_same_team` på BÅDA lagen. Ger den träff är svaret
    klart — en strikt träff får aldrig konkurrera med en lösare, och två
    strikta träffar är tvetydighet som aldrig gissas.

    Steg 2 körs BARA när steg 1 gav noll kandidater och använder
    `_same_team_in_context` på båda lagen (kortnamn, förkortning, årtal).

    Steg 3 körs BARA när steg 2 också gav noll, och kräver att bara ETT lag
    matchar. Se `_one_side_candidates`: liga + exakt avspark + ett gemensamt
    lag utesluter att det är två olika matcher.

    Varje steg kräver EXAKT en kandidat. Två möjliga matcher i något steg
    betyder att vi inte vet, och då länkas ingen — samma disciplin som
    resultatidentitetens auto-merge.
    """
    for candidates in (_candidates_for(match, series, _same_team),
                       _candidates_for(match, series, _same_team_in_context),
                       _one_side_candidates(match, series)):
        if candidates:
            return candidates[0] if len(candidates) == 1 else None
    return None


def _fotmob_for(match: dict, series: list[list[dict]],
                claimed: Optional[set[int]] = None) -> Optional[list[dict]]:
    """Hitta FotMob-serien för en ankarmatch: samma liga, samma två lag.

    En provider-match får bara kopplas en gång. Om ankaret råkar innehålla
    dubbletter blir den kvarvarande FotMob-serien i stället ett eget kort,
    aldrig statistik på två olika matcher.
    """
    # Unikheten avgörs FÖRE claimed-filtret. Om två provider-events har samma
    # identitet får det första kortet aldrig godtyckligt "ta" den ena och
    # därmed göra den andra skenbart unik för nästa kort.
    hit = _linked_series(match, series)
    if hit is None:
        return None
    candidate, is_mirrored = hit
    if claimed is not None and int(candidate[-1]["fotmob_id"]) in claimed:
        return None
    if is_mirrored:
        # Spegelvänd träff: serien uttrycks i ankarets orientering så att
        # statistiken aldrig hamnar på fel lag. Se `_mirrored_capture`.
        return [_mirrored_capture(row) for row in candidate]
    return candidate


def _mirrored_capture(row: dict) -> dict:
    """Uttryck en providerrad i motsatt hemma/borta-orientering.

    Providrar är oense om hemmalaget på neutral plan (Sofascore `Udinese –
    Trabzonspor`, Flashscore/FotMob tvärtom, 2026-08-02). En länk som bara
    byter sida hade gjort lagens statistik omvänd — därför speglas VARJE
    sidoberoende fält, så serien blir exakt vad providern hade rapporterat om
    den delat ankarets orientering. Två namnkonventioner täcks: prefix
    (`home_score`) och suffix (`xg_home`).
    """
    out = dict(row)
    out["home"], out["away"] = row.get("away"), row.get("home")
    out["home_score"], out["away_score"] = (row.get("away_score"),
                                            row.get("home_score"))
    for key in row:
        if key.endswith("_home"):
            partner = f"{key[:-5]}_away"
            out[key], out[partner] = row.get(partner), row.get(key)
    return out


def _series_for(match: dict, series: list[list[dict]], id_key: str,
                claimed: set) -> Optional[list[dict]]:
    """Samma konservativa länkning som `_fotmob_for`, för valfri provider.

    Spegelvänd hemma/borta accepteras — källorna är bevisat oense om
    hemmalaget (Udinese–Trabzonspor låg som två kort 2026-08-02) — men då
    returneras serien TRANSPONERAD till ankarets orientering via
    `_mirrored_capture`, aldrig rå. Tvetydighet länkar aldrig.
    """
    hit = _linked_series(match, series)
    if hit is None:
        return None
    candidate, is_mirrored = hit
    if str(candidate[-1][id_key]) in claimed:
        return None
    if is_mirrored:
        return [_mirrored_capture(row) for row in candidate]
    return candidate


# `radar_version` MÅSTE ingå: journalen läser den ur den här vyn för att veta
# vilken KOD som producerade raden. Saknas den faller kohortbestämningen
# tillbaka på härledning ur observerade växlingar, och varje rad efter den
# sista kända växlingen blir felaktigt `transitional` — alltså raderad ur
# blindkohorten. Exakt det fel kohortregeln infördes för att stoppa.
_FOTMOB_VIEW_KEYS = (
    "fotmob_id", "capture_version", "league", "tournament",
    "home", "away", "start_at", "home_score", "away_score",
    "xg_home", "xg_away", "xgot_home", "xgot_away",
    "big_chances_home", "big_chances_away",
    "shots_home", "shots_away",
    "shots_on_home", "shots_on_away",
    "shots_inside_home", "shots_inside_away",
    "minute", "captured_at", "radar_version",
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
    "shots_off_home", "shots_off_away",
    "shots_blocked_home", "shots_blocked_away",
    "touches_box_home", "touches_box_away",
    "saves_home", "saves_away",
    "possession_home", "possession_away",
    "minute", "stage_label", "stage_name", "captured_at", "radar_version",
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
    blocked = pair("shots_blocked")
    inside = pair("shots_inside")
    touches = pair("touches_box")
    complete_pairs = sum((big, on_target, blocked, inside, touches))
    # Nivå 2 är "raden kan bära en proxysignal", så villkoret MÅSTE vara
    # detsamma som proxyns aktivering. Sedan v7 är den grenen `på mål +
    # blockerade`; med `inside` kvar här hade en rad som visst kan signalera
    # rankats som partiell och kunnat döljas av en sämre källa.
    if big and on_target and (blocked or inside):
        return (3, complete_pairs)
    if big or (on_target and (blocked or inside)):
        return (2, complete_pairs)
    proxy_keys = ("big_chances_home", "big_chances_away",
                  "shots_on_home", "shots_on_away",
                  "shots_blocked_home", "shots_blocked_away",
                  "shots_inside_home", "shots_inside_away",
                  "touches_box_home", "touches_box_away")
    reported = sum(row.get(key) is not None for key in proxy_keys)
    return (1, reported) if reported else (0, 0)


# Livekällorna i radarn, i stigande prioritet vid LIKA fälttäckning.
# Sofascore togs bort 2026-08-06 (falska xG-nollor, se ankarloopen i payload).
# Den samlar oförändrat resultat, modellstatistik och frånvaro på andra håll —
# konstanten gäller enbart radarns livevisning och dess källhälsorad.
LIVE_SOURCES = ("flashscore", "fotmob")
_SOURCE_PRIORITY = {"fotmob": 1, "flashscore": 2}


def _best_source(candidates: list[tuple[str, list[dict]]]
                 ) -> tuple[str, list[dict]]:
    """Välj källa på schema/täckning + fast prioritet, aldrig på signalvärde."""
    return max(candidates, key=lambda item: (
        _stats_rank(item[1][-1]), _SOURCE_PRIORITY[item[0]]))


def _signal_with_basis(provider: str, captures: list[dict], view_keys,
                       match_fallback: Optional[dict] = None,
                       fallback_source: Optional[str] = None
                       ) -> tuple[dict, dict]:
    """Signal och exakt per-fält-proveniens ur en providerserie.

    Chansmåtten kommer alltid från `provider`. Bara saknad minut/ställning får
    lånas från den verifierade motpartsraden, och UI:t får både det effektiva
    värdet och dess källa så att en fallback aldrig ser providerspecifik ut.

    `fallback_source` MÅSTE följa med raden. Den var hårdkodad till
    "sofascore" så länge Sofascore var enda tänkbara ankare; när Flashscore
    tog över den rollen (2026-08-06) hade en hårdkodning gjort proveniensen
    till en ren lögn — basis hade pekat ut en källa som inte ens lästes.
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
                source = fallback_source
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
    """Signal + visningsfält ur en enda, sammanhängande FotMob-serie.

    Fallbacken är Flashscore-ankaret: bara minut/ställning, aldrig statistik.
    """
    return _signal_with_basis(
        "fotmob", captures, _FOTMOB_VIEW_KEYS, match_fallback, "flashscore")


def _flashscore_signal(captures: list[dict],
                       match_fallback: Optional[dict] = None
                       ) -> tuple[dict, dict]:
    """Signal + visningsfält ur en enda, sammanhängande Flashscore-serie.

    Samma kontrakt som FotMob-vägen: chansmåtten kommer UTESLUTANDE ur den
    egna serien, medan klocka/ställning får lånas per fält från den redan
    verifierade FotMob-länken när Flashscores stadieklocka är okänd. Det är
    inte en kantfall-detalj: minuten HÄRLEDS ur stadiets starttid, så halvtid
    och förlängning ger `None` by design — och då är motpartens klocka
    skillnaden mellan ett läsbart kort och ett tomt. Lånet påverkar aldrig xG
    eller skott.
    """
    return _signal_with_basis(
        "flashscore", captures, _FLASHSCORE_VIEW_KEYS,
        match_fallback, "fotmob")


def _frozen_stage(label: Optional[str]) -> Optional[str]:
    """Släpp bara igenom etiketter för stadier där klockan STÅR STILLA.

    UI:t visar etiketten i klockans ställe, så en etikett för ett stadium där
    klockan går ("2:a halvlek") skulle ersätta en minut som är sannare.
    Kolumnen bär historiska värden från när tabellen var bredare — de får
    inte läcka ut i vyn bara för att de ligger kvar i databasen.
    """
    from .flashscore import STAGE_LABEL
    return label if label in set(STAGE_LABEL.values()) else None


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
    fotmob_series = _fotmob_series(store, since)
    flashscore_series = _flashscore_series(store, since)
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
    # 30-minutersserie länkas till ett färskt ankarkort och bära signalen,
    # trots att samma serie hade dolts som fristående kort.
    fotmob_series = [captures for captures in fotmob_series
                     if _fresh_series(captures, now)]
    flashscore_series = [captures for captures in flashscore_series
                         if _fresh_series(captures, now)]
    matches = []
    claimed_fotmob: set[int] = set()

    # FLASHSCORE ÄR ANKARET sedan 2026-08-06. Sofascore var det tidigare, men
    # den kopplades ur radarn helt: uppmätt på europacupkvällen 2026-08-06
    # rapporterade den `xg_home=0.0, xg_away=0.0` för Paide–SK Rapid där
    # Flashscore hade 0.09 respektive 0.81. En nolla är inte saknad data — den
    # ser ut som en mätning, och kortet läste därför som "inga chanser skapade"
    # mitt i en match där bortalaget hade 0,81 xG. Sofascore lever kvar
    # oförändrad i resultat, modellstatistik och frånvaro; det här gäller
    # ENBART livevisningen.
    for fs in flashscore_series:
        current = fs[-1]
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        extra: dict = {"flashscore": {
            key: current.get(key) for key in _FLASHSCORE_VIEW_KEYS}}
        candidates = [("flashscore", fs)]
        fm = _fotmob_for(current, fotmob_series, claimed_fotmob)
        if fm:
            fm_current = fm[-1]
            claimed_fotmob.add(int(fm_current["fotmob_id"]))
            extra["fotmob"] = {
                key: fm_current.get(key) for key in _FOTMOB_VIEW_KEYS}
            candidates.append(("fotmob", fm))
        # Valet görs enbart på rapporterad fälttäckning och fast källprioritet.
        # Signalen räknas FÖRST EFTER valet, så ett dramatiskt värde kan aldrig
        # få en sämre provider att vinna.
        source, chosen = _best_source(candidates)
        if source == "fotmob":
            signal, _ = _fotmob_signal(chosen, current)
        else:
            # Flashscores klocka är None vid halvtid/förlängning (härledd ur
            # stadiets starttid). Är FotMob länkad lånas minut/ställning
            # därifrån — annars vore kortet minutlöst just i paus.
            signal, _ = _flashscore_signal(chosen, fm[-1] if fm else None)
        matches.append({
            **current,
            "event_id": f"flashscore:{current['flashscore_id']}",
            "stage_label": _frozen_stage(current.get("stage_label")),
            **extra,
            "signal": signal,
            "is_signal": signal["level"] in {"watch", "strong"},
        })

    # FotMob står på egna ben. Om Flashscore helt saknar en match men FotMob
    # har en färsk serie ska matchen ändå synas — det stänger den sista luckan
    # i löftet "stats finns → kort visas". Flashscore prövas INTE igen här:
    # varje Flashscore-serie fick redan sitt kort i ankarloopen ovan, och en
    # andra prövning skulle bara kunna skapa den dubblett den ska förhindra.
    # Det namespacade event-id:t kan aldrig krocka med ankarets nycklar.
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
        matches.append({
            **current,
            "event_id": f"fotmob:{fotmob_id}",
            "fotmob": view,
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
                   row.get("source") in LIVE_SOURCES]
    source_runs = {}
    for source in LIVE_SOURCES:
        checked = [row.get("checked_at") for row in live_health
                   if row.get("source") == source and row.get("checked_at")]
        if checked:
            source_runs[source] = max(checked)
    # `last_run` betyder att hela källgruppen har kontrollerats, inte bara att
    # den sist körda loopen är färsk. Minsta av varje källas senaste kontroll
    # är den konservativa gemensamma vattenstämpeln.
    if len(source_runs) == len(LIVE_SOURCES):
        combined_last_run = min(source_runs.values())
    else:
        # En delkällas färska tid får inte se ut som att HELA radarn körts.
        # De enskilda tiderna finns kvar i source_runs; gemensam watermark
        # förblir okänd tills alla aktiva livekällor faktiskt kontrollerats.
        combined_last_run = None
    return {
        "version": RADAR_VERSION,
        "mode": "shadow",
        "last_run": combined_last_run,
        # UI och diagnoser ska aldrig bära en egen kopia av källistan. Det var
        # så Sofascore stod kvar i texten efter att den kopplats ur radarn.
        "sources": list(LIVE_SOURCES),
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
                for src in LIVE_SOURCES),
        },
        # INGA TYSTA TAK: står här av samma skäl som i källhälsan — ett dolt
        # urval läser som "det här var allt som fanns live".
        "dropped": store.meta_get("live_radar_dropped") or "",
        "disclaimer": (
            "Informationsradar. Påverkar inte tips, Kelly, facit eller notiser."),
    }
