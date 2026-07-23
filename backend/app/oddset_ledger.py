"""WP5: immutable prediction ledger at fixed pre-match horizons.

The flag log answers "what did we act on?". This ledger answers the broader
research question: what did every available sharp/model prediction say at a
pre-registered time, including selections that were not flags (the control
group). Capture and evaluation are deliberately separate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
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
    for market, signs in (("ah", ("H", "A")), ("ou", ("O", "U"))):
        pair = model.get(market) or {}
        line = pair.get("line")
        if line is None:
            continue
        for sign in signs:
            fair = pair.get(f"p{sign}")
            if fair is not None:
                rows.append(_row(
                    market, sign, line, fair, "model", True, True, odds,
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
    feature_builder = None
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
            added = store.oddset_capture_predictions(capture, rows)
            if tier == "model" and match.get("league") in ("allsvenskan", "eliteserien"):
                # V2-A fryser inputen vid exakt samma as_of. Funktionen ändrar
                # inga sannolikheter och reconstructed backfill hålls separat.
                if feature_builder is None:
                    from .oddset_v2 import FeatureBuilder
                    feature_builder = FeatureBuilder(store)
                feature_builder.capture(match, capture, "live")
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
               row["signal_version"])
        grouped.setdefault(key, []).append(row)
    return rows, grouped


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
            "active_version": version == current_versions.get(tier),
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
    if update_states:
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
        "groups": groups,
    }
