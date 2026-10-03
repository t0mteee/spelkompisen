"""Slå ihop kommande Oddset-matcher som fick en rad per källa (2026-10-03).

Bakgrund (docs/overlamningar/overlamning-2026-10-03-oddset-identitet.md):
collect() prövade bara rader inom listfönstret [nu−12 h, nu+10 d] som
länkkandidater. När Pinnacle och Svenska Spel listade samma match mer än tio
dygn före avspark, i olika varv, skapade de varsin rad (`pin:`/`svs:`).
Käll-id:n är write-once, så ett senare varv kunde aldrig slå ihop raderna.
Koden är rättad (`link_cands`). Det här engångsskriptet tar hand om par som
redan skapats.

Ett par slås ihop bara när ALLT gäller:

1. samma liga; en ren Pinnacle-rad (`pin:<pinnacle_id>`, kambi_id NULL) och en
   ren Svenska Spel-rad (`svs:<kambi_id>`, pinnacle_id NULL);
2. avsparkarna skiljer högst 15 min, och avsparken ligger mellan nu + 49 h och
   MAX_AVSPARK. Flashscore-frånvaron fryses 48 h före avspark och WP5/V2.2
   24 h före, så ingen sådan rad kan ha hunnit skrivas;
3. insamlingens egen förstalänk hade kopplat dem (`_team_pair_score` ≥ 0,75
   med minst 0,55 per sida; landslag på landskod);
4. minst ena laget är strikt lika (samma normaliserade ordmängd, eller en
   ordmängd som ryms i den andra), och truppmarkörerna (U21, dam, II …) är
   lika på båda sidor;
5. entydigt åt båda hållen: varje rad har exakt en sådan motpart;
6. Svenska Spel-raden har inga rader i andra tabeller än de flyttbara
   (`MOVABLE_TABLES`). Amber-modellflaggor i `oddset_value_log` lämnas kvar på
   sitt gamla id: de loggades med en modell utan Pinnacle-ankare, eftersom
   Pinnacle låg på den andra raden, och de stängs aldrig, precis som utan
   skriptet;
7. paret står i den granskade planen (`--plan`). Körningen gör aldrig mer än
   det som granskades, bara mindre om läget hunnit ändras.

Pinnacle-raden är kanon (sharp_alt och historiken finns där). Kambi-id,
Kambis visningsnamn och radens oddshistorik flyttas dit, och Svenska
Spel-raden tas bort. Inga priser skapas, ändras eller bakfylls; antalet
oddsrader är oförändrat.

Utan `--kor` är skriptet en ren läsning (`mode=ro`):

    .venv/bin/python -B scripts/migrera_oddset_identitetspar.py \\
        --spara-plan ../docs/oddset-identitetspar-plan-2026-10-03.json

Körning, efter Samans godkännande och med snapshot-jobbet stoppat:

    .venv/bin/python -B scripts/migrera_oddset_identitetspar.py \\
        --kor --plan ../docs/oddset-identitetspar-plan-2026-10-03.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.landslag import kod  # noqa: E402
from app.oddset import (  # noqa: E402
    LEAGUES, MIN_MATCH_SCORE, _team_pair_score, norm_team)


DB = ROOT / "data" / "stryktips.db"
BACKUP_DIR = ROOT / "data" / "backups"
MAX_START_DELTA_MIN = 15
MIN_LEAD_H = 49
# Paren skapades före rättelsen 2026-10-03. Källorna listade då som längst
# till 2026-10-19. Ett par med senare avspark har en annan orsak och ska
# utredas, inte slås ihop av det här skriptet.
MAX_AVSPARK = "2026-10-31T23:59:59Z"
MOVABLE_TABLES = (
    "oddset_odds", "oddset_sharp_alt", "oddset_matchbook_liquidity")
LEFT_IN_PLACE = frozenset({"oddset_value_log"})
# Fryst kopia av live_radar._SQUAD_MARKERS (2026-10-03) plus Svenska Spels
# damformer. U-åldrar känns igen som "u" + siffror.
SQUAD_MARKERS = frozenset({
    "b", "ii", "reserve", "reserves", "academy", "youth", "women", "damer",
    "dam", "ladies", "wfc", "lfc"})
LANDSLAG_LEAGUES = frozenset(
    league["key"] for league in LEAGUES if league.get("landslag"))


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _tokens(name: str) -> frozenset[str]:
    return frozenset(norm_team(name or "").split())


def _squad(name: str) -> frozenset[str]:
    return frozenset(
        token for token in _tokens(name)
        if token in SQUAD_MARKERS
        or (token.startswith("u") and token[1:].isdigit()))


def _strictly_equal(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta)


def link_rule(pin: dict, svs: dict) -> str | None:
    """Varför raderna är samma match, eller None. Tid och liga prövas av
    anroparen."""
    if pin["league"] in LANDSLAG_LEAGUES:
        codes = (kod(pin["home"] or ""), kod(pin["away"] or ""))
        same = all(codes) and codes == (
            kod(svs["home"] or ""), kod(svs["away"] or ""))
        return "landskod" if same else None
    if _team_pair_score(pin["home"], pin["away"],
                        svs["home"], svs["away"]) < MIN_MATCH_SCORE:
        return None
    if (_squad(pin["home"]) != _squad(svs["home"])
            or _squad(pin["away"]) != _squad(svs["away"])):
        return None
    home = _strictly_equal(pin["home"], svs["home"])
    away = _strictly_equal(pin["away"], svs["away"])
    if home and away:
        exact = (_tokens(pin["home"]) == _tokens(svs["home"])
                 and _tokens(pin["away"]) == _tokens(svs["away"]))
        return "exakt" if exact else "ordmängd"
    return "ena laget" if home or away else None


def _pure_rows(conn: sqlite3.Connection,
               since: str) -> tuple[list[dict], list[dict]]:
    """Kommande rader med exakt ett käll-id och självbärande id."""
    rows = [dict(row) for row in conn.execute(
        "SELECT * FROM oddset_matches WHERE start >= ? "
        "AND (pinnacle_id IS NULL) != (kambi_id IS NULL)", (since,))]
    pins = [row for row in rows if row["pinnacle_id"] is not None
            and row["id"] == f"pin:{row['pinnacle_id']}"]
    kambis = [row for row in rows if row["kambi_id"] is not None
              and row["id"] == f"svs:{row['kambi_id']}"]
    return pins, kambis


def _referencing_tables(conn: sqlite3.Connection) -> list[str]:
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return [
        table for table in tables
        if table != "oddset_matches" and any(
            column[1] == "match_id"
            for column in conn.execute(f"PRAGMA table_info({table})"))
    ]


def _counts(conn: sqlite3.Connection, table: str,
            match_ids: list[str]) -> Counter:
    """Rader per match_id, en fråga per tabell (alla tabeller har inte
    match_id först i ett index)."""
    out: Counter = Counter()
    for i in range(0, len(match_ids), 500):
        chunk = match_ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        out.update(dict(conn.execute(
            f"SELECT match_id, COUNT(*) FROM {table} "
            f"WHERE match_id IN ({marks}) GROUP BY match_id", chunk)))
    return out


def plan_pairs(conn: sqlite3.Connection, now: dt.datetime) -> dict:
    """Alla par som uppfyller regel 1–6, plus de som föll och varför."""
    lower, upper = _iso(now + dt.timedelta(hours=MIN_LEAD_H)), MAX_AVSPARK
    pins, kambis = _pure_rows(conn, _iso(now))
    candidates: list[tuple[dict, dict, str]] = []
    for svs in kambis:
        svs_at = _parse(svs["start"])
        if svs_at is None:
            continue
        for pin in pins:
            if pin["league"] != svs["league"]:
                continue
            pin_at = _parse(pin["start"])
            if pin_at is None or abs(
                    (pin_at - svs_at).total_seconds()) > MAX_START_DELTA_MIN * 60:
                continue
            rule = link_rule(pin, svs)
            if rule:
                candidates.append((pin, svs, rule))

    per_pin = Counter(pin["id"] for pin, _, _ in candidates)
    per_svs = Counter(svs["id"] for _, svs, _ in candidates)
    tables = _referencing_tables(conn)
    blocking = [t for t in tables
                if t not in MOVABLE_TABLES and t not in LEFT_IN_PLACE]
    svs_ids = [svs["id"] for _, svs, _ in candidates]
    counts = {table: _counts(conn, table, svs_ids) for table in tables}
    pairs, skipped = [], []
    for pin, svs, rule in sorted(candidates,
                                 key=lambda item: (item[0]["start"], item[0]["id"])):
        entry = {
            "pin": pin["id"], "svs": svs["id"], "league": pin["league"],
            "start": pin["start"], "rule": rule,
            "pin_names": f"{pin['home']}–{pin['away']}",
            "svs_names": f"{svs['home']}–{svs['away']}",
        }
        if per_pin[pin["id"]] > 1 or per_svs[svs["id"]] > 1:
            skipped.append({**entry, "reason": "tvetydig"})
            continue
        if not lower <= pin["start"] <= upper or not lower <= svs["start"] <= upper:
            skipped.append({**entry, "reason": "utanför tidsgränserna"})
            continue
        refs = {table: counts[table][svs["id"]] for table in blocking
                if counts[table][svs["id"]]}
        if refs:
            skipped.append({**entry, "reason": "referenser", "refs": refs})
            continue
        entry["moved"] = {table: counts[table][svs["id"]]
                          for table in MOVABLE_TABLES if table in counts}
        entry["left"] = {table: counts[table][svs["id"]]
                         for table in sorted(LEFT_IN_PLACE) if table in counts}
        entry["sources"] = dict(conn.execute(
            "SELECT source, COUNT(*) FROM oddset_odds WHERE match_id=? "
            "GROUP BY source ORDER BY source", (svs["id"],)).fetchall())
        entry["svs_row"] = {key: svs[key] for key in (
            "kambi_id", "home", "away", "start", "updated_at")}
        entry["pin_updated_at"] = pin["updated_at"]
        pairs.append(entry)
    return {"generated_at": _iso(now), "lower": lower, "upper": upper,
            "pairs": pairs, "skipped": skipped, "blocking_tables": blocking,
            "movable_tables": [t for t in MOVABLE_TABLES if t in tables]}


def _same_time_variants(conn: sqlite3.Connection, match_ids: list[str]) -> int:
    """Två olika priser från samma källa/marknad/tecken vid exakt samma
    observationstid — invarianten i Storage.oddset_identity_conflicts."""
    if not match_ids:
        return 0
    marks = ",".join("?" * len(match_ids))
    return conn.execute(
        f"SELECT COUNT(*) FROM (SELECT match_id, source, market, sign, "
        f"fetched_at FROM oddset_odds WHERE match_id IN ({marks}) "
        f"GROUP BY match_id, source, market, sign, fetched_at "
        f"HAVING COUNT(DISTINCT COALESCE(odds, -1) || '|' || "
        f"COALESCE(line, -999)) > 1)", match_ids).fetchone()[0]


def backup_database(source: Path | str, target: Path | str) -> None:
    """Konsistent onlinekopia med SQLite:s backup-API; skriver aldrig över."""
    target = Path(target)
    if target.exists():
        raise RuntimeError(f"backupen finns redan: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=10)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.execute("PRAGMA busy_timeout=10000")
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()


def migrate(db: Path | str, approved: list[dict],
            now: dt.datetime | None = None) -> dict:
    """Slå ihop de godkända paren som fortfarande uppfyller regel 1–6.

    Allt sker i EN skrivtransaktion; varje kontroll som fallerar rullar
    tillbaka hela körningen."""
    now = now or dt.datetime.now(dt.timezone.utc)
    approved_keys = {(pair["pin"], pair["svs"]) for pair in approved}
    conn = sqlite3.connect(db, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("BEGIN IMMEDIATE")
        plan = plan_pairs(conn, now)
        movable = plan["movable_tables"]
        todo = [pair for pair in plan["pairs"]
                if (pair["pin"], pair["svs"]) in approved_keys]
        not_now = sorted(approved_keys - {(p["pin"], p["svs"]) for p in todo})
        pin_ids = [pair["pin"] for pair in todo]
        svs_ids = [pair["svs"] for pair in todo]
        n_matches = conn.execute("SELECT COUNT(*) FROM oddset_matches").fetchone()[0]
        before = {table: sum(_counts(conn, table, pin_ids + svs_ids).values())
                  for table in movable}
        value_log_before = _counts(conn, "oddset_value_log", svs_ids)
        for pair in todo:
            for table in movable:
                conn.execute(
                    f"UPDATE {table} SET match_id=? WHERE match_id=?",
                    (pair["pin"], pair["svs"]))
            # Provider-id:t har ett globalt unikhetsindex: den gamla ägaren tas
            # bort före flytten. Transaktionen gör stegen atomiska.
            conn.execute("DELETE FROM oddset_matches WHERE id=?", (pair["svs"],))
            svs = pair["svs_row"]
            updated = max(filter(None, (svs["updated_at"], pair["pin_updated_at"])),
                          default=None)
            conn.execute(
                "UPDATE oddset_matches SET kambi_id=?, home=?, away=?, "
                "updated_at=COALESCE(?, updated_at) "
                "WHERE id=? AND kambi_id IS NULL",
                (svs["kambi_id"], svs["home"], svs["away"], updated, pair["pin"]))
            if conn.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError(f"{pair['pin']} ändrades under körningen")
        for table in movable:
            on_pin = sum(_counts(conn, table, pin_ids).values())
            on_svs = sum(_counts(conn, table, svs_ids).values())
            if on_pin != before[table] or on_svs:
                raise RuntimeError(
                    f"{table}: {before[table]} rader före, {on_pin} på "
                    f"Pinnacle-raderna och {on_svs} kvar efter flytten")
        if _counts(conn, "oddset_value_log", svs_ids) != value_log_before:
            raise RuntimeError("oddset_value_log ändrades")
        n_after = conn.execute("SELECT COUNT(*) FROM oddset_matches").fetchone()[0]
        if n_matches - n_after != len(todo):
            raise RuntimeError("oväntad förändring av antalet matcher")
        variants = _same_time_variants(conn, pin_ids)
        if variants:
            raise RuntimeError(
                f"{variants} samtidiga prisvarianter efter flytten")
        leftover = [pair for pair in plan_pairs(conn, now)["pairs"]
                    if (pair["pin"], pair["svs"]) in approved_keys]
        if leftover:
            raise RuntimeError(f"{len(leftover)} godkända par finns kvar")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    # Hela filen kontrolleras efter commit, utanför skrivlåset (busy_timeout
    # hos de andra skrivarna är 10 s). Fel här återställs från backupen.
    check = sqlite3.connect(db, timeout=10)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    return {
        "merged": len(todo), "approved": len(approved_keys),
        "not_merged_now": not_now,
        "pairs": [(pair["pin"], pair["svs"]) for pair in todo],
        "matches_before": n_matches, "matches_after": n_after,
        "moved_rows": before,
        "value_log_left": sum(value_log_before.values()),
        "integrity": integrity,
    }


def _print_plan(plan: dict) -> None:
    pairs, skipped = plan["pairs"], plan["skipped"]
    rules = Counter(pair["rule"] for pair in pairs)
    print(f"Plan {plan['generated_at']} · avspark {plan['lower']} – {plan['upper']}")
    print(f"slås ihop: {len(pairs)} ({', '.join(f'{k} {v}' for k, v in sorted(rules.items()))})"
          f" · hoppas över: {len(skipped)}"
          f" · oddsrader som flyttas: {sum(p['moved']['oddset_odds'] for p in pairs)}"
          f" · modellflaggor kvar på gammalt id: "
          f"{sum(p['left'].get('oddset_value_log', 0) for p in pairs)}")
    print(f"{'avspark':20s} {'liga':18s} {'Pinnacle-rad':16s} {'SvS-rad':16s} "
          f"{'regel':9s} namn (Pinnacle | Svenska Spel)")
    for pair in pairs:
        print(f"{pair['start']:20s} {pair['league'][:18]:18s} {pair['pin']:16s} "
              f"{pair['svs']:16s} {pair['rule']:9s} "
              f"{pair['pin_names']} | {pair['svs_names']}")
    for pair in skipped:
        print(f"HOPPAS ÖVER ({pair['reason']}{' ' + json.dumps(pair['refs']) if pair.get('refs') else ''}): "
              f"{pair['start']} {pair['league']} {pair['pin']} {pair['svs']} "
              f"{pair['pin_names']} | {pair['svs_names']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--spara-plan", help="skriv planen som JSON hit")
    parser.add_argument("--kor", action="store_true",
                        help="slå ihop paren i --plan (efter backup)")
    parser.add_argument("--plan", help="granskad plan från --spara-plan")
    args = parser.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)

    if not args.kor:
        conn = sqlite3.connect(
            f"{Path(args.db).resolve().as_uri()}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            plan = plan_pairs(conn, now)
        finally:
            conn.close()
        _print_plan(plan)
        if args.spara_plan:
            Path(args.spara_plan).write_text(
                json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
            print(f"plan sparad: {args.spara_plan}")
        return

    if not args.plan:
        parser.error("--kor kräver --plan (den granskade listan)")
    approved = json.loads(Path(args.plan).read_text())["pairs"]
    stamp = now.strftime("%Y-%m-%dT%H%M%SZ")
    backup = BACKUP_DIR / f"stryktips-{stamp}-fore-oddset-identitetspar.db"
    backup_database(args.db, backup)
    result = migrate(args.db, approved, now)
    print(f"backup: {backup}")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
