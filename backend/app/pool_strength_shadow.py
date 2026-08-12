"""Förregistrerat pool-shadow: Pinnacle mot små lagstyrkeblandningar.

Spåret påverkar inga poolförslag. Vid h24/h3/m20 fryses Pinnacles devigade
1X2-vektor och målmodellens xG-/styrkevektor. Två linjära kandidater mäts:
90 % sharp + 10 % styrka samt 80 % sharp + 20 % styrka. Facit läses senare
ur ``pool_event_settlement``; historiska sannolikheter rekonstrueras aldrig.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Optional

from . import oddset_data, oddset_model, oddset_value, pool_dataset
from .analysis import _normalize_odds
from .oddset import norm_team
from .storage import Storage


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "pool-strength-forward-manifest-v1.json"
SIGNS = ("1", "X", "2")
COL = {"1": "1", "X": "x", "2": "2"}

# Svenska Spels liganamn -> målmodellens explicita liganyckel. Ingen fuzzy
# ligamatchning: en okänd cup/landskamp ska vara synlig som coverage-bortfall.
LEAGUE_ALIASES = {
    "allsvenskan": "allsvenskan",
    "superettan": "superettan",
    "eliteserien": "eliteserien",
    "obos-ligaen": "obosligaen",
    "obos ligaen": "obosligaen",
    "major league soccer": "mls",
    "mls": "mls",
    "premier league": "premier_league",
    "serie a": "serie_a",
    "la liga": "la_liga",
    "bundesliga": "bundesliga",
}


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def shadow_version() -> str:
    raw = json.dumps(load_manifest(), sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"))
    return f"ps-{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def model_signal_version(store: Storage) -> str:
    return oddset_value.signal_versions(store)["model"]


def _league_key(raw: Optional[str]) -> Optional[str]:
    return LEAGUE_ALIASES.get((raw or "").strip().casefold())


def _calibration(store: Storage, league: str) -> float:
    raw = store.meta_get(f"oddset_cal:{league}")
    if not raw:
        head = oddset_model.FIT_POOLS.get(league, (league,))[0]
        raw = store.meta_get(f"oddset_cal:{head}")
    try:
        return float((json.loads(raw or "{}").get("t") or 1.0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1.0


def _canonical_team(store: Storage, league: str, fit: dict,
                    raw_name: str) -> Optional[str]:
    """Exakt kanon först, sedan explicit alias — aldrig fuzzy/substräng."""
    name = norm_team(raw_name)
    if name in fit.get("teams", {}):
        return name
    target = oddset_data._alias_map(store, league).get(name)
    return target if target in fit.get("teams", {}) else None


def _model_probs(store: Storage, league: str, home: str, away: str,
                 now: dt.datetime, fits: dict) -> tuple[Optional[dict], str]:
    pool = oddset_model.FIT_POOLS.get(league, (league,))
    if pool not in fits:
        rows = []
        for pool_league in pool:
            rows.extend(oddset_data.merged_results(store, pool_league))
        fits[pool] = oddset_model.fit_league(rows, now=now.date())
    fit = fits[pool]
    if not fit:
        return None, "missing_fit"
    hn = _canonical_team(store, league, fit, home)
    an = _canonical_team(store, league, fit, away)
    if not hn or not an:
        return None, "unlinked_team"
    if (fit["teams"][hn]["n"] < oddset_model.MIN_MATCHES or
            fit["teams"][an]["n"] < oddset_model.MIN_MATCHES):
        # Poolspåret v1 använder ingen fuzzy Elo-prior. Tunn historik får
        # falla stängt tills en separat prior-hypotes har förregistrerats.
        return None, "thin_history"
    mus = oddset_model.predict(fit, hn, an, league=league)
    if not mus:
        return None, "missing_prediction"
    matrix = oddset_model.temper(
        oddset_model.dc_matrix(*mus), _calibration(store, league))
    return oddset_model.matrix_1x2(matrix), "ok"


def _blend(sharp: dict, model: dict, weight: float) -> dict:
    out = {sign: ((1.0 - weight) * sharp[sign] + weight * model[sign])
           for sign in SIGNS}
    total = sum(out.values()) or 1.0
    return {sign: out[sign] / total for sign in SIGNS}


def capture_due(store: Storage, product: str, draw, sharp_result: Optional[dict],
                now: Optional[dt.datetime] = None) -> dict:
    """Frys en horisont när både kupongen och en riktig sharp-läsning finns."""
    now = now or dt.datetime.now(dt.timezone.utc)
    horizon = pool_dataset.horizon_window_open(draw.reg_close_time, now=now)
    report = {"horizon": horizon, "captured": 0, "eligible": 0}
    if not horizon:
        return report
    if (not sharp_result or sharp_result.get("skipped") or
            sharp_result.get("pinnacle_error")):
        report["error"] = "sharp_not_observed"
        return report
    manifest = load_manifest()
    current_model = model_signal_version(store)
    if current_model != manifest["source_versions"]["model_signal_version"]:
        report["error"] = "model_source_version_changed"
        return report
    close = _parse(draw.reg_close_time)
    minutes = pool_dataset.HORIZONS[horizon]
    target = close - dt.timedelta(minutes=minutes)
    delay = round((now - target).total_seconds() / 60, 1)
    hits = sharp_result.get("hits") or {}
    version = shadow_version()
    fits: dict = {}
    rows = []
    for match in draw.matches:
        league = _league_key(match.league)
        hit = hits.get(match.event_number) or {}
        sharp = _normalize_odds(hit.get("odds") or {})
        if any(sharp.get(sign) is None for sign in SIGNS):
            sharp = None
        model, model_issue = (None, "unsupported_league")
        if league in oddset_data.MODEL_LEAGUES:
            model, model_issue = _model_probs(
                store, league, match.home, match.away, now, fits)
        eligible = bool(sharp and model and not match.cancelled)
        if match.cancelled:
            issue = "cancelled"
        elif not league or league not in oddset_data.MODEL_LEAGUES:
            issue = "unsupported_league"
        elif not sharp:
            issue = "missing_sharp"
        elif not model:
            issue = model_issue
        else:
            issue = None
        b10 = _blend(sharp, model, 0.10) if eligible else None
        b20 = _blend(sharp, model, 0.20) if eligible else None
        values = {
            "sharp": sharp, "model": model, "blend10": b10, "blend20": b20,
        }
        prob_values = []
        for family in ("sharp", "model", "blend10", "blend20"):
            for sign in SIGNS:
                prob_values.append(
                    round(values[family][sign], 8) if values[family] else None)
        rows.append((
            product, draw.draw_number, horizon, match.event_number, version,
            current_model, _iso(now), _iso(target), delay, match.match_start,
            match.league, league, match.home, match.away, int(eligible), issue,
            *prob_values,
        ))
    before = store.conn.total_changes
    with store.bulk():
        store.conn.executemany(
            "INSERT OR IGNORE INTO pool_strength_shadow_capture "
            "(product,draw_number,horizon,event_number,shadow_version,"
            "model_signal_version,captured_at,target_at,delay_min,match_start,"
            "league_raw,league,home,away,eligible,issue,"
            "p_sharp_1,p_sharp_x,p_sharp_2,p_model_1,p_model_x,p_model_2,"
            "p_blend10_1,p_blend10_x,p_blend10_2,"
            "p_blend20_1,p_blend20_x,p_blend20_2) "
            f"VALUES ({','.join('?' for _ in range(28))})", rows)
    report["captured"] = store.conn.total_changes - before
    report["eligible"] = sum(row[14] for row in rows)
    report["shadow_version"] = version
    return report


def _bootstrap_ci(clustered: dict[str, list[float]], seed: str,
                  iters: int = 1200) -> Optional[list[float]]:
    clusters = list(clustered.values())
    if len(clusters) < 10:
        return None
    rng = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16))
    means = []
    for _ in range(iters):
        sample = [rng.choice(clusters) for _ in clusters]
        flat = [value for cluster in sample for value in cluster]
        means.append(sum(flat) / len(flat))
    means.sort()
    return [round(means[int(0.05 * (iters - 1))], 6),
            round(means[int(0.95 * (iters - 1))], 6)]


def _metric(rows: list[dict], family: str, seed: str) -> dict:
    deltas, by_league, clusters = [], {}, {}
    suffix = {"1": "1", "X": "x", "2": "2"}
    for row in rows:
        sign = row["outcome"]
        col = suffix[sign]
        sharp = row[f"p_sharp_{col}"]
        candidate = row[f"p_{family}_{col}"]
        if not sharp or not candidate:
            continue
        delta = -math.log(sharp) - (-math.log(candidate))
        deltas.append(delta)
        by_league.setdefault(row["league"], []).append(delta)
        clusters.setdefault(row["cluster"], []).append(delta)
    return {
        "candidate": family,
        "n": len(deltas),
        "mean_delta_logloss": (round(sum(deltas) / len(deltas), 6)
                               if deltas else None),
        "ci90": _bootstrap_ci(clusters, seed) if deltas else None,
        "by_league": {league: {
            "n": len(values), "mean_delta_logloss": round(
                sum(values) / len(values), 6)}
            for league, values in sorted(by_league.items())},
    }


def report(store: Storage, product: Optional[str] = None,
           products: Optional[list[str]] = None) -> dict:
    """Mät ett enskilt spel, en hel spelfamilj eller alla produkter.

    `products` används för familjer. Då dedupliceras samma match på samma sätt
    som i globalvyn; annars skulle en match på två Topptipset-varianter väga
    dubbelt bara för att den råkade ligga på två kuponger.
    """
    manifest = load_manifest()
    version = shadow_version()
    args: list = [version]
    where = "c.shadow_version=?"
    if products:
        marks = ",".join("?" for _ in products)
        where += f" AND c.product IN ({marks})"
        args.extend(products)
    elif product:
        where += " AND c.product=?"
        args.append(product)
    raw = [dict(row) for row in store.conn.execute(
        "SELECT c.*,e.outcome,e.cancelled FROM pool_strength_shadow_capture c "
        "LEFT JOIN pool_event_settlement e ON e.product=c.product "
        "AND e.draw_number=c.draw_number AND e.event_number=c.event_number "
        f"WHERE {where} ORDER BY c.captured_at,c.product,c.draw_number,c.event_number",
        args)]
    # Samma match kan ligga på flera poolprodukter. Tvärproduktstatus räknar
    # varje match/horizont en gång; produktfilter behåller produktens egen rad.
    unique = {}
    for row in raw:
        key = ((row["product"], row["draw_number"], row["event_number"],
                row["horizon"]) if product and not products else
               (row["league"], row["match_start"], row["home"], row["away"],
                row["horizon"]))
        unique.setdefault(key, row)
    rows = list(unique.values())
    for row in rows:
        # Matchen är den statistiska enheten även i ett produktfilter. Att
        # klustra på omgång skulle göra osäkerheten beroende av vilken kupong
        # matcherna råkade ligga på, trots manifestets unique-match-kontrakt.
        row["cluster"] = (f"{row['league']}:{row['match_start']}:"
                          f"{row['home']}:{row['away']}")
    eligible = [row for row in rows if row["eligible"]]
    settled = [row for row in eligible
               if row.get("outcome") in SIGNS and not row.get("cancelled")]
    issues = {}
    for row in rows:
        if row.get("issue"):
            issues[row["issue"]] = issues.get(row["issue"], 0) + 1
    horizons = {}
    gate = manifest["gate"]
    for horizon in manifest["scope"]["horizons"]:
        subset = [row for row in settled if row["horizon"] == horizon]
        leagues = {}
        for row in subset:
            leagues.setdefault(row["league"], set()).add(row["cluster"])
        league_counts = {key: len(value) for key, value in leagues.items()}
        dates = sorted({row["captured_at"][:10] for row in subset})
        span = ((dt.date.fromisoformat(dates[-1]) -
                 dt.date.fromisoformat(dates[0])).days + 1 if dates else 0)
        represented = sum(n >= gate["minimum_settled_per_league"]
                          for n in league_counts.values())
        data_ready = bool(
            len(subset) >= gate["minimum_settled_events_per_horizon"] and
            represented >= gate["minimum_represented_leagues"] and
            span >= gate["minimum_span_days"])
        horizons[horizon] = {
            "captured": sum(row["horizon"] == horizon for row in rows),
            "eligible": sum(row["horizon"] == horizon for row in eligible),
            "settled": len(subset), "span_days": span,
            "league_counts": league_counts, "data_ready": data_ready,
            "metrics": [
                _metric(subset, family,
                        f"{version}:{product or products}:{horizon}:{family}")
                for family in ("model", "blend10", "blend20")
            ],
        }
    decision = manifest["scope"]["decision_horizons"]
    ready = all(horizons[horizon]["data_ready"] for horizon in decision)
    status = "candidate" if ready else "samlar"
    return {
        "experiment": manifest["experiment"], "shadow_version": version,
        "model_signal_version": manifest["source_versions"]["model_signal_version"],
        "starts_at": manifest["collection"]["starts_at"],
        "status": status, "actionable": False, "affects_systems": False,
        "product": product, "products": products,
        "captured": len(rows), "eligible": len(eligible),
        "settled": len(settled), "coverage": (round(len(eligible) / len(rows), 4)
                                                if rows else None),
        "issues": issues, "gate": gate, "horizons": horizons,
        "decay_half_life_days": round(oddset_model.DECAY_DAYS * math.log(2)),
        "note": ("Första grinden mäter sannolikheter mot riktigt 1X2-utfall. "
                 "Inga poolrader ändras före separat system-shadow och beslut."),
    }
