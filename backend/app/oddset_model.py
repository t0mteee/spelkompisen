"""Egen målmodell: xG-viktad Poisson-styrkefit per liga, med DC-korrektion.

Styrkor (anfall/försvar per lag + hemmafördel per liga) fittas iterativt på
resultat sedan 2024 med exponentiell tidsavklingning. Där Sofascore-xG finns
används xG-viktad "effektiv målproduktion" (0.65·xG + 0.35·mål) — xG är mindre
brusig än utfallet. Totalnivån ANKRAS mot devigad sharp ÖU-linje när Pinnacle
finns (vm-lärdomen: linjen ≈ median, okalibrerad μ blir systematiskt fel).

METODREGEL (vm, tre gånger bevisad): modell-edges utan sharp-ankare är
systematiskt uppblåsta → allt härifrån är AMBER-tier: bakom toggle i UI,
ALDRIG in i CLV-facitet. Grön blir modellen först om backtesten (Etapp 5) håller.

Träningsmatcher modelleras INTE (rotationsrisk — där är steam/nyheter verktyget).

Detta är inte en Dixon-Coles-MLE: lagstyrkorna fittas iterativt med Poisson-
momentekvationer och DC:s rho-korrektion appliceras först i prediktionsmatrisen.
"""
from __future__ import annotations

import datetime as dt
import math
from difflib import SequenceMatcher
from typing import Optional

from . import oddset_data
from .analysis import _power_probs
from .storage import Storage

DC_RHO_CLUB = -0.01     # REFITTAD i Etapp 5-backtesten (2026-07-12): grid-minimum
                        # −0.01/+0.02 i BÅDA ligorna — klubblitteraturens −0.13
                        # överkorrigerar här precis som för landslag (vm: −0.04)
MAX_GOALS = 12
XG_WEIGHT = 0.65        # effektiva mål = 0.65·xG + 0.35·mål (när xG finns)
DECAY_DAYS = 240.0      # vikt = exp(-ålder/240 d) — e-folding 240 d, dvs
                        # HALVERINGSTID ≈ 166 d (beteendet behållet vid
                        # granskningen 2026-07-13; bara benämningen var fel)
FIT_ITER = 80
MODEL_EDGE_SHOW = 0.05  # amber-pill först vid ≥5 % (högre ribba än sharp — okalibrerad)
MIN_MATCHES = 8         # lag med färre viktade matcher får Elo-prior (M2) i stället
ELO_K = 0.35            # M2: styrka ur ClubElo: att = q^k, def = q^-k där
                        # q = 10^((elo − liga-medel)/400). Grov mappning (+100 Elo
                        # ≈ 1.5× λ-kvot) — forward-loggen utvärderar, inte tron.
