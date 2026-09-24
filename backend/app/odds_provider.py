"""Extern oddskälla via the-odds-api.com — komplement för matcher där Svenska
Spel ännu inte satt odds, och som *sharp-referens* (Pinnacle).

Aktiveras genom miljövariabeln ODDS_API_KEY (gratis nyckel: the-odds-api.com).
Utan nyckel är allt avstängt och endpoints svarar {"enabled": false}.

Matchning av lag mellan källorna är heuristisk:
* Landslag: Svenska Spel anger ISO-kod (t.ex. DEU) -> engelskt namn via pycountry,
  så "Tyskland" matchar "Germany".
* Klubbar: fuzzy namnmatchning (difflib).
Vi accepterar bara matchningar över en konfidenströskel och injicerar aldrig
osäkra odds — låg konfidens flaggas istället.
"""
from __future__ import annotations

import datetime as dt
import difflib
import functools
import gettext
import os
import re
import unicodedata
from typing import Optional

import httpx

try:
    import pycountry
except ImportError:  # pragma: no cover
    pycountry = None

API_BASE = "https://api.the-odds-api.com/v4"
SHARP_PREFERENCE = ("pinnacle", "betfair_ex_eu", "marathonbet")
HOME_AWAY_MIN = 0.60     # minsta likhet per sida
COMBINED_MIN = 0.72      # minsta snittlikhet
TIME_WINDOW_H = 36       # extern match måste starta inom X timmar från SS-matchen
# pool-name-v5: är SvS-avsparken känd får en Pinnacle-kandidat bara prövas om
# dess avspark ligger högst så här nära. Ett lag spelar en match i taget, så
# samma lag ett dygn senare (Finland–Spain 27 h före England–Spanien) är en
# annan match och får inte längre göra rätt rad tvetydig. 36 h gäller bara
# the-odds-api, diagnostikens sökfönster och vägen utan känd SvS-avspark.
POOL_ANCHOR_S = 15 * 60

# Football-specifika ISO->namn-överstyrningar där pycountry skiljer sig från
# hur oddsbolagen (Pinnacle m.fl.) skriver landslagsnamnen
_ISO_OVERRIDE = {
    "KOR": "South Korea", "PRK": "North Korea", "USA": "USA",
    "GBR": "England", "CZE": "Czech Republic", "RUS": "Russia",
    "IRN": "Iran", "BOL": "Bolivia", "VEN": "Venezuela",
    "CIV": "Ivory Coast", "CPV": "Cape Verde", "CUW": "Curacao",
    "COD": "DR Congo", "TUR": "Turkey", "MKD": "North Macedonia",
}


def api_key() -> Optional[str]:
    return os.environ.get("ODDS_API_KEY")


