"""WP5: immutable prediction ledger at fixed pre-match horizons.

The flag log answers "what did we act on?". This ledger answers the broader
research question: what did every available sharp/model prediction say at a
pre-registered time, including selections that were not flags (the control
group). Capture and evaluation are deliberately separate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
from typing import Optional

from . import oddset_value
from .storage import Storage


HORIZONS = (("m20", 20), ("h3", 180), ("h24", 1440))
HORIZON_MAX_DELAY = {"m20": 10, "h3": 15, "h24": 45}
PREDICTION_POLICY = {
    "schema": 1,
    "horizons_min": {key: minutes for key, minutes in HORIZONS},
    "flag_edge": oddset_value.EDGE_LOG,
    "best_book": True,
    "sharp_direct_only": True,
    "closing": "exact-line-fresh-v1",
}
WINSOR_EV = 0.20
BOOTSTRAP_ITERS = 1000
CANDIDATE_MIN_FLAGS = 50
CANDIDATE_MIN_MATCHES = 30
CANDIDATE_MIN_SPAN_DAYS = 28
GREEN_NEW_MATCHES = 15
FDR_Q = 0.10
PRIMARY_LEAGUES = {
    "allsvenskan", "superettan", "eliteserien", "obosligaen", "mls",
}

# Förregistrerad utvärderingskadens (2026-07-24). Status får bara ändras en
# gång per EVAL_INTERVAL_H, inte vid varje insamlingsvarv — annars blir
# candidate/green ett sekventiellt test med hundratals titt-tillfällen på en
# ensidig 5 %-gräns, och brus lyser förr eller senare grönt. Läsning av
# rapporten är fri; det är BESLUTEN som är kadensstyrda.
EVAL_INTERVAL_H = 168.0          # en gång per vecka
EVAL_META_KEY = "oddset_ledger_last_eval"

# Modell-mot-close: snabb forskningsgrind på ALLA frysta prediktioner, inte
# bara flaggor. Förregistrerad innan utfallet räknades 2026-07-25; se
# docs/modell-mot-close-2026-07-25.md.
MODEL_CLOSE_PAIR_MAX_MIN = 5.0
MODEL_CLOSE_MIN_CASES = 50
MODEL_CLOSE_MIN_MATCHES = 30
MODEL_CLOSE_MIN_SPAN_DAYS = 7
MODEL_CLOSE_DIRECTION_MIN_PP = 0.5


def _evaluation_due(store: Storage, now: dt.datetime) -> bool:
    """True om det gått minst EVAL_INTERVAL_H sedan senaste statusbeslut."""
    last = store.meta_get(EVAL_META_KEY)
    if not last:
        return True
    try:
        since = (now - _parse_iso(last)).total_seconds() / 3600
    except ValueError:
        return True
    return since >= EVAL_INTERVAL_H


def _parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _line_key(line: Optional[float]) -> int:
    return (Storage.ODDSET_NO_LINE_KEY if line is None
            else int(round(float(line) * 1000)))


def horizon_at(match_start: str, now: dt.datetime) -> Optional[tuple[str, int]]:
    """Current capture bucket; earlier missed horizons are never backfilled."""
    remaining = (_parse_iso(match_start) - now).total_seconds() / 60
    if remaining <= 0:
        return None
    return next(((key, minutes) for key, minutes in HORIZONS
                 if remaining <= minutes), None)


def prediction_versions(store: Storage) -> dict[str, dict[str, str]]:
    """Composite versions include both the predictor and ledger flag policy."""
    base = oddset_value.signal_versions(store)
    out = {}
    for tier in ("sharp", "model"):
        version = oddset_value._fingerprint(  # same semantic hash convention
            "s" if tier == "sharp" else "m",
            {"base_version": base[tier], "policy": PREDICTION_POLICY,
             "tier": tier})
        out[tier] = {"signal_version": version, "base_version": base[tier]}
    return out


def _best_book(odds: dict, market: str, sign: str,
               line: Optional[float]) -> Optional[dict]:
    candidates = []
    target_key = _line_key(line)
    for source, markets in odds.items():
        if source == "pinnacle":
            continue
        price = (markets or {}).get(market)
        if not price or not price.get(sign):
            continue
        if market != "1x2" and _line_key(price.get("line")) != target_key:
            continue
        candidates.append({
            "book": source, "odds": price[sign],
            "available": bool(price.get("available")),
            "fresh": bool(price.get("fresh")),
        })
    if not candidates:
        return None
    # A currently actionable price always beats a higher stale quote.
    return max(candidates, key=lambda r: (r["fresh"], r["available"], r["odds"]))


def _row(market: str, sign: str, line: Optional[float], fair: float,
         fair_source: str, fair_available: bool, fair_fresh: bool,
         odds: dict, eligible: bool, anchored: Optional[bool] = None) -> dict:
    book = _best_book(odds, market, sign, line)
    edge = (round(fair * book["odds"] - 1, 4)
            if book and book["fresh"] and fair_fresh else None)
    is_flag = bool(eligible and edge is not None and edge >= oddset_value.EDGE_LOG)
    return {
        "market": market, "sign": sign, "line": line,
        "line_key": _line_key(line), "fair_prob": round(fair, 6),
        "fair_source": fair_source, "fair_available": fair_available,
        "fair_fresh": fair_fresh,
        "model_anchored": None if anchored is None else int(anchored),
        "book": book["book"] if book else None,
        "book_odds": book["odds"] if book else None,
        "book_available": bool(book and book["available"]),
        "book_fresh": bool(book and book["fresh"]),
        "edge": edge, "eligible": eligible, "is_flag": is_flag,
    }


def _sharp_rows(match: dict) -> list[dict]:
    odds = match.get("odds") or {}
    pin = odds.get("pinnacle") or {}
    rows = []
    for market, signs in oddset_value._MARKET_SIGNS.items():
        price = pin.get(market)
        if not price:
            continue
        fair = oddset_value._devig(price, signs)
        if not fair:
            continue
        derived = bool(price.get("derived"))
        available = bool(price.get("available"))
        fresh = bool(price.get("fresh"))
        line = price.get("line")
        for sign in signs:
            rows.append(_row(
                market, sign, line, fair[sign],
                "derived" if derived else "pinnacle", available, fresh,
                odds, eligible=bool(not derived and fresh)))
    return rows


def _model_rows(match: dict) -> list[dict]:
    from . import oddset_model

    odds = match.get("odds") or {}
    model = match.get("model") or {}
    anchored = bool(model.get("anchored"))
    rows = []
    for sign in ("1", "X", "2"):
        fair = (model.get("p") or {}).get(sign)
        if fair is not None:
            rows.append(_row(
                "1x2", sign, None, fair, "model", True, True, odds,
                eligible=True, anchored=anchored))
    for market, signs in (
            ("ah", ("H", "A")), ("ou", ("O", "U")), ("cor", ("O", "U"))):
        pair = model.get(market) or {}
        line = pair.get("line")
        if line is None:
            continue
        for sign in signs:
            fair = pair.get(f"p{sign}")
            if fair is not None:
                rows.append(_row(
                    market, sign, line, fair,
                    (oddset_model.CORNER_MODEL_VERSION
                     if market == "cor" else "model"),
                    True, True, odds,
                    eligible=True, anchored=anchored))
    return rows


def _capture_meta(match: dict, horizon: tuple[str, int], tier: str,
                  version: dict[str, str], now: dt.datetime) -> dict:
    key, minutes = horizon
    start = _parse_iso(match["start"])
    target = start - dt.timedelta(minutes=minutes)
    return {
        "match_id": match["id"], "horizon": key, "tier": tier,
        **version, "league": match.get("league"),
        "description": f"{match.get('home', '?')} – {match.get('away', '?')}",
        "match_start": _iso(start), "target_at": _iso(target),
        "captured_at": _iso(now),
        "offset_minutes": round((start - now).total_seconds() / 60, 1),
        "delay_minutes": round(max(0, (now - target).total_seconds() / 60), 1),
        "git_hash": oddset_value._code_version(),
    }


def due_model_matches(store: Storage, matches: list[dict],
                      now: Optional[dt.datetime] = None) -> list[dict]:
    """Only fit the model in a fast poll when a new fixed horizon is due."""
    from . import oddset_data
    now = now or dt.datetime.now(dt.timezone.utc)
    version = prediction_versions(store)["model"]["signal_version"]
    due = []
    for match in matches:
        if match.get("league") not in oddset_data.MODEL_LEAGUES or not match.get("start"):
            continue
        horizon = horizon_at(match["start"], now)
        if horizon and not store.oddset_prediction_captured(
                match["id"], horizon[0], "model", version):
            due.append(match)
    return due


def capture_predictions(store: Storage, matches: list[dict],
                        tiers: tuple[str, ...] = ("sharp", "model"),
                        now: Optional[dt.datetime] = None) -> dict:
    """Capture all available selections in the current horizon, once."""
    from . import oddset_data
    now = now or dt.datetime.now(dt.timezone.utc)
    versions = prediction_versions(store)
    result = {"captures": 0, "rows": 0, "empty": 0}
    v22_builder = None
    for match in matches:
        if not match.get("start"):
            continue
        horizon = horizon_at(match["start"], now)
        if not horizon:
            continue
        for tier in tiers:
            if tier == "model" and match.get("league") not in oddset_data.MODEL_LEAGUES:
                continue
            version = versions[tier]
            if store.oddset_prediction_captured(
                    match["id"], horizon[0], tier, version["signal_version"]):
                continue
            rows = _sharp_rows(match) if tier == "sharp" else _model_rows(match)
            capture = _capture_meta(match, horizon, tier, version, now)
            from . import oddset_v22
            if tier == "sharp" and match.get("league") in oddset_v22.SCOPE_LEAGUES:
                # V2.2 utgår från sharp-capturen, inte den ordinarie amber-
                # modellens ledgeridentitet. Det håller forskningsligorna helt
                # utanför produktens modellversion/facit. Feature + sharp +
                # shadow är fortfarande atomära och retrybara.
                if v22_builder is None:
                    v22_builder = oddset_v22.FeatureBuilder(store)
                with store.bulk():
                    added = store.oddset_capture_predictions(capture, rows)
                    v22_builder.capture(
                        match, capture, versions["sharp"]["signal_version"])
            else:
                added = store.oddset_capture_predictions(capture, rows)
            result["captures"] += 1
            result["rows"] += added
            result["empty"] += int(not rows)
    return result


def resolve_closings(store: Storage,
                     now: Optional[dt.datetime] = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = store.oddset_unresolved_predictions(_iso(now))
    with store.bulk():
        for row in rows:
            close = oddset_value.closing_snapshot(store, row)
            store.oddset_set_prediction_closing(
                row, close.get("fair"), close.get("odds"), close.get("note"),
                close.get("closing_line"), close.get("line_delta"),
                close.get("line_move_score"))
    return len(rows)


def _seed(key: tuple) -> int:
    raw = "|".join(str(v) for v in key).encode()
    return int(hashlib.sha1(raw).hexdigest()[:8], 16)


def _bootstrap(values: list[dict], key: tuple,
               iters: int = BOOTSTRAP_ITERS) -> tuple[Optional[list[float]], Optional[float]]:
    blocks: dict[str, list[float]] = {}
    for row in values:
        blocks.setdefault(row["match_id"], []).append(row["close_ev_w"])
    if len(blocks) < 3:
        return None, None
    groups = list(blocks.values())
    rng = random.Random(_seed(key))
    means = []
    for _ in range(iters):
        sample = [rng.choice(groups) for _ in groups]
        flat = [value for group in sample for value in group]
        means.append(sum(flat) / len(flat))
    means.sort()
    lo = means[int(iters * 0.05)]
    hi = means[min(iters - 1, int(iters * 0.95))]
    # BH behöver ett p-värde under nollhypotesen, inte svansen i en vanlig
    # bootstrapfördelning som är centrerad på observerat medel. Kluster-
    # signflip behåller all korrelation inom match men centrerar H0 vid noll.
    observed = sum(value for group in groups for value in group) / sum(map(len, groups))
    null_means = []
    null_rng = random.Random(_seed((*key, "null")))
    for _ in range(iters):
        signed = []
        for group in groups:
            flip = null_rng.choice((-1, 1))
            signed.append([value * flip for value in group])
        flat = [value for group in signed for value in group]
        null_means.append(sum(flat) / len(flat))
    p = ((1 + sum(mean >= observed for mean in null_means)) / (iters + 1)
         if observed > 0 else 1.0)
    return [round(lo, 4), round(hi, 4)], round(p, 4)


def _span(rows: list[dict]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    dates = [_parse_iso(row["match_start"]) for row in rows]
    span = max(0, int((max(dates) - min(dates)).total_seconds() // 86400))
    weeks = len({(date.isocalendar().year, date.isocalendar().week) for date in dates})
    return span, weeks


def _group_stats(rows: list[dict], key: tuple) -> dict:
    timely = [row for row in rows if row.get("timely")]
    eligible = [row for row in timely if row.get("eligible")]
    flags = [row for row in eligible if row.get("is_flag")]
    resolved = [row for row in flags if row.get("close_ev") is not None]
    span_days, n_weeks = _span(resolved)
    n_matches = len({row["match_id"] for row in resolved})
    ci, p_value = _bootstrap(resolved, key)
    avg = (sum(row["close_ev"] for row in resolved) / len(resolved)
           if resolved else None)
    avg_w = (sum(row["close_ev_w"] for row in resolved) / len(resolved)
             if resolved else None)
    testable = bool(len(resolved) >= CANDIDATE_MIN_FLAGS
                    and n_matches >= CANDIDATE_MIN_MATCHES
                    and span_days >= CANDIDATE_MIN_SPAN_DAYS and p_value is not None)
    return {
        "n_predictions": len(rows), "n_timely": len(timely),
        "n_late": len(rows) - len(timely), "n_eligible": len(eligible),
        "n_controls": sum(not row.get("is_flag") for row in eligible),
        "n_flags": len(flags), "n_resolved": len(resolved),
        "n_matches": n_matches, "n_weeks": n_weeks, "span_days": span_days,
        "first_resolved_at": (min(row["match_start"] for row in resolved)
                              if resolved else None),
        "last_resolved_at": (max(row["match_start"] for row in resolved)
                             if resolved else None),
        "avg_close_ev": round(avg, 4) if avg is not None else None,
        "avg_close_ev_w": round(avg_w, 4) if avg_w is not None else None,
        "ci": ci, "ci_stable": n_matches >= 10, "p_value": p_value,
        "testable": testable,
        "candidate_base": bool(testable and ci and ci[0] > 0),
    }


def _candidate_eta(group: dict, now: dt.datetime) -> Optional[str]:
    """Försiktig tidigaste prognos för mängd- och tidsgaten.

    KI-gaten kan inte prognostiseras. Datumet säger därför bara när 50 stängda
    flaggor, 30 matcher och 28 dagars bredd kan vara uppnådda vid hittillsvarande
    takt. För små stickprov får inget skenexakt datum.
    """
    if group["status"] != "amber" or not group["primary"] \
            or not group["active_version"]:
        return None
    first_raw = group.get("first_resolved_at")
    if not first_raw or group["n_resolved"] < 3 or group["n_matches"] < 3:
        return None
    first = _parse_iso(first_raw)
    age_days = max(1.0, (now - first).total_seconds() / 86400)
    flag_rate = group["n_resolved"] / age_days
    match_rate = group["n_matches"] / age_days
    if flag_rate <= 0 or match_rate <= 0:
        return None
    flag_gate = now + dt.timedelta(
        days=max(0, CANDIDATE_MIN_FLAGS - group["n_resolved"]) / flag_rate)
    match_gate = now + dt.timedelta(
        days=max(0, CANDIDATE_MIN_MATCHES - group["n_matches"]) / match_rate)
    span_gate = first + dt.timedelta(days=CANDIDATE_MIN_SPAN_DAYS)
    return _iso(max(flag_gate, match_gate, span_gate))


def _bh_pass(groups: list[dict]) -> set[tuple]:
    tested = sorted(
        ((group["p_value"], group["key"]) for group in groups
         if not group["primary"] and group["testable"]),
        key=lambda item: item[0])
    accepted = 0
    for rank, (p_value, _) in enumerate(tested, 1):
        if p_value <= rank / len(tested) * FDR_Q:
            accepted = rank
    return {key for _, key in tested[:accepted]}


def _prepare_rows(store: Storage) -> tuple[list[dict], dict[tuple, list[dict]]]:
    rows = store.oddset_prediction_rows()
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        row["timely"] = bool(
            row.get("delay_minutes") is not None
            and row["delay_minutes"] <= HORIZON_MAX_DELAY[row["horizon"]])
        if row.get("closing_fair") is not None and row.get("book_odds") \
                and row.get("book_fresh"):
            close_ev = row["closing_fair"] * row["book_odds"] - 1
            row["close_ev"] = round(close_ev, 6)
            row["close_ev_w"] = max(-WINSOR_EV, min(WINSOR_EV, close_ev))
        else:
            row["close_ev"] = row["close_ev_w"] = None
        key = (row["tier"], row.get("league") or "?", row["market"],
               _evaluation_version(row))
        grouped.setdefault(key, []).append(row)
    return rows, grouped


def _evaluation_version(row: dict) -> str:
    """Marknadsspecifik metodversion utan att bumpa orelaterade modeller.

    Hörnmodellen tillkom som en ny marknad. Att lägga dess metod i den globala
    målmodellens fingerprint skulle felaktigt nollställa 1X2/AH/ÖU och V2.2.
    Fair-källan bär därför hörnmetoden och blir del av just hörngruppens version.
    """
    if row.get("tier") == "model" and row.get("market") == "cor":
        return f"{row['signal_version']}:{row.get('fair_source') or 'corner-unknown'}"
    return row["signal_version"]


def _active_evaluation_version(tier: str, market: str, version: str,
                               current_versions: dict[str, str]) -> bool:
    if tier == "model" and market == "cor":
        from . import oddset_model
        return version == (
            f"{current_versions['model']}:{oddset_model.CORNER_MODEL_VERSION}")
    return version == current_versions.get(tier)


def _prob_vector(rows: dict[str, dict], field: str,
                 signs: tuple[str, ...]) -> Optional[dict[str, float]]:
    """Komplett, normaliserad sannolikhetsvektor eller None."""
    try:
        raw = {sign: float(rows[sign][field]) for sign in signs}
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value <= 0 for value in raw.values()):
        return None
    total = sum(raw.values())
    if total <= 0:
        return None
    return {sign: value / total for sign, value in raw.items()}


def _model_close_cases(rows: list[dict]) -> tuple[list[dict], dict]:
    """Para kompletta modellvektorer med direkt sharp vid samma horisont/lina."""
    sharp_groups: dict[tuple, dict[str, dict]] = {}
    model_groups: dict[tuple, dict[str, dict]] = {}
    for row in rows:
        market = row.get("market")
        signs = oddset_value._MARKET_SIGNS.get(market)
        if not signs or row.get("horizon") not in HORIZON_MAX_DELAY:
            continue
        timely = (row.get("delay_minutes") is not None
                  and row["delay_minutes"] <= HORIZON_MAX_DELAY[row["horizon"]])
        if not timely:
            continue
        common = (
            row["match_id"], row["horizon"], market, row["line_key"],
            row["signal_version"], row["captured_at"],
        )
        if (row.get("tier") == "sharp"
                and row.get("fair_source") == "pinnacle"
                and row.get("fair_available") and row.get("fair_fresh")
                and row.get("closing_fair") is not None):
            sharp_groups.setdefault(common, {})[row["sign"]] = row
        elif (row.get("tier") == "model"
              and row.get("fair_available") and row.get("fair_fresh")
              and row.get("closing_fair") is not None):
            model_groups.setdefault(common, {})[row["sign"]] = row

    sharp_index: dict[tuple, list[dict]] = {}
    for key, selections in sharp_groups.items():
        match_id, horizon, market, line_key, version, captured_at = key
        signs = oddset_value._MARKET_SIGNS[market]
        sharp = _prob_vector(selections, "fair_prob", signs)
        close = _prob_vector(selections, "closing_fair", signs)
        if not sharp or not close:
            continue
        sharp_index.setdefault(
            (match_id, horizon, market, line_key), []).append({
                "version": version, "captured_at": captured_at,
                "selections": selections, "sharp": sharp, "close": close,
            })

    cases = []
    diagnostics = {
        "n_model_vectors": len(model_groups),
        "n_complete_model_vectors": 0,
        "n_no_matching_sharp": 0,
        "n_close_mismatch": 0,
    }
    for key, selections in model_groups.items():
        match_id, horizon, market, line_key, version, captured_at = key
        signs = oddset_value._MARKET_SIGNS[market]
        model = _prob_vector(selections, "fair_prob", signs)
        close = _prob_vector(selections, "closing_fair", signs)
        if not model or not close:
            continue
        diagnostics["n_complete_model_vectors"] += 1
        model_at = _parse_iso(captured_at)
        candidates = []
        for candidate in sharp_index.get(
                (match_id, horizon, market, line_key), []):
            delta_min = abs(
                (_parse_iso(candidate["captured_at"]) - model_at).total_seconds()
            ) / 60
            if delta_min <= MODEL_CLOSE_PAIR_MAX_MIN:
                candidates.append((delta_min, candidate))
        if not candidates:
            diagnostics["n_no_matching_sharp"] += 1
            continue
        _, paired = min(candidates, key=lambda item: item[0])
        if any(abs(close[sign] - paired["close"][sign]) > 0.0002
               for sign in signs):
            # Båda ledgerraderna ska ha sett samma exakta close. Avvikelse
            # betyder att de inte är ett säkert par, inte att den ena vinner.
            diagnostics["n_close_mismatch"] += 1
            continue

        ce_model = -sum(close[sign] * math.log(model[sign]) for sign in signs)
        ce_sharp = -sum(
            close[sign] * math.log(paired["sharp"][sign]) for sign in signs)
        model_abs = [
            abs(model[sign] - close[sign]) * 100 for sign in signs]
        sharp_abs = [
            abs(paired["sharp"][sign] - close[sign]) * 100 for sign in signs]
        direction_hits = direction_n = 0
        for sign in signs:
            model_shift = model[sign] - paired["sharp"][sign]
            close_shift = close[sign] - paired["sharp"][sign]
            if (abs(model_shift) * 100 >= MODEL_CLOSE_DIRECTION_MIN_PP
                    and abs(close_shift) > 1e-9):
                direction_n += 1
                direction_hits += int(model_shift * close_shift > 0)
        first = next(iter(selections.values()))
        cases.append({
            "match_id": match_id, "horizon": horizon, "market": market,
            "line_key": line_key,
            "model_version": _evaluation_version(next(iter(selections.values()))),
            "sharp_version": paired["version"], "league": first.get("league") or "?",
            "description": first.get("description"), "match_start": first["match_start"],
            "captured_at": captured_at, "n_selections": len(signs),
            "logscore_gain": ce_sharp - ce_model,
            "model_mae_pp": sum(model_abs) / len(model_abs),
            "sharp_mae_pp": sum(sharp_abs) / len(sharp_abs),
            "mae_gain_pp": (
                sum(sharp_abs) / len(sharp_abs)
                - sum(model_abs) / len(model_abs)),
            "model_bias_pp": (
                sum((model[sign] - close[sign]) * 100 for sign in signs)
                / len(signs)),
            "direction_hits": direction_hits, "direction_n": direction_n,
        })
    diagnostics["n_paired_cases"] = len(cases)
    return cases, diagnostics


def _paired_metric_ci(cases: list[dict], field: str,
                      key: tuple, iters: int = BOOTSTRAP_ITERS
                      ) -> Optional[list[float]]:
    """90 %-KI med matchen som block; flera horisonter är korrelerade."""
    blocks: dict[str, list[float]] = {}
    for case in cases:
        blocks.setdefault(case["match_id"], []).append(case[field])
    if len(blocks) < 3:
        return None
    groups = list(blocks.values())
    rng = random.Random(_seed((*key, field)))
    means = []
    for _ in range(iters):
        sample = [rng.choice(groups) for _ in groups]
        flat = [value for group in sample for value in group]
        means.append(sum(flat) / len(flat))
    means.sort()
    return [
        round(means[int(iters * 0.05)], 6),
        round(means[min(iters - 1, int(iters * 0.95))], 6),
    ]


def _model_close_group(cases: list[dict], key: tuple,
                       active_version: str) -> dict:
    n_matches = len({case["match_id"] for case in cases})
    dates = [_parse_iso(case["match_start"]) for case in cases]
    span_days = (max(0, int((max(dates) - min(dates)).total_seconds() // 86400))
                 if dates else 0)
    logscore_gain = (
        sum(case["logscore_gain"] for case in cases) / len(cases)
        if cases else None)
    model_mae = (
        sum(case["model_mae_pp"] for case in cases) / len(cases)
        if cases else None)
    sharp_mae = (
        sum(case["sharp_mae_pp"] for case in cases) / len(cases)
        if cases else None)
    mae_gain = (
        sum(case["mae_gain_pp"] for case in cases) / len(cases)
        if cases else None)
    bias = (
        sum(case["model_bias_pp"] for case in cases) / len(cases)
        if cases else None)
    direction_n = sum(case["direction_n"] for case in cases)
    direction_hits = sum(case["direction_hits"] for case in cases)
    logscore_ci = _paired_metric_ci(cases, "logscore_gain", key)
    mae_ci = _paired_metric_ci(cases, "mae_gain_pp", key)
    testable = bool(
        len(cases) >= MODEL_CLOSE_MIN_CASES
        and n_matches >= MODEL_CLOSE_MIN_MATCHES
        and span_days >= MODEL_CLOSE_MIN_SPAN_DAYS
        and logscore_ci)
    if not testable:
        status = "collecting"
    elif logscore_ci[0] > 0:
        status = "better"
    elif logscore_ci[1] < 0:
        status = "worse"
    else:
        status = "inconclusive"
    version = cases[0]["model_version"] if cases else key[-1]
    if cases and cases[0]["market"] == "cor":
        from . import oddset_model
        version_active = version == (
            f"{active_version}:{oddset_model.CORNER_MODEL_VERSION}")
    else:
        version_active = version == active_version
    return {
        "market": cases[0]["market"] if cases else None,
        "version": version, "active_version": version_active,
        "n_cases": len(cases), "n_matches": n_matches,
        "n_selections": sum(case["n_selections"] for case in cases),
        "span_days": span_days,
        "logscore_gain": (round(logscore_gain, 6)
                          if logscore_gain is not None else None),
        "logscore_gain_ci": logscore_ci,
        "model_mae_pp": round(model_mae, 3) if model_mae is not None else None,
        "sharp_mae_pp": round(sharp_mae, 3) if sharp_mae is not None else None,
        "mae_gain_pp": round(mae_gain, 3) if mae_gain is not None else None,
        "mae_gain_ci": mae_ci,
        "model_bias_pp": round(bias, 3) if bias is not None else None,
        "direction_n": direction_n,
        "direction_hit_rate": (
            round(direction_hits / direction_n, 4) if direction_n else None),
        "testable": testable, "status": status,
    }


def model_close_report_from_rows(
        rows: list[dict], active_version: str) -> dict:
    """Modellens parade närhet till close relativt frozen sharp."""
    cases, diagnostics = _model_close_cases(rows)

    def grouped(fields: tuple[str, ...]) -> list[dict]:
        buckets: dict[tuple, list[dict]] = {}
        for case in cases:
            group_key = tuple(case[field] for field in fields)
            buckets.setdefault(group_key, []).append(case)
        result = []
        for group_key, group_cases in buckets.items():
            report = _model_close_group(
                group_cases, (*fields, *group_key), active_version)
            for field, value in zip(fields, group_key):
                if field != "model_version":
                    report[field] = value
            result.append(report)
        return sorted(result, key=lambda item: (
            not item["active_version"], item.get("market") or "",
            item.get("horizon") or "", item.get("league") or "",
            item["version"]))

    return {
        **diagnostics,
        "active_version": active_version,
        "criteria": {
            "n_cases": MODEL_CLOSE_MIN_CASES,
            "n_matches": MODEL_CLOSE_MIN_MATCHES,
            "span_days": MODEL_CLOSE_MIN_SPAN_DAYS,
            "pair_max_minutes": MODEL_CLOSE_PAIR_MAX_MIN,
            "primary_metric": "paired_logscore_gain_vs_frozen_sharp",
            "ci": 0.90,
        },
        "summary": grouped(("market", "model_version")),
        "horizons": grouped(("market", "horizon", "model_version")),
        "leagues": grouped(("league", "market", "model_version")),
    }


def prediction_report(store: Storage, update_states: bool = False,
                      now: Optional[dt.datetime] = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    now_iso = _iso(now)
    current_versions = {
        tier: version["signal_version"]
        for tier, version in prediction_versions(store).items()
    }
    rows, grouped = _prepare_rows(store)
    groups = []
    for key, grows in grouped.items():
        tier, league, market, version = key
        groups.append({
            "key": key, "tier": tier, "league": league, "market": market,
            "version": version,
            "active_version": _active_evaluation_version(
                tier, market, version, current_versions),
            "primary": (tier == "sharp" and market == "1x2"
                        and league in PRIMARY_LEAGUES),
            **_group_stats(grows, key),
        })
    fdr_pass = _bh_pass(groups)
    for group in groups:
        group["fdr_pass"] = group["primary"] or group["key"] in fdr_pass
        group["candidate_ready"] = bool(
            group["candidate_base"] and group["fdr_pass"])

    states = store.oddset_prediction_states()
    if update_states and not _evaluation_due(store, now):
        # SEKVENTIELL TESTNING (2026-07-24): statusövergångarna kördes vid
        # VARJE insamlingsvarv (var 30:e min, tätare nära avspark). Det ger
        # hundratals titt-tillfällen på en ensidig 5 %-gräns, och under
        # nollhypotesen passerar en ren brusvandring då långt oftare än 5 %.
        # Utvärderingen är nu begränsad till en förregistrerad kadens
        # (EVAL_INTERVAL_H); rapporten kan läsas när som helst, men status
        # får bara ÄNDRAS vid ett schemalagt tillfälle.
        update_states = False
    if update_states:
        store.meta_set(EVAL_META_KEY, now_iso)
        for group in groups:
            key = group["key"]
            if key not in states and group["candidate_ready"]:
                store.oddset_set_prediction_state(key, "candidate", now_iso)
        states = store.oddset_prediction_states()
        for group in groups:
            state = states.get(group["key"])
            if not state or state["status"] != "candidate":
                continue
            post = [row for row in grouped[group["key"]]
                    if row.get("is_flag") and row["captured_at"] > state["candidate_at"]
                    and row.get("close_ev") is not None]
            post_ci, _ = _bootstrap(post, (*group["key"], "post"))
            if len({row["match_id"] for row in post}) >= GREEN_NEW_MATCHES \
                    and post_ci and post_ci[0] > 0:
                store.oddset_set_prediction_state(group["key"], "green", now_iso)
        states = store.oddset_prediction_states()

    for group in groups:
        state = states.get(group["key"], {})
        group["status"] = state.get("status", "amber")
        group["candidate_at"] = state.get("candidate_at")
        group["green_at"] = state.get("green_at")
        post = [row for row in grouped[group["key"]]
                if state.get("candidate_at") and row.get("is_flag")
                and row["captured_at"] > state["candidate_at"]
                and row.get("close_ev") is not None]
        post_ci, _ = _bootstrap(post, (*group["key"], "post")) if post else (None, None)
        group["post_candidate_matches"] = len({row["match_id"] for row in post})
        group["post_candidate_ci"] = post_ci
        group["candidate_eta_at"] = _candidate_eta(group, now)
        group.pop("key")

    groups.sort(key=lambda group: (
        not group["active_version"],
        {"green": 0, "candidate": 1, "amber": 2}[group["status"]],
        not group["primary"], group["tier"], group["league"], group["market"]))
    captures = store.oddset_prediction_captures()
    capture_quality = {}
    for key, _ in HORIZONS:
        subset = [capture for capture in captures if capture["horizon"] == key]
        delays = sorted(capture["delay_minutes"] for capture in subset)
        capture_quality[key] = {
            "n": len(subset),
            "n_timely": sum(delay <= HORIZON_MAX_DELAY[key] for delay in delays),
            "avg_delay_minutes": (round(sum(delays) / len(delays), 1)
                                  if delays else None),
            "max_delay_minutes": max(delays) if delays else None,
            "tolerance_minutes": HORIZON_MAX_DELAY[key],
        }
    return {
        "n_predictions": len(rows), "n_captures": len(captures),
        "n_empty_captures": sum(capture["row_count"] == 0 for capture in captures),
        "horizons": {key: sum(capture["horizon"] == key for capture in captures)
                     for key, _ in HORIZONS},
        "capture_quality": capture_quality,
        "current_versions": current_versions,
        "criteria": {
            "candidate": {
                "n_resolved": CANDIDATE_MIN_FLAGS,
                "n_matches": CANDIDATE_MIN_MATCHES,
                "span_days": CANDIDATE_MIN_SPAN_DAYS,
                "ci_lower_above": 0,
            },
            "green": {"new_matches": GREEN_NEW_MATCHES, "ci_lower_above": 0},
        },
        "model_close": model_close_report_from_rows(
            rows, current_versions["model"]),
        "groups": groups,
    }


def dashboard_summary(store: Storage) -> dict:
    """Billig ledgerstatus för Idag-vyn, utan bootstrap eller close-upplösning.

    Den fulla rapporten är ett forskningsverktyg och räknar om bootstrap-KI:n
    för alla grupper. Startsidan visar bara insamlingsantal och status för de
    primära sharp/1X2-grupperna; att köra hela rapporten där gav flera sekunders
    väntan utan att resten av resultatet användes.
    """
    current_versions = {
        tier: version["signal_version"]
        for tier, version in prediction_versions(store).items()
    }
    compact = store.oddset_prediction_dashboard_summary(
        current_versions["sharp"], PRIMARY_LEAGUES, HORIZON_MAX_DELAY)
    states = store.oddset_prediction_states()
    groups = []
    for row in compact["groups"]:
        tier, league, market = "sharp", row["league"], "1x2"
        version = row["signal_version"]
        key = (tier, league, market, version)
        groups.append({
            "tier": tier, "league": league, "market": market,
            "version": version, "active_version": True, "primary": True,
            "n_resolved": row["n_resolved"],
            "status": states.get(key, {}).get("status", "amber"),
        })
    groups.sort(key=lambda group: group["league"])
    return {
        "n_predictions": compact["n_predictions"],
        "n_captures": compact["n_captures"],
        "current_versions": current_versions,
        "groups": groups,
    }