CORNER_MODEL_VERSION = "corner-poisson-total-v1"


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dc_matrix(mu_h: float, mu_a: float, rho: float = DC_RHO_CLUB) -> list[list[float]]:
    hp = [_pois(i, mu_h) for i in range(MAX_GOALS + 1)]
    ap = [_pois(j, mu_a) for j in range(MAX_GOALS + 1)]
    m = [[hp[i] * ap[j] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
    tau = {(0, 0): 1 - mu_h * mu_a * rho, (0, 1): 1 + mu_h * rho,
           (1, 0): 1 + mu_a * rho, (1, 1): 1 - rho}
    for (i, j), t in tau.items():
        m[i][j] *= max(t, 0.0)
    s = sum(sum(row) for row in m) or 1.0
    return [[c / s for c in row] for row in m]


def temper(matrix: list[list[float]], t: float) -> list[list[float]]:
    """Temperatur-kalibrering av HELA målmatrisen: p^(1/T), renormaliserad.
    T > 1 = modellen var överkonfident (extremer krymps). T fittas per liga i
    walk-forward-backtesten (cli oddsetcalibrate), men valdes och rapporterades
    på samma historiska prediktionsmängd. Ledgern gör den oberoende forward-
    valideringen innan modellen kan lämna amber."""
    if abs(t - 1.0) < 1e-6:
        return matrix
    m = [[c ** (1 / t) for c in row] for row in matrix]
    s = sum(sum(row) for row in m) or 1.0
    return [[c / s for c in row] for row in m]


def matrix_1x2(m: list[list[float]]) -> dict[str, float]:
    p1 = sum(m[i][j] for i in range(len(m)) for j in range(len(m)) if i > j)
    p2 = sum(m[i][j] for i in range(len(m)) for j in range(len(m)) if i < j)
    return {"1": p1, "X": max(0.0, 1 - p1 - p2), "2": p2}


# --- styrkefit -------------------------------------------------------------------

def fit_league(results: list[dict], now: Optional[dt.date] = None,
               iters: int = FIT_ITER) -> Optional[dict]:
    """Iterativ Poisson-fit: λ_hemma = base_liga·hf_liga·att_h·def_a,
    λ_borta = base_liga·att_a·def_h. Lagstyrkor (att/def) är GEMENSAMMA över
    alla ligor i indata (cross-liga-fit: upp-/nedflyttare länkar populationerna
    mellan säsonger); base och hemmafördel skattas PER liga (rad-nyckeln
    'league', '' om saknas). Returnerar {'teams', 'home_adv': {lg}, 'base': {lg}}."""
    now = now or dt.date.today()
    rows = []
    for r in results:
        try:
            age = (now - dt.date.fromisoformat(r["date"])).days
        except ValueError:
            continue
        if age < 0:
            continue
        w = math.exp(-age / DECAY_DAYS)
        eh = (XG_WEIGHT * r["xg_h"] + (1 - XG_WEIGHT) * r["hg"]
              if r.get("xg_h") is not None else float(r["hg"]))
        ea = (XG_WEIGHT * r["xg_a"] + (1 - XG_WEIGHT) * r["ag"]
              if r.get("xg_a") is not None else float(r["ag"]))
        rows.append((r["home"], r["away"], eh, ea, w, r.get("league") or ""))
    if len(rows) < 40:
        return None

    teams = sorted({t for h, a, *_ in rows for t in (h, a)})
    leagues = sorted({lg for *_, lg in rows})
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    base, home_adv = {}, {}
    for lg in leagues:
        lw = sum(w for *_, w, l in rows if l == lg) or 1e-9
        base[lg] = sum((eh + ea) * w for _, _, eh, ea, w, l in rows if l == lg) / (2 * lw)
        home_adv[lg] = 1.25
    for _ in range(iters):
        exp_h = {t: 1e-9 for t in teams}
        exp_a = {t: 1e-9 for t in teams}
        obs_h = {t: 1e-9 for t in teams}
        obs_a = {t: 1e-9 for t in teams}
        exp_dh = {t: 1e-9 for t in teams}   # förväntat insläppt hemma/borta
        exp_da = {t: 1e-9 for t in teams}
        obs_dh = {t: 1e-9 for t in teams}
        obs_da = {t: 1e-9 for t in teams}
        th_exp = {lg: 1e-9 for lg in leagues}
        th_obs = {lg: 1e-9 for lg in leagues}
        tt_exp = {lg: 1e-9 for lg in leagues}
        tt_obs = {lg: 1e-9 for lg in leagues}
        for h, a, eh, ea, w, lg in rows:
            lh = base[lg] * home_adv[lg] * att[h] * dfn[a]
            la = base[lg] * att[a] * dfn[h]
            exp_h[h] += w * lh; obs_h[h] += w * eh
            exp_a[a] += w * la; obs_a[a] += w * ea
            exp_dh[a] += w * lh; obs_dh[a] += w * eh   # bortalagets försvar möter lh
            exp_da[h] += w * la; obs_da[h] += w * ea
            th_exp[lg] += w * lh; th_obs[lg] += w * eh
            tt_exp[lg] += w * (lh + la); tt_obs[lg] += w * (eh + ea)
        for t in teams:
            att[t] *= ((obs_h[t] + obs_a[t]) / (exp_h[t] + exp_a[t])) ** 0.5
            dfn[t] *= ((obs_dh[t] + obs_da[t]) / (exp_dh[t] + exp_da[t])) ** 0.5
        m_att = sum(att.values()) / len(teams)
        m_dfn = sum(dfn.values()) / len(teams)
        for t in teams:
            att[t] /= m_att
            dfn[t] /= m_dfn
            # mjuk ridge mot 1: i en pool där en liga är svagt kopplad (OBOS-lag
            # möter bara varandra) är skalan oidentifierbar längs (att·c, def·c,
            # base/c²) — utan dämpning driver base iväg (observerat: 28.9).
            att[t] **= 0.98
            dfn[t] **= 0.98
        for lg in leagues:
            base[lg] *= m_att * m_dfn * (tt_obs[lg] / tt_exp[lg]) ** 0.25
            home_adv[lg] *= (th_obs[lg] / th_exp[lg]) ** 0.5

    nw = {t: 0.0 for t in teams}
    for h, a, _, _, w, _ in rows:
        nw[h] += w; nw[a] += w
    return {"teams": {t: {"att": round(att[t], 3), "def": round(dfn[t], 3),
                          "n": round(nw[t], 1)} for t in teams},
            "home_adv": {lg: round(v, 3) for lg, v in home_adv.items()},
            "base": {lg: round(v, 3) for lg, v in base.items()}}


def _find_team(fit: dict, norm_name: str) -> Optional[str]:
    if norm_name in fit["teams"]:
        return norm_name
    best, best_s = None, 0.6
    for t in fit["teams"]:
        if norm_name in t or t in norm_name:
            return t
        s = SequenceMatcher(None, norm_name, t).ratio()
        if s > best_s:
            best, best_s = t, s
    return best


def _lg_param(d: dict, league: Optional[str]) -> float:
    if league in d:
        return d[league]
    return sum(d.values()) / len(d)


def predict(fit: dict, home_norm: str, away_norm: str,
            league: Optional[str] = None) -> Optional[tuple[float, float]]:
    h, a = _find_team(fit, home_norm), _find_team(fit, away_norm)
    if not h or not a:
        return None
    th, ta = fit["teams"][h], fit["teams"][a]
    if th["n"] < MIN_MATCHES or ta["n"] < MIN_MATCHES:
        return None
    base = _lg_param(fit["base"], league)
    hf = _lg_param(fit["home_adv"], league)
    mu_h = base * hf * th["att"] * ta["def"]
    mu_a = base * ta["att"] * th["def"]
    return mu_h, mu_a


def _ensure_priors(fit: dict, elo: dict, names: tuple[str, ...]) -> bool:
    """M2: lag som saknas i fitten eller har < MIN_MATCHES viktade matcher får
    styrkor ur ClubElo relativt ligans medel (tunna lag blandas proportionellt).
    Muterar fitten (n sätts till MIN_MATCHES så priorn inte dubbelappliceras)."""
    if "_mean_elo" not in fit:
        vals = []
        for t in fit["teams"]:
            ev = elo.get(t) or elo.get(_find_team({"teams": elo}, t) or "")
            if ev:
                vals.append(ev)
        fit["_mean_elo"] = sum(vals) / len(vals) if vals else None
    if not fit["_mean_elo"]:
        return False
    used = False
    for nm in names:
        t = _find_team(fit, nm)
        cur = fit["teams"].get(t) if t else None
        if cur and cur["n"] >= MIN_MATCHES:
            continue
        ev = elo.get(nm) or elo.get(_find_team({"teams": elo}, nm) or "")
        if not ev:
            continue
        q = 10 ** ((ev - fit["_mean_elo"]) / 400)
        att_e, def_e = q ** ELO_K, q ** -ELO_K
        if cur:
            w = cur["n"] / MIN_MATCHES
            cur["att"] = round(w * cur["att"] + (1 - w) * att_e, 3)
            cur["def"] = round(w * cur["def"] + (1 - w) * def_e, 3)
            cur["n"] = MIN_MATCHES
        else:
            fit["teams"][nm] = {"att": round(att_e, 3), "def": round(def_e, 3),
                                "n": MIN_MATCHES}
        used = True
    return used


def _anchor_total(mu_h: float, mu_a: float, line: float, p_over: float,
                  temperature: float = 1.0) -> tuple[float, float]:
    """Skala målmedlen tills slutmatrisens settlement-sannolikhet matchar sharp.

    Marknadens tvåvägsprobabilitet motsvarar P(vinst | återbetalning borttagen),
    inte den ovillkorade P(total > linje). Därför måste hel- och kvartslinjers
    push/halv-push ingå. Temperaturjusteringen ligger inne i rotlösningen så att
    den inte kan bryta ankaret efteråt. Modellens styrkeförhållande bevaras.
    """
    target = max(1e-6, min(1 - 1e-6, p_over))

    def prob(scale: float) -> float:
        matrix = temper(dc_matrix(scale * mu_h, scale * mu_a), temperature)
        return _settlement_probability(matrix, "ou", "O", line)

    lo, hi = 0.05, 5.0
    while prob(lo) > target and lo > 1e-4:
        lo /= 2
    while prob(hi) < target and hi < 50:
        hi *= 2
    if target <= prob(lo):
        scale = lo
    elif target >= prob(hi):
        scale = hi
    else:
        for _ in range(50):
            scale = (lo + hi) / 2
            if prob(scale) < target:
                lo = scale
            else:
                hi = scale
        scale = (lo + hi) / 2
    return scale * mu_h, scale * mu_a


# --- asiatiska marknader ur DC-matrisen ------------------------------------------------

def _half_outcome(matrix: list[list[float]], kind: str, side: str,
                  line: float) -> tuple[float, float]:
    """(P_vinst, P_push) för en HEL- eller HALVLINJE. AH-linjen är hemmaperspektiv
    (bortasidan spelar mot −linjen); ÖU: side 'O'/'U' mot totalen."""
    pw = pp = 0.0
    n = len(matrix)
    for i in range(n):
        for j in range(n):
            p = matrix[i][j]
            if kind == "ah":
                v = (i - j) + line if side == "H" else (j - i) - line
            else:
                v = (i + j) - line if side == "O" else line - (i + j)
            if v > 1e-9:
                pw += p
            elif abs(v) <= 1e-9:
                pp += p
    return pw, pp


def _settlement_terms(matrix: list[list[float]], kind: str, side: str,
                      line: float) -> tuple[float, float]:
    """Sammanvägd (P_vinst, P_push) för hel-, halv- eller kvartslinje."""
    quarter = abs(line * 2 - round(line * 2)) > 1e-9
    halves = [line - 0.25, line + 0.25] if quarter else [line]
    pw = pp = 0.0
    for half_line in halves:
        win, push = _half_outcome(matrix, kind, side, half_line)
        pw += win / len(halves)
        pp += push / len(halves)
    return pw, pp


def _settlement_probability(matrix: list[list[float]], kind: str, side: str,
                            line: float) -> float:
    """Fair tvåvägsprobabilitet efter att push-delen räknats bort."""
    pw, pp = _settlement_terms(matrix, kind, side, line)
    return pw / (1 - pp) if pp < 1 else 0.0


def pair_fair(matrix: list[list[float]], kind: str, line: float,
              sides: tuple[str, str]) -> Optional[dict]:
    """Fair decimalodds för båda sidor av en asiatisk linje (hel/halv/kvarts).
    Kvartslinje = halva insatsen på var sin grannlinje; push återbetalar.
    fair o löser: o·P_vinst + P_push = 1."""
    out = {"line": line}
    for side in sides:
        pw, pp = _settlement_terms(matrix, kind, side, line)
        if pw < 0.01:
            return None
        out[side] = round((1 - pp) / pw, 2)
        out[f"p{side}"] = round(_settlement_probability(
            matrix, kind, side, line), 4)
    return out


# --- hörn-modell (M4b) ---------------------------------------------------------------
# vm-lärdomen står fast: hörn-VÄRDE kräver sharp linje (modell-edges blev +120 %
# okalibrerat). Förväntan visas; från 2026-07-25 fryses även en explicit
# Poisson-baslinje på SHARPENS lina i prediction-ledgern. Den påverkar inga
# tips utan kalibreras med samma modell-mot-close-mått som övriga marknader.

def corner_model(results: list[dict]) -> Optional[dict]:
    """Liga-nivå ur egen Sofascore-data: snitt-total + hemmaandel ~ supremacy (OLS).
    Supremacy-proxy för historiska matcher = xG-differens (mindre brusig än mål)."""
    rows = []
    for r in results:
        if r.get("cor_h") is None or r.get("cor_a") is None:
            continue
        tot = r["cor_h"] + r["cor_a"]
        if tot <= 0:
            continue
        sup = ((r["xg_h"] - r["xg_a"]) if r.get("xg_h") is not None
               else float(r["hg"] - r["ag"]))
        rows.append((tot, r["cor_h"] / tot, max(-2.5, min(2.5, sup))))
    if len(rows) < 60:
        return None
    n = len(rows)
    mean_tot = sum(t for t, _, _ in rows) / n
    xbar = sum(s for _, _, s in rows) / n
    ybar = sum(sh for _, sh, _ in rows) / n
    var = sum((s - xbar) ** 2 for _, _, s in rows) or 1e-9
    cov = sum((s - xbar) * (sh - ybar) for _, sh, s in rows)
    b = cov / var
    return {"tot": round(mean_tot, 2), "a": round(ybar - b * xbar, 4),
            "b": round(b, 4), "n": n}


def expected_corners(cm: dict, mu_h: float, mu_a: float) -> dict:
    sup = max(-2.5, min(2.5, mu_h - mu_a))
    share = max(0.25, min(0.75, cm["a"] + cm["b"] * sup))
    return {"tot": round(cm["tot"], 1), "h": round(cm["tot"] * share, 1),
            "a": round(cm["tot"] * (1 - share), 1)}


def corner_pair(mean_total: float, line: float) -> Optional[dict]:
    """Poisson-baslinje för totalhörn på en asiatisk lina.

    Detta är medvetet en enkel, förregistrerad startpunkt. Överdispersion eller
    annan kalibrering blir en NY semantisk modellversion och måste slå denna på
    det parade close-måttet — parametrar väljs aldrig efter samma forwarddata.
    """
    if mean_total <= 0 or line < 0:
        return None
    max_corners = max(40, int(mean_total + 10 * math.sqrt(mean_total) + 1))
    probs = [
        math.exp(-mean_total) * mean_total ** total / math.factorial(total)
        for total in range(max_corners + 1)
    ]
    norm = sum(probs) or 1.0
    probs = [value / norm for value in probs]
    quarter = abs(line * 2 - round(line * 2)) > 1e-9
    halves = [line - 0.25, line + 0.25] if quarter else [line]
    out = {"line": line}
    for side in ("O", "U"):
        pw = pp = 0.0
        for half_line in halves:
            win = push = 0.0
            for total, probability in enumerate(probs):
                value = total - half_line if side == "O" else half_line - total
                if value > 1e-9:
                    win += probability
                elif abs(value) <= 1e-9:
                    push += probability
            pw += win / len(halves)
            pp += push / len(halves)
        if pw < 0.01 or pp >= 1:
            return None
        out[side] = round((1 - pp) / pw, 2)
        out[f"p{side}"] = round(pw / (1 - pp), 4)
    return out


def market_comparisons(match: dict, model: dict,
                       now: Optional[dt.datetime] = None) -> dict:
    """Modell vs marginalrensad Pinnacle vs marginalrensad SvS i pp.

    AH/ÖU jämförs bara på modellens exakta lina. Om Pinnacles huvudlina har
    flyttat används det befintliga alt-linjelagret; annars redovisas sharp som
    saknad i stället för att två olika linor jämförs.
    """
    from . import oddset_value

    now = now or dt.datetime.now(dt.timezone.utc)
    odds = match.get("odds") or {}
    pin_all = odds.get("pinnacle") or {}
    svs_all = odds.get("svenskaspel") or {}
    sharp_alt = match.get("sharp_alt") or {}
    out = {}
    for market, signs in (
            ("1x2", ("1", "X", "2")),
            ("ah", ("H", "A")),
            ("ou", ("O", "U")),
            ("cor", ("O", "U"))):
        if market == "1x2":
            model_probs = model.get("p") or {}
            line = None
        else:
            pair = model.get(market) or {}
            model_probs = {sign: pair.get(f"p{sign}") for sign in signs}
            line = pair.get("line")
        if any(model_probs.get(sign) is None for sign in signs):
            continue

        pin = pin_all.get(market) or {}
        sharp = None
        sharp_source = None
        if pin.get("fresh") and (
                market == "1x2"
                or (pin.get("line") is not None and line is not None
                    and abs(float(pin["line"]) - float(line)) < 0.0005)):
            sharp = oddset_value._devig(pin, signs)
            sharp_source = "pinnacle"
        elif market != "1x2" and line is not None:
            sharp = oddset_value._alt_fair(
                sharp_alt.get(market) or {}, line, signs, now)
            if sharp:
                sharp_source = "pinnacle_alt"

        svs = svs_all.get(market) or {}
        svs_fair = None
        if svs.get("fresh") and (
                market == "1x2"
                or (svs.get("line") is not None and line is not None
                    and abs(float(svs["line"]) - float(line)) < 0.0005)):
            svs_fair = oddset_value._devig(svs, signs)

        model_probs = {sign: round(float(model_probs[sign]), 4) for sign in signs}
        result = {
            "line": line, "model": model_probs,
            "sharp": ({sign: round(sharp[sign], 4) for sign in signs}
                      if sharp else None),
            "svs": ({sign: round(svs_fair[sign], 4) for sign in signs}
                    if svs_fair else None),
            "sharp_source": sharp_source,
            "model_vs_sharp_pp": (
                {sign: round((model_probs[sign] - sharp[sign]) * 100, 2)
                 for sign in signs} if sharp else None),
            "model_vs_svs_pp": (
                {sign: round((model_probs[sign] - svs_fair[sign]) * 100, 2)
                 for sign in signs} if svs_fair else None),
            "svs_vs_sharp_pp": (
                {sign: round((svs_fair[sign] - sharp[sign]) * 100, 2)
                 for sign in signs} if sharp and svs_fair else None),
        }
        if not sharp:
            result["sharp_note"] = "ingen färsk Pinnacle på exakt lina"
        if not svs_fair:
            result["svs_note"] = "ingen färsk SvS på exakt lina"
        out[market] = result
    return out


# --- payload-koppling ---------------------------------------------------------------

# Sverige poolas (Allsvenskan + Superettan delar lagpopulation via upp-/nedflyttning);
# hörn-statistik hålls per liga (tempot skiljer mellan ligor).
FIT_POOLS = {"allsvenskan": ("allsvenskan", "superettan"),
             "superettan": ("allsvenskan", "superettan"),
             "eliteserien": ("eliteserien", "obosligaen"),
             "obosligaen": ("eliteserien", "obosligaen"),
             "mls": ("mls",)}

# Prognos-relevanta parametrar — grunden för modellens signal_version-finger-
# avtryck (granskningspunkt 5): ändras någon av dessa (eller T-kalibreringen/
# relevant dataversion) byts version och facitet delas. Docs/UI gör det INTE.
MODEL_PARAMS = {
    "algo": "poisson-iterativ + dc-tau i prediktion",
    "rho": DC_RHO_CLUB, "xg_w": XG_WEIGHT, "decay_d": DECAY_DAYS,
    "iters": FIT_ITER, "min_m": MIN_MATCHES, "elo_k": ELO_K, "ridge": 0.98,
    "anchor": "settlement-aware-tempered-v2",
    "result_merge_v": oddset_data.MODEL_DATA_VERSION,
    "pools": sorted(f"{k}:{'+'.join(v)}" for k, v in FIT_POOLS.items()),
}


def attach_model(store: Storage, matches: list[dict],
                 allowed_leagues: Optional[set[str]] = None,
                 fit_pools: Optional[dict[str, tuple[str, ...]]] = None) -> None:
    """Sätter m['model'] (amber-tier) på liga-matcher: sannolikheter, fair odds,
    μ, ankar-status, modell-edge vs SvS samt ClubElo. Träningsmatcher hoppas över.

    `allowed_leagues` används endast av det isolerade V2.2-forskningsflödet.
    Standardvägen för ordinarie UI/signaler förblir MODEL_LEAGUES och dess
    signalversion påverkas därför inte när nya forskningsligor läggs till."""
    from .oddset import norm_team
    fits: dict[str, Optional[dict]] = {}
    elo = oddset_data.get_elo(store)
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    corner_ms: dict[str, Optional[dict]] = {}
    cals: dict[str, dict] = {}
    pool_policy = fit_pools or FIT_POOLS

    def _cal(league: str) -> dict:
        if league not in cals:
            import json as _json
            raw = store.meta_get(f"oddset_cal:{league}")
            if not raw:   # ärv pool-huvudligans kalibrering (Superettan/OBOS saknar
                pool = pool_policy.get(
                    league, (league,))   # stängningsodds att fitta mot)
                raw = store.meta_get(f"oddset_cal:{pool[0]}")
            try:
                cals[league] = _json.loads(raw) if raw else {}
            except ValueError:
                cals[league] = {}
        return cals[league]

    allowed = allowed_leagues or oddset_data.MODEL_LEAGUES
    for m in matches:
        lg = m.get("league")
        if lg not in allowed:   # bara ligor med resultatdata
            continue
        if (m.get("start") or "9") <= now_iso:
            continue   # startad match — modell-edges mot live-odds är meningslösa
        pool = pool_policy.get(lg, (lg,))
        if pool not in fits:
            rows = []
            for plg in pool:
                rows.extend(oddset_data.merged_results(store, plg))
            fits[pool] = fit_league(rows)
        fit = fits[pool]
        if not fit:
            continue
        if lg not in corner_ms:
            corner_ms[lg] = corner_model(oddset_data.merged_results(store, lg))
        hn, an = norm_team(m["home"]), norm_team(m["away"])
        prior_used = _ensure_priors(fit, elo, (hn, an))
        mus = predict(fit, hn, an, league=lg)
        eh, ea = elo.get(hn) or elo.get(_find_team({"teams": elo}, hn) or ""), \
            elo.get(an) or elo.get(_find_team({"teams": elo}, an) or "")
        if eh or ea:
            m["elo"] = {"h": eh, "a": ea}
        if not mus:
            continue
        mu_h, mu_a = mus
        anchored = False
        cal_t = _cal(lg).get("t") or 1.0
        pin_ou = ((m.get("odds") or {}).get("pinnacle") or {}).get("ou")
        if pin_ou and pin_ou.get("fresh") and pin_ou.get("O") and pin_ou.get("U"):
            inv = {"O": 1 / pin_ou["O"], "U": 1 / pin_ou["U"]}
            p_over = _power_probs(inv)["O"]
            mu_h, mu_a = _anchor_total(
                mu_h, mu_a, pin_ou["line"], p_over, temperature=cal_t)
            anchored = True
        matrix = dc_matrix(mu_h, mu_a)
        matrix = temper(matrix, cal_t)
        probs = matrix_1x2(matrix)
        svs_all = (m.get("odds") or {}).get("svenskaspel") or {}
        svs = svs_all.get("1x2") or {}
        edges = {}
        if svs.get("fresh"):
            for sign in ("1", "X", "2"):
                o = svs.get(sign)
                if o:
                    edges[sign] = round(probs[sign] * o - 1.0, 4)
        # AH/ÖU vid SvS:s visade linje: fair ur samma matris + modell-edge.
        # OBS: när totalen är sharp-ankrad är ÖU-fairen nära sharpen per
        # konstruktion — AH bär modellens egen styrkebedömning (supremacy).
        pairs = {}
        for market, sides in (("ah", ("H", "A")), ("ou", ("O", "U"))):
            sv = svs_all.get(market)
            if not sv or not sv.get("fresh") or sv.get("line") is None:
                continue
            pf = pair_fair(matrix, market, sv["line"], sides)
            if not pf:
                continue
            pf["edges"] = {sd: round(pf[f"p{sd}"] * sv[sd] - 1.0, 4)
                           for sd in sides if sv.get(sd)}
            pairs[market] = pf
        m["model"] = {
            "p": {s: round(p, 4) for s, p in probs.items()},
            "fair": {s: round(1 / p, 2) if p > 0.001 else None
                     for s, p in probs.items()},
            "mu": [round(mu_h, 2), round(mu_a, 2)],
            "anchored": anchored, "edges": edges, "prior": prior_used,
            "cal_t": cal_t if cal_t != 1.0 else None, **pairs}
        m["model"]["comparison"] = market_comparisons(
            m, m["model"])
        cm = corner_ms.get(lg)
        if cm:
            corners = expected_corners(cm, mu_h, mu_a)
            m["model"]["corners"] = corners
            pin_cor = ((m.get("odds") or {}).get("pinnacle") or {}).get("cor")
            if (pin_cor and pin_cor.get("fresh")
                    and pin_cor.get("line") is not None):
                pair = corner_pair(corners["tot"], float(pin_cor["line"]))
                if pair:
                    m["model"]["cor"] = pair
                    # Jämförelsen byggdes före hörnparet fanns; komplettera
                    # först nu så den bär exakt samma modellobjekt som ledgern.
                    m["model"]["comparison"] = market_comparisons(
                        m, m["model"])


# ---------------------------------------------------------------- powerrank
# Lagstyrkorna har funnits sedan Etapp 5 men bara som en intern biprodukt av
# `fit_league`. Saman 2026-08-07: syndikat rankar lag och justerar ranken mot
# stats under säsongen, så överpresterande lag dippar och underpresterande
# vänder. Mekanismen FANNS redan (`XG_WEIGHT` viktar xG över mål), men den
# gick aldrig att se — och det som inte syns går inte att ifrågasätta.
#
# METODSPÄRR: allt här är AMBER. Det är en visning av modellens syn, inte ett
# beslutsunderlag. Uppmätt förutsäger modellen inte Pinnacles drift till
# stängning (r = −0,120, 90 % KI [−0,252, +0,034]), så ranken får inte ge
# stödchip, lyfta ett spelkort eller påverka edge, urval eller notiser. Ska
# den bli actionable krävs egen förregistrering och grind — samma väg som
# amber-modellen fälldes på 2026-07-24.
POWERRANK_VERSION = "powerrank-v2"


def season_of(date_iso: str, league: Optional[str] = None) -> Optional[str]:
    """Säsongsetikett för ett matchdatum.

    Höst/vår-ligorna är exakt de som football-data publicerar per säsongsfil
    (`FD_SEASON_CODES`) — den listan finns redan och beskriver samma verklighet,
    så den återanvänds i stället för en parallell handskriven uppsättning som
    kan glida isär. Övriga (nordiska ligor, MLS) spelar inom kalenderåret.
    """
    try:
        year, month = int(date_iso[:4]), int(date_iso[5:7])
    except (TypeError, ValueError, IndexError):
        return None
    if league in oddset_data.FD_SEASON_CODES:
        start = year if month >= 7 else year - 1
        return f"{start}/{(start + 1) % 100:02d}"
    return str(year)


def expected_points(xg_h: float, xg_a: float,
                    rho: float = DC_RHO_CLUB) -> tuple[float, float]:
    """Förväntade poäng ur en matchs xG — inte ur dess mål.

    Poängen ett lag "borde" ha fått givet chanserna det skapade och släppte
    till. Skillnaden mot faktiska poäng är över-/underprestationen: ett lag
    som tar fler poäng än sitt xG motiverar har haft tur eller
    övereffektivitet, och båda regredierar.
    """
    matrix = dc_matrix(max(xg_h, 0.01), max(xg_a, 0.01), rho)
    probs = matrix_1x2(matrix)
    return (3 * probs["1"] + probs["X"], 3 * probs["2"] + probs["X"])


def _display_name(key: str, raws: Optional[set[str]]) -> str:
    """Visningsnamn ur de RÅA namnen källorna skrev, aldrig ur nyckeln.

    Nyckeln är normaliserad för matchning (gemener, diakriter strippade), och
    den formen ska aldrig nå skärmen. Bland varianterna vinner den som bär
    diakriter (`Djurgårdens IF` slår `Djurgarden`) och därefter den längsta
    (`Degerfors IF` slår `Degerfors`) — fullständigare namn är lättare att
    känna igen. Saknas råa namn helt title-casas nyckeln; diakriter GISSAS
    aldrig fram, de kommer bara från en källa som faktiskt skrev dem.
    """
    if not raws:
        return key.title()
    return max(raws, key=lambda n: (not n.isascii(), len(n), n))


def powerrank(results: list[dict], fit: Optional[dict] = None,
              league: Optional[str] = None,
              season: Optional[str] = None,
              odds_names: Optional[list[str]] = None) -> list[dict]:
    """Lagstyrka + xPts-avvikelse per lag, starkast först.

    `att`/`def` kommer ur den fit modellen FAKTISKT använder — ingen egen
    parallell skattning som kan glida isär från prognoserna. Fitten ser HELA
    poolen med tidsvikt; säsongsfiltret gäller bara de räknade kolumnerna.

    **Poäng och xPts räknas på EXAKT samma matcher: de som har xG.** En match
    utan xG bidrar med ingenting alls — inte poäng, inte mål, inte xPts. Fram
    till 2026-08-07 räknades poängen på alla matcher och skalades ned med
    täckningsgraden (`pts × n_xg / matches`), vilket antog att poängen
    fördelade sig jämnt över täckta och otäckta matcher. Det antagandet är
    inte givet, och gjorde avvikelsen till en approximation i stället för en
    mätning. Lag helt utan xG-matcher faller ur tabellen: det finns inget att
    jämföra deras poäng MOT, och en rad med `–` inbjuder till en jämförelse
    som inte går att göra. xG bakfylls aldrig (`MODEL_DATA_VERSION`-regeln).
    """
    fit = fit or fit_league(results)
    if not fit:
        return []
    teams = fit.get("teams") or {}
    agg: dict[str, dict] = {}
    seen: dict[str, int] = {}          # xG-matcher i HELA historiken
    for row in results:
        if league and row.get("league") != league:
            continue
        hg, ag = row.get("hg"), row.get("ag")
        xg_h, xg_a = row.get("xg_h"), row.get("xg_a")
        if hg is None or ag is None or xg_h is None or xg_a is None:
            continue
        for team in (row.get("home"), row.get("away")):
            if team:
                seen[team] = seen.get(team, 0) + 1
        if season and season_of(row.get("date") or "", row.get("league")) != season:
            continue
        xp_h, xp_a = expected_points(float(xg_h), float(xg_a))
        for side, team, xp in (("h", row.get("home"), xp_h),
                               ("a", row.get("away"), xp_a)):
            if not team:
                continue
            entry = agg.setdefault(team, {
                "matches": 0, "pts": 0.0, "xpts": 0.0, "gf": 0, "ga": 0})
            own, opp = (hg, ag) if side == "h" else (ag, hg)
            entry["matches"] += 1
            entry["gf"] += own
            entry["ga"] += opp
            entry["pts"] += 3 if own > opp else 1 if own == opp else 0
            entry["xpts"] += xp

    # Råa namn per normaliserad nyckel: UI:t har matchens namn som providern
    # skrev det ("GIF Sundsvall"), inte den normaliserade formen. Utan dessa
    # blev uppslaget en grov substrängsjämförelse som ibland missade.
    raw: dict[str, set[str]] = {}
    for row in results:
        for key, rawkey in (("home", "home_raw"), ("away", "away_raw")):
            name, rawname = row.get(key), row.get(rawkey)
            if name and rawname:
                raw.setdefault(name, set()).add(rawname)
    # Oddssidans namn läggs till som variant och vinner via diakriterna i
    # `_display_name`. Uppslaget kräver EXAKT samma normaliserade nyckel —
    # ingen fuzzy-matchning: en felkopplad rad skulle sätta fel klubbnamn på
    # en rad som i övrigt är korrekt, och det är värre än ett tråkigt namn.
    from .oddset import norm_team          # sen import: oddset importerar oss
    for name in odds_names or []:
        key = norm_team(name)
        if key in agg:
            raw.setdefault(key, set()).add(name)

    out = []
    for team, v in agg.items():
        strength = teams.get(team)
        # MIN_MATCHES gäller STYRKESKATTNINGEN och prövas därför mot hela
        # historiken, inte mot det säsongsfiltrerade urvalet. Annars vore
        # varje säsong tom i två månader — och det är inte styrkan som blivit
        # osäker av att man tittar på en kortare period.
        if not strength or seen.get(team, 0) < MIN_MATCHES:
            continue
        out.append({
            "team": team,
            "name": _display_name(team, raw.get(team)),
            "aliases": sorted(raw.get(team, set())),
            "att": round(strength["att"], 3),
            "def": round(strength["def"], 3),
            "ratio": round(strength["att"] / max(strength["def"], 1e-6), 3),
            # samtliga kolumner nedan mäts på SAMMA matcher: de med xG
            "matches": v["matches"],
            "goal_diff": v["gf"] - v["ga"],
            "points": round(v["pts"], 1),
            "xpts": round(v["xpts"], 1),
            # positivt = laget har tagit FLER poäng än chanserna motiverar,
            # alltså kandidat för nedgång
            "overperformance": round(v["pts"] - v["xpts"], 1),
        })
    out.sort(key=lambda r: -r["ratio"])
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out