def enabled() -> bool:
    return bool(api_key())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\b(fc|if|sk|bk|fk|cf|sc|ac|fk|club|cd)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def english_name(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    if iso in _ISO_OVERRIDE:
        return _ISO_OVERRIDE[iso]
    if pycountry:
        c = pycountry.countries.get(alpha_3=iso) or pycountry.countries.get(alpha_2=iso)
        if c:
            return getattr(c, "common_name", None) or c.name
    return None


def _parse_time(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_apart(a: Optional[str], b: Optional[str]) -> Optional[float]:
    ta, tb = _parse_time(a), _parse_time(b)
    if ta is None or tb is None:
        return None
    return abs((ta - tb).total_seconds()) / 3600.0


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# Poolens egna bekräftade kortnamn. Ändra inte Oddsets/modellens globala
# alias för att rätta poolmatcharen. Evidens: täckningsrapport 2026-09-13
# och NameRuleTests (Svenska Spel ↔ Pinnacle).
POOL_MATCH_VERSION = "pool-name-v6"
_POOL_TEAM_ALIASES = {
    "leeds": "leeds united",
    "nottingham": "nottingham forest",
    "tottenham": "tottenham hotspur",
    "frankfurt": "eintracht frankfurt",
    "sabah masazir": "sabah",
    "hull": "hull city",
    "mainz": "mainz 05",
    # Stryktipset 4971: providerpar + samma avspark i egen diagnostik/odds.
    # Se överlämningen 2026-09-21. Endast poolen; modellalias är orörda.
    "coventry": "coventry city",
    "ipswich": "ipswich town",
    "newcastle": "newcastle united",
    "derby": "derby county",
    "lincoln": "lincoln city",
    "swansea": "swansea city",
    "blackburn": "blackburn rovers",
    "preston": "preston north end",
    # Topptipset 4346: samma motståndare/avspark, observerat Pinnacle-id
    # 1636640777 (2026-09-21). Endast poolen, inte modellens alias.
    "cuiaba esporte": "cuiaba",
    # pool-name-v5, belagt i Pinnacles index 2026-09-24 12:25Z: exakt avspark,
    # samma motståndare och namnet entydigt i indexet. Endast poolen.
    # Topptipset 4352: Nashville SC–Toronto FC 2026-09-27 00:30Z, id
    # 1636866540. SC-regeln gäller fortsatt generellt (Barcelona ≠ Barcelona SC).
    "nashville": "nashville sc",
    # Topptipset 4350: Once Caldas–Atletico Bucaramanga 2026-09-26 01:15Z,
    # id 1636734323. Atletico är inget klubbformsord (se nedan), därför alias.
    "bucaramanga": "atletico bucaramanga",
    # Topptipset 4351: Deportivo Pereira–Inter Bogota 2026-09-26 21:00Z, id
    # 1636816733 (klubben bytte namn från La Equidad 2025). SvS skriver
    # "Internacional de Bogota." och motståndaren "Pereira" (generiskt delnamn).
    "internacional de bogota": "inter bogota",
    # MEDVETET INTE alias: Aguilas (indexet har både Aguilas–Hercules i Spanien
    # och Aguilas Doradas i Colombia), Fortaleza (Fortaleza och Fortaleza
    # CEIF), America (Club America och America Mineiro). Samma klass som
    # Estudiantes: ett kortnamn som pekar på flera klubbar får inget globalt alias.
}
# Estudiantes är INTE ett globalt alias: La Plata, Caseros och Rio Cuarto
# är olika klubbar. Belägget gäller SvS-kortnamnet mot Lanus i 4346.
_POOL_CONTEXT_ALIASES = {("estudiantes", "lanus"): "estudiantes de la plata"}
_SQUAD_MARKERS = frozenset({"b", "ii", "reserve", "reserves", "academy",
                            "youth", "women", "damer"})
_norm_cache: dict[str, str] = {}
_rejected_pairs: set[frozenset] | None = None


def _norm_team(name: str) -> str:
    cached = _norm_cache.get(name)
    if cached is None:
        from .oddset import norm_team      # lat: oddset importerar pinnacle
        cached = norm_team(name)
        # SC kan skilja klubbar åt (Barcelona / Barcelona SC). Global
        # suffixstrippning får inte göra dem identiska i poolmatcharen.
        raw_tokens = re.findall(r"[a-z0-9]+", name.casefold())
        if "sc" in raw_tokens and "sc" not in cached.split():
            cached += " sc"
        cached = _POOL_TEAM_ALIASES.get(cached, cached)
        _norm_cache[name] = cached
    return cached


def _squad(normalized: str) -> frozenset[str]:
    return frozenset(token for token in normalized.split()
                     if token in _SQUAD_MARKERS
                     or (token.startswith("u") and token[1:].isdigit()))


def _rejected() -> set[frozenset]:
    global _rejected_pairs
    if _rejected_pairs is None:
        from .oddset_data import TEAM_REJECTED_LINKS
        _rejected_pairs = {frozenset(pair) for pairs in TEAM_REJECTED_LINKS.values()
                           for pair in pairs}
    return _rejected_pairs


def team_sim(a: Optional[str], b: Optional[str]) -> float:
    """Exakt/alias ger 1; obekräftade delnamn och olika trupper ger 0.

    Annan stavningslikhet bedöms med samma fuzzy-trösklar som tidigare.
    Ett delnamn får inte falla tillbaka till fuzzy efter att ha avvisats.
    """
    if not a or not b:
        return 0.0
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return 0.0
    if _squad(na) != _squad(nb):
        return 0.0
    if frozenset((na, nb)) in _rejected():
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.0
    return _ratio(na, nb)


def _best_side(candidates: list[str], target: str) -> float:
    return max((team_sim(c, target) for c in candidates if c), default=0.0)


def pool_side_score(candidates: list[str], target: str, opponent: str,
                    target_opponent: str, gap_h: Optional[float]) -> float:
    """Belagt kortnamn kräver exakt motståndare och känd avspark ±15 min.

    Ingen fuzzy eller landskod får göra kontextaliaset till en annan klubb.
    Övriga par använder oförändrad namnregel.
    """
    name = _norm_team(candidates[0])
    other = _norm_team(opponent)
    canonical = _POOL_CONTEXT_ALIASES.get((name, other))
    if canonical:
        return float(gap_h is not None and gap_h <= 0.25
                     and _norm_team(target_opponent) == other
                     and _norm_team(target) == canonical)
    return _best_side(candidates, target)


def diagnostic_team_sim(a: str, b: str) -> float:
    """Sökledtråd ENBART: delnamn får synas i audit men aldrig länka odds."""
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return 0.0
    return max(team_sim(a, b), _ratio(na, nb))


# --- pool-name-v5: generiska delnamn och landslag ---------------------------
# Ord som bara beskriver klubbFORMEN, aldrig vilken klubb det är. Ett delnamn
# (Plymouth / Plymouth Argyle) räknas bara när ALLT som skiljer namnen är
# sådana ord. Varje ord är prövat mot Pinnacles index 2026-09-24 och SvS
# namnhistorik: det har minst ett belagt par med samma klubb, och varje
# belagt par med OLIKA klubbar står i _POOL_REJECTED_PARTS. Motivering per
# ord: docs/overlamningar/overlamning-2026-09-24-poolnamn-v5.md. Medvetet
# UTE: atletico (Atletico Albacete och Las Palmas Atletico är B-lag, Paris FC
# ≠ Paris 13 Atletico), sc (Barcelona ≠ Barcelona SC), rangers (Queens Park ≠
# QPR), wednesday (Sheffield), forest och hotspur (inget par utöver
# poolaliasen Nottingham/Tottenham), real, sporting och siffror/årtal.
_POOL_GENERIC_WORDS = frozenset({
    "town", "city", "united", "county", "rovers", "albion", "athletic",
    "wanderers", "argyle", "alexandra", "stanley", "harriers", "club",
    "deportivo", "gremio"})
# Belagt OLIKA klubbar som ändå är varandras generiska delnamn (index
# 2026-09-24 mot SvS namnhistorik). Poolspecifikt: TEAM_REJECTED_LINKS delas
# med modellen och ändras inte för poolens skull.
_POOL_REJECTED_PARTS = frozenset(frozenset(pair) for pair in (
    ("dundee", "dundee united"),           # Dundee FC ≠ Dundee United
    ("oxford", "oxford city"),             # SvS Oxford = Oxford United
    ("bangor city", "bangor"),             # Bangor City (WAL) ≠ Bangor (NIR)
    ("eskilstuna city", "eskilstuna"),     # Eskilstuna City ≠ AFC Eskilstuna
    ("america", "club america"),           # SvS America (BRA) = America Mineiro
    ("guarani", "club guarani"),           # Guarani (BRA) ≠ Club Guarani (PAR)
    ("club aurora", "aurora"),             # Club Aurora (BOL) ≠ Aurora FC (GUA)
    ("deportivo municipal", "municipal"),  # Peru ≠ Guatemala
    ("moron", "deportivo moron"),          # Morön BK ≠ Deportivo Morón
))
# Landslag. ISO-landsnamnet blir namnkandidat ENBART när SvS-deltagaren heter
# som landet på svenska: SvS sätter isoCode även på klubbar (Real Madrid ESP,
# Galway IRL), och ett landsnamn som kandidat för en klubb gav felkopplingen
# Vestmannaeyja–Valur → Iceland–Switzerland. `english_name` delas med
# the-odds-api och Bomben och ändras inte; poolens extra former står här.
_POOL_ISO_EXTRA = {"CZE": ("Czechia",), "TUR": ("Turkiye", "Turkey")}
# FIFA-koder utan ISO 3166-1-land som SvS använder (omgångarna 2026-09-24):
# svenskt namn och Pinnacles namn.
_POOL_NATIONS = {
    "ENG": ("England", ("England",)),
    "SCO": ("Skottland", ("Scotland",)),
    "WAL": ("Wales", ("Wales",)),
    "NIR": ("Nordirland", ("Northern Ireland",)),
    "XXK": ("Kosovo", ("Kosovo",)),
}
# Svenska namnformer som pycountry saknar. DR Kongo: SvS deltagarnamn i 12
# länkade poolmatcher mot Pinnacles DR Congo. GBR följer _ISO_OVERRIDE.
_POOL_SV_EXTRA = {"COD": ("DR Kongo",), "GBR": ("England",)}
_SAINT = frozenset({"st", "sankt", "saint"})
_COUNTRY_FILLER = frozenset({"och", "and"})
EXACT, PART = "exact", "part"
_sv_translation = None
_country_names: frozenset[str] | None = None


def _is_squad_token(token: str) -> bool:
    return token in _SQUAD_MARKERS or (token.startswith("u") and token[1:].isdigit())


@functools.lru_cache(maxsize=16384)
def _country_tokens(name: Optional[str]) -> tuple[str, ...]:
    """Landsnamn utan diakriter, skiljetecken och och/and; St/Sankt = Saint."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return tuple("saint" if t in _SAINT else t
                 for t in re.findall(r"[a-z0-9]+", s) if t not in _COUNTRY_FILLER)


def _country(iso: Optional[str]):
    if not iso or not pycountry:
        return None
    return pycountry.countries.get(alpha_3=iso) or pycountry.countries.get(alpha_2=iso)


def _sv(text: str) -> str:
    global _sv_translation
    if _sv_translation is None:
        try:
            _sv_translation = gettext.translation(
                "iso3166-1", pycountry.LOCALES_DIR, languages=["sv"])
        except (AttributeError, OSError):
            _sv_translation = gettext.NullTranslations()
    return _sv_translation.gettext(text)


@functools.lru_cache(maxsize=None)
def _swedish_forms(iso: str) -> tuple[tuple[str, ...], ...]:
    names = list(_POOL_SV_EXTRA.get(iso, ()))
    if iso in _POOL_NATIONS:
        names.append(_POOL_NATIONS[iso][0])
    country = _country(iso)
    for attr in ("name", "common_name"):
        value = getattr(country, attr, None) if country is not None else None
        if value:
            swedish = _sv(value)
            names += [swedish, swedish.split(",")[0]]   # "Moldavien, republiken"
    forms: list[tuple[str, ...]] = []
    for name in names:
        tokens = _country_tokens(name)
        if tokens and tokens not in forms:
            forms.append(tokens)
    return tuple(forms)


def _english_forms(iso: str) -> list[str]:
    names = [english_name(iso), *_POOL_ISO_EXTRA.get(iso, ()),
             *_POOL_NATIONS.get(iso, ("", ()))[1]]
    country = _country(iso)
    if country is not None:
        names += [country.name, getattr(country, "common_name", None)]
    out: list[str] = []
    for name in names:
        if name and name not in out:
            out.append(name)
    return out


@functools.lru_cache(maxsize=4096)
def national_squad(name: Optional[str], iso: Optional[str]) -> Optional[tuple[str, ...]]:
    """Truppmarkörerna om SvS-deltagaren är landslaget för SIN landskod, annars None.

    Namnet ska vara landets svenska namn: exakt (Tjeckien, Bosnien &
    Hercegovina, St. Lucia), SvS egen avkortning där varje ord är ett prefix
    och minst fem tecken återstår (Nederländ, Liechtens, Nordirlan, Bosnien/H)
    eller första ordet följt av enbokstavsförkortningar (Bosnien o).
    Truppmarkörer (U21) följer med kandidaterna. En klubb med isoCode är
    aldrig ett landslag.
    """
    if not iso:
        return None
    tokens = _country_tokens(name)
    squad = tuple(t for t in tokens if _is_squad_token(t))
    core = tuple(t for t in tokens if not _is_squad_token(t))
    if not core:
        return None
    for form in _swedish_forms(iso):
        if core == form:
            return squad
        if (len("".join(core)) >= 5 and len(core) <= len(form)
                and all(full.startswith(part) for part, full in zip(core, form))):
            return squad
        if (len(form) >= 2 and len(core) >= 2 and core[0] == form[0]
                and len(core[0]) >= 5 and all(len(t) == 1 for t in core[1:])):
            return squad
    return None


def pool_name_candidates(name: str, iso: Optional[str]) -> tuple[list[str], bool]:
    """(kandidatnamn, landslag?) för en SvS-deltagare.

    SvS-namnet står alltid först (kontextaliasen läser candidates[0]).
    Landsnamn tillkommer ENBART för ett igenkänt landslag.
    """
    squad = national_squad(name, iso)
    if squad is None:
        return [name], False
    suffix = "".join(" " + token for token in squad)
    out = [name]
    for english in _english_forms(iso):
        if english + suffix not in out:
            out.append(english + suffix)
    return out, True


def _country_name_set() -> frozenset[str]:
    global _country_names
    if _country_names is None:
        names = set(_ISO_OVERRIDE.values())
        for swedish, english in _POOL_NATIONS.values():
            names.add(swedish)
            names.update(english)
        for extra in (*_POOL_ISO_EXTRA.values(), *_POOL_SV_EXTRA.values()):
            names.update(extra)
        for country in (pycountry.countries if pycountry else ()):
            for attr in ("name", "common_name"):
                value = getattr(country, attr, None)
                if value:
                    names.update((value, _sv(value), _sv(value).split(",")[0]))
        _country_names = frozenset(" ".join(_country_tokens(n)) for n in names if n)
    return _country_names


@functools.lru_cache(maxsize=16384)
def is_country_name(name: Optional[str]) -> bool:
    """Ett landsnamn på engelska eller svenska, även med truppmarkör (Iceland U21)."""
    core = [t for t in _country_tokens(name) if not _is_squad_token(t)]
    return bool(core) and " ".join(core) in _country_name_set()


def pool_part(a: Optional[str], b: Optional[str]) -> bool:
    """Generiskt delnamn (Plymouth / Plymouth Argyle, Novorizontino / Gremio
    Novorizontino).

    Det kortare namnets ord är ett sammanhängande prefix eller suffix av det
    längres och ALLA övriga ord är klubbformsord. Samma trupp krävs; kända
    falska par och landsnamn fälls, och det kortare namnet måste bära minst
    ett eget ord. Ensamt aldrig en länk: match_index kräver dessutom känd
    avspark inom POOL_ANCHOR_S. `team_sim` är orörd (delnamn ger där 0).
    """
    if not a or not b:
        return False
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb or na == nb or _squad(na) != _squad(nb):
        return False
    pair = frozenset((na, nb))
    if pair in _rejected() or pair in _POOL_REJECTED_PARTS:
        return False
    if any(is_country_name(name) for name in (a, b, na, nb)):
        return False
    core_a = [t for t in na.split() if not _is_squad_token(t)]
    core_b = [t for t in nb.split() if not _is_squad_token(t)]
    short, long_ = sorted((core_a, core_b), key=len)
    n = len(short)
    if not n or n == len(long_) or all(t in _POOL_GENERIC_WORDS for t in short):
        return False
    for rest in ((long_[n:] if long_[:n] == short else None),
                 (long_[:-n] if long_[-n:] == short else None)):
        if rest and all(t in _POOL_GENERIC_WORDS for t in rest):
            return True
    return False


def pool_side_relation(candidates: list[str], target: str, opponent: str,
                       target_opponent: str, gap_h: Optional[float],
                       national: bool = False) -> tuple[Optional[str], float]:
    """(relation, sidopoäng) för EN sida i pool-name-v5.

    'exact' = exakt/alias (1,0); 'part' = generiskt delnamn (sidopoäng 0 som
    i v4); None = ingetdera, med stavningslikheten för nivå F. Kontextalias
    styrs enbart av sin egen regel. Landsnamn matchas bara exakt: ett igenkänt
    landslag hos SvS eller ett landsnamn hos Pinnacle får varken delnamn eller
    stavningslikhet (England~Finland 0,714 och France~Ukraine 0,615 är olika
    länder, inte stavningsvarianter).
    """
    name = _norm_team(candidates[0])
    if (name, _norm_team(opponent)) in _POOL_CONTEXT_ALIASES:
        score = pool_side_score(candidates, target, opponent, target_opponent, gap_h)
        return (EXACT if score >= 1.0 else None), score
    score = _best_side(candidates, target)
    if score >= 1.0:
        return EXACT, 1.0
    if national or is_country_name(candidates[0]) or is_country_name(target):
        # Samma land i annan skrivform (St./Saint, &/and) är fortfarande exakt.
        wanted = _country_tokens(target)
        if any(c and _country_tokens(c) == wanted for c in candidates):
            return EXACT, 1.0
        return None, 0.0
    if pool_part(candidates[0], target):
        return PART, score
    return None, score


# --- pool-name-v6: truppmarkörer ur Pinnacles LIGANAMN ----------------------
# Pinnacle skriver U21-, U20-, U19-, reserv- och damlag UTAN markör i
# lagnamnet ("Ukraine - Turkiye" i "UEFA - U21 Euro Championship Qualifiers",
# "Chelsea - Arsenal" i "England - Women Super League"). Markören finns bara i
# ligans namn. Poolmatcharen lägger därför ligans markörer på kandidatens
# lagnamn, och den befintliga truppregeln (`_squad`) gör resten: ett SvS-lag
# utan markör kan inte länkas till raden, ett SvS-lag med samma markör
# ("Sverige U21") kan. Tidsankare, nivåer och trösklar är orörda. Listan är
# prövad mot alla liganamn i Pinnacles index 2026-09-24; varje liga med
# Pinnacles egen åldersgräns (ageLimit > 0) fångas.
# U-åldrar 15–23 (uppdraget U17–U23; U15/U16 är samma klass). SvS "Dam" är
# fortsatt ingen truppmarkör, så en dammatch hos SvS länkas inte (som v5).
_LEAGUE_AGE_RE = re.compile(r"\b(?:u|under|sub)[\s-]?(\d{2})\b")
_LEAGUE_AGE_RANGE = range(15, 24)
_LEAGUE_WOMEN_WORDS = frozenset({
    "women", "womens", "woman", "female", "females", "ladies", "girls",
    "feminine", "feminin", "feminines", "femenina", "femenino", "femenil",
    "feminina", "feminino", "femminile", "frauen", "frauenliga", "damen",
    "dames", "damer", "vrouwen", "kvinner", "kvinder", "kvinnor", "naisten",
    "kobiet", "damallsvenskan", "elitettan", "toppserien", "kvindeligaen",
    "kvindeliga", "wsl", "nwsl", "swpl"})
# Ord som bara är damform i en viss följd (Liga F, W-League, WE League, WK
# League, Kansallinen Liiga). Ensamma "f"/"w" är det inte (Group F).
# Medvetet UTE: junior (skotska Junior Cup är vuxna klubbar), wpl (Welsh
# Premier League), olympic (herrturneringen är U23 men SvS skriver lagen
# utan markör), premier league 2 (U21 men namnet saknar markör; inte belagt).
_LEAGUE_WOMEN_PHRASES = (("liga", "f"), ("w", "league"), ("we", "league"),
                         ("wk", "league"), ("kansallinen", "liiga"))
_LEAGUE_YOUTH_WORDS = frozenset({"youth", "juvenil", "juveniles", "primavera",
                                 "academy"})
_LEAGUE_RESERVE_WORDS = frozenset({"reserve", "reserves", "reserva", "reservas"})


@functools.lru_cache(maxsize=4096)
def league_squad(league: Optional[str]) -> tuple[str, ...]:
    """Truppmarkörerna som Pinnacles liganamn bär (sorterade), annars ().

    U-ålder ger "u21" osv., damform "women", reservliga "reserves" och
    ungdomsliga utan U-ålder "youth" — samma tokens som `_squad` redan känner.
    """
    if not league:
        return ()
    s = unicodedata.normalize("NFKD", league)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    tokens = re.findall(r"[a-z0-9]+", s)
    markers = {f"u{int(age)}" for age in _LEAGUE_AGE_RE.findall(s)
               if int(age) in _LEAGUE_AGE_RANGE}
    pairs = set(zip(tokens, tokens[1:]))
    if (_LEAGUE_WOMEN_WORDS.intersection(tokens) or "(w)" in s
            or any(phrase in pairs for phrase in _LEAGUE_WOMEN_PHRASES)):
        markers.add("women")
    if not markers.intersection(f"u{age}" for age in _LEAGUE_AGE_RANGE) \
            and _LEAGUE_YOUTH_WORDS.intersection(tokens):
        markers.add("youth")
    if _LEAGUE_RESERVE_WORDS.intersection(tokens):
        markers.add("reserves")
    return tuple(sorted(markers))


def with_league_squad(name: str, markers: tuple[str, ...]) -> str:
    """Lagnamnet med ligans truppmarkörer som saknas (aldrig dubbelt: ett
    namn som redan bär markören, t.ex. "Sweden U21", lämnas orört)."""
    have = _squad(_norm_team(name))
    missing = [marker for marker in markers if marker not in have]
    return " ".join([name, *missing]) if missing else name


def is_side_market(home: str, away: str) -> bool:
    """Namngivna hörn-/kort-event är inte matchens målmarknad."""
    return bool(re.search(r"\b(corners?|bookings?|cards?)\b",
                          f"{home} {away}", flags=re.IGNORECASE))


class ExternalOdds:
    """the-odds-api, credit-snålt: matcha via gratis /events, betala bara odds
    för matchade matcher (1 credit/match med en region)."""

    def __init__(self, regions: str = "eu", timeout: float = 25.0):
        self.regions = regions          # EN region = 1 credit per event
        self._client = httpx.Client(timeout=timeout)
        self.requests_remaining: Optional[str] = None  # uppdateras vid varje anrop

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, path: str, **params):
        params["apiKey"] = api_key()
        r = self._client.get(f"{API_BASE}{path}", params=params)
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            self.requests_remaining = rem
        r.raise_for_status()
        return r.json()

    # --- GRATIS: lista ligor + events ---
    def soccer_sports(self) -> list[str]:
        sports = self._get("/sports")
        return [s["key"] for s in sports
                if s.get("active") and s.get("key", "").startswith("soccer_")]

    def event_index(self, max_sports: int = 25) -> list[dict]:
        """Alla kommande soccer-events (utan odds). Kostar inga credits."""
        index: list[dict] = []
        for sport in self.soccer_sports()[:max_sports]:
            try:
                events = self._get(f"/sports/{sport}/events")
            except httpx.HTTPStatusError:
                continue
            for ev in events:
                index.append({"sport": sport, "id": ev.get("id"),
                              "home": ev.get("home_team"), "away": ev.get("away_team"),
                              "commence_time": ev.get("commence_time")})
        return index

    def match_event(self, home: str, away: str, home_iso: Optional[str],
                    away_iso: Optional[str], index: list[dict],
                    match_start: Optional[str] = None) -> Optional[dict]:
        """Hitta bästa matchande event (ingen kostnad). Returnerar sport+id+konfidens.

        Kräver både namnlikhet och — om match_start anges — att den externa
        matchen startar inom TIME_WINDOW_H timmar. Tidsfönstret stänger ute
        fel fixtures (t.ex. samma lag i en annan omgång)."""
        home_cands = [home, english_name(home_iso)]
        away_cands = [away, english_name(away_iso)]
        best, best_score = None, 0.0
        for ev in index:
            if match_start:
                gap = _hours_apart(match_start, ev.get("commence_time"))
                if gap is None or gap > TIME_WINDOW_H:
                    continue
            sh = _best_side(home_cands, ev["home"])
            sa = _best_side(away_cands, ev["away"])
            if sh < HOME_AWAY_MIN or sa < HOME_AWAY_MIN:
                continue
            score = (sh + sa) / 2
            if score > best_score:
                best, best_score = ev, score
        if not best or best_score < COMBINED_MIN:
            return None
        return {**best, "confidence": round(best_score, 3)}

    # --- KOSTAR 1 credit per anrop ---
    def event_odds(self, sport: str, event_id: str) -> dict[str, dict]:
        ev = self._get(f"/sports/{sport}/events/{event_id}/odds",
                       regions=self.regions, markets="h2h", oddsFormat="decimal")
        home, away = ev.get("home_team"), ev.get("away_team")
        books: dict[str, dict] = {}
        for bk in ev.get("bookmakers", []):
            m = next((mk for mk in bk.get("markets", []) if mk.get("key") == "h2h"), None)
            if not m:
                continue
            o = {x["name"]: x["price"] for x in m.get("outcomes", [])}
            books[bk["key"]] = {"1": o.get(home), "X": o.get("Draw"), "2": o.get(away)}
        return books

    @staticmethod
    def pick_book(books: dict[str, dict]) -> Optional[str]:
        if not books:
            return None
        return next((b for b in SHARP_PREFERENCE if b in books), next(iter(books)))
