"""PH2: PIT-dataset för poolspelen — frysta features per omgång/horisont.

Bygger ENBART på lokalt observerade snapshots (`cohort=observed_pit`):
final_only-omgångar har per definition inga horisonter och får ALDRIG
låtsas ha rörelser. Allt läses "as of" horisontens cutoff (spelstopp −
24 h / 3 h / 20 min); senaste faktiskt observerade punkt före cutoff
används och laggen redovisas. Finalvärden används aldrig som input.

Features per match: devigad SvS-/sharp-sannolikhet, slutstreck-nivå vid
as-of, first→as-of-rörelse i devigade procentenheter, gap = p_marknad −
streck/100, sen streck-mot-sharp-reversal. Per omgång: täckning, folk-/
marknadsentropi, favorittryck, svårighet samt omsättning/jackpot om de
VERKLIGEN var kända vid as-of (pool_draw_snapshot-serien — framåtriktad,
null historiskt).

Deterministisk och idempotent per (nyckel, FEATURE_VERSION): en ändring av
beräkningen kräver ny version, aldrig overwrite.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Optional

from .analysis import _normalize_odds
from .storage import Storage

FEATURE_VERSION = "pit-v1"
COHORT = "observed_pit"
HORIZONS = {"h24": 1440, "h3": 180, "m20": 20}
SIGNS = ("1", "X", "2")
_COL = {"1": "1", "X": "x", "2": "2"}   # kolumnsuffix

REVERSAL_WINDOW_MIN = 180   # sista 3 h före as-of
REVERSAL_STRECK_PP = 1.0    # folket ≥1 pp åt ena hållet …
REVERSAL_SHARP_PP = 0.5     # … medan devigad sharp ≥0,5 pp åt andra


def _parse(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def record_draw_snapshot(store: Storage, product: str, draw_number: int,
                         net_sale: Optional[float], jackpot: Optional[float],
                         at: Optional[str] = None) -> int:
    """Framåtriktad omsättnings-/jackpottserie. Skriver bara vid förändring."""
    last = store.conn.execute(
        "SELECT net_sale, jackpot FROM pool_draw_snapshot "
        "WHERE product=? AND draw_number=? ORDER BY fetched_at DESC LIMIT 1",
        (product, draw_number)).fetchone()
    if last and last[0] == net_sale and last[1] == jackpot:
        return 0
    store.conn.execute(
        "INSERT OR IGNORE INTO pool_draw_snapshot "
        "(product, draw_number, fetched_at, net_sale, jackpot) VALUES (?,?,?,?,?)",
        (product, draw_number, at or _iso(dt.datetime.now(dt.timezone.utc)),
         net_sale, jackpot))
    if not store._bulk:  # noqa: SLF001
        store.conn.commit()
    return 1


def _series(store: Storage, table: str, product: str, draw_number: int,
            cutoff: str) -> dict[int, dict[str, list[tuple[str, Optional[float], Optional[int]]]]]:
    """{event: {sign: [(fetched_at, odds, streck), …]}} t.o.m. cutoff."""
    has_streck = table == "snapshots"
    cols = "event_number, sign, odds" + (", streck" if has_streck else "")
    out: dict[int, dict[str, list]] = {}
    for row in store.conn.execute(
            f"SELECT {cols}, fetched_at FROM {table} "
            "WHERE product=? AND draw_number=? AND fetched_at<=? "
            "ORDER BY fetched_at", (product, draw_number, cutoff)):
        if has_streck:
            event, sign, odds, streck, ts = row
        else:
            event, sign, odds, ts = row
            streck = None
        out.setdefault(int(event), {}).setdefault(sign, []).append(
            (ts, odds, streck))
    return out


def _probs_at_index(sers: dict[str, list], idx) -> Optional[dict[str, float]]:
    odds = {}
    for sign in SIGNS:
        seq = sers.get(sign) or []
        if not seq:
            return None
        _, o, _ = idx(seq)
        if not o or o <= 0:
            return None
        odds[sign] = o
    probs = _normalize_odds(odds)
    return None if any(probs[s] is None for s in SIGNS) else probs


def _at_or_before(seq: list, cutoff: str):
    """Senaste punkten ≤ cutoff (sekvensen är redan filtrerad ≤ yttre cutoff)."""
    best = None
    for point in seq:
        if point[0] <= cutoff:
            best = point
        else:
            break
    return best


def build_draw(store: Storage, product: str, draw_number: int,
               reg_close_time: str,
               now: Optional[dt.datetime] = None) -> dict:
    """Frys alla passerade, ännu ej byggda horisonter för en omgång."""
    now = now or dt.datetime.now(dt.timezone.utc)
    close = _parse(reg_close_time)
    report = {"built": 0, "skipped": 0}
    if close is None:
        return report
    computed_at = _iso(now)
    for horizon, minutes in HORIZONS.items():
        cutoff_dt = close - dt.timedelta(minutes=minutes)
        if cutoff_dt > now:
            report["skipped"] += 1
            continue
        exists = store.conn.execute(
            "SELECT 1 FROM pool_pit_draw_features WHERE product=? AND "
            "draw_number=? AND horizon=? AND feature_version=?",
            (product, draw_number, horizon, FEATURE_VERSION)).fetchone()
        if exists:
            report["skipped"] += 1
            continue
        asof = _iso(cutoff_dt)
        svs = _series(store, "snapshots", product, draw_number, asof)
        sharp = _series(store, "sharp_snapshots", product, draw_number, asof)
        if not svs and not sharp:
            report["skipped"] += 1   # inte observerad vid horisonten — ingen rad
            continue
        events = sorted(set(svs) | set(sharp))
        n_cov_svs = n_cov_sharp = n_cov_streck = 0
        folk_entropies, market_entropies, max_folk, max_market = [], [], [], []
        match_rows = []
        for event in events:
            ssvs, ssharp = svs.get(event, {}), sharp.get(event, {})
            row: dict = {"event": event, "svs_lag": None, "sharp_lag": None,
                         "reversal": None}
            p_svs = _probs_at_index(ssvs, lambda q: q[-1])
            p_svs_first = _probs_at_index(ssvs, lambda q: q[0])
            p_sharp = _probs_at_index(ssharp, lambda q: q[-1])
            p_sharp_first = _probs_at_index(ssharp, lambda q: q[0])
            streck = {s: (ssvs.get(s) or [(None, None, None)])[-1][2]
                      for s in SIGNS}
            has_streck = all(streck[s] is not None for s in SIGNS)
            if p_svs:
                n_cov_svs += 1
                ts = max((ssvs[s][-1][0] for s in SIGNS))
                row["svs_lag"] = round(
                    (cutoff_dt - _parse(ts)).total_seconds() / 60, 1)
            if p_sharp:
                n_cov_sharp += 1
                ts = max((ssharp[s][-1][0] for s in SIGNS))
                row["sharp_lag"] = round(
                    (cutoff_dt - _parse(ts)).total_seconds() / 60, 1)
            if has_streck:
                n_cov_streck += 1
            for s in SIGNS:
                row[f"p_svs_{_COL[s]}"] = p_svs and round(p_svs[s], 4)
                row[f"p_sharp_{_COL[s]}"] = p_sharp and round(p_sharp[s], 4)
                row[f"streck_{_COL[s]}"] = streck[s]
                row[f"move_svs_pp_{_COL[s]}"] = (
                    p_svs and p_svs_first and
                    round((p_svs[s] - p_svs_first[s]) * 100, 2))
                row[f"move_sharp_pp_{_COL[s]}"] = (
                    p_sharp and p_sharp_first and
                    round((p_sharp[s] - p_sharp_first[s]) * 100, 2))
            market = p_sharp or p_svs
            for s in SIGNS:
                row[f"gap_{_COL[s]}"] = (
                    round(market[s] - streck[s] / 100.0, 4)
                    if market and streck[s] is not None else None)
            # sen reversal: folket och sharpen åt OLIKA håll sista 3 h — på
            # marknadens huvudtecken (störst p). Kräver punkter i fönstret.
            if market and has_streck and p_sharp:
                fav = max(SIGNS, key=lambda s: market[s])
                w_start = _iso(cutoff_dt - dt.timedelta(minutes=REVERSAL_WINDOW_MIN))
                old_sharp = _probs_at_index(
                    ssharp, lambda q: _at_or_before(q, w_start) or q[0])
                old_streck_pt = _at_or_before(ssvs.get(fav) or [], w_start)
                if old_sharp and old_streck_pt and old_streck_pt[2] is not None:
                    d_streck = streck[fav] - old_streck_pt[2]
                    d_sharp = (p_sharp[fav] - old_sharp[fav]) * 100
                    if (abs(d_streck) >= REVERSAL_STRECK_PP and
                            abs(d_sharp) >= REVERSAL_SHARP_PP and
                            (d_streck > 0) != (d_sharp > 0)):
                        row["reversal"] = fav
            if has_streck:
                tot = sum(streck[s] for s in SIGNS) or 1
                dist = [max(streck[s] / tot, 1e-9) for s in SIGNS]
                folk_entropies.append(-sum(p * math.log(p) for p in dist))
                max_folk.append(max(dist))
            if market:
                market_entropies.append(
                    -sum(max(market[s], 1e-9) * math.log(max(market[s], 1e-9))
                         for s in SIGNS))
                max_market.append(max(market[s] for s in SIGNS))
            match_rows.append(row)

        pds = store.conn.execute(
            "SELECT net_sale, jackpot FROM pool_draw_snapshot "
            "WHERE product=? AND draw_number=? AND fetched_at<=? "
            "ORDER BY fetched_at DESC LIMIT 1",
            (product, draw_number, asof)).fetchone()
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
        with store.bulk():
            store.conn.execute(
                "INSERT INTO pool_pit_draw_features (product, draw_number, "
                "horizon, feature_version, cohort, asof, computed_at, n_events, "
                "n_covered_svs, n_covered_sharp, n_covered_streck, entropy_folk, "
                "entropy_market, favorite_pressure, difficulty, turnover_asof, "
                "jackpot_asof) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw_number, horizon, FEATURE_VERSION, COHORT, asof,
                 computed_at, len(events), n_cov_svs, n_cov_sharp, n_cov_streck,
                 mean(folk_entropies), mean(market_entropies), mean(max_folk),
                 mean([1 - v for v in max_market]) if max_market else None,
                 pds and pds[0], pds and pds[1]))
            for row in match_rows:
                store.conn.execute(
                    "INSERT INTO pool_pit_match_features (product, draw_number, "
                    "horizon, event_number, feature_version, asof, svs_lag_min, "
                    "sharp_lag_min, p_svs_1, p_svs_x, p_svs_2, p_sharp_1, "
                    "p_sharp_x, p_sharp_2, streck_1, streck_x, streck_2, "
                    "move_svs_pp_1, move_svs_pp_x, move_svs_pp_2, "
                    "move_sharp_pp_1, move_sharp_pp_x, move_sharp_pp_2, "
                    "gap_1, gap_x, gap_2, reversal_sign) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (product, draw_number, horizon, row["event"],
                     FEATURE_VERSION, asof, row["svs_lag"], row["sharp_lag"],
                     row["p_svs_1"], row["p_svs_x"], row["p_svs_2"],
                     row["p_sharp_1"], row["p_sharp_x"], row["p_sharp_2"],
                     row["streck_1"], row["streck_x"], row["streck_2"],
                     row["move_svs_pp_1"], row["move_svs_pp_x"],
                     row["move_svs_pp_2"], row["move_sharp_pp_1"],
                     row["move_sharp_pp_x"], row["move_sharp_pp_2"],
                     row["gap_1"], row["gap_x"], row["gap_2"], row["reversal"]))
        report["built"] += 1
    return report


def build_recent(store: Storage, product: Optional[str] = None,
                 days_back: float = 7.0,
                 now: Optional[dt.datetime] = None) -> dict:
    """Varv-vänlig inkrementell byggare: omgångar med spelstopp i närtid.
    (Historisk helsvep: scripts/bygg_pit_dataset.py.)"""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = _iso(now - dt.timedelta(days=days_back))
    until = _iso(now + dt.timedelta(days=2))
    q = ("SELECT product, draw_number, reg_close_time FROM draws "
         "WHERE reg_close_time>=? AND reg_close_time<=?")
    args: list = [since, until]
    if product:
        q += " AND product=?"
        args.append(product)
    total = {"built": 0, "skipped": 0}
    for prod, draw_number, close in store.conn.execute(q, args).fetchall():
        rep = build_draw(store, prod, int(draw_number), close, now=now)
        total["built"] += rep["built"]
        total["skipped"] += rep["skipped"]
    return total
