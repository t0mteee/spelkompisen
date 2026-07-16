"""Återupptagningsbar ClubElo-backfill från 2024 utan datum-för-datum-anrop.

Tre säsongsankare hittar tillgängliga svenska/norska klubbar. Därefter hämtas
varje klubbs fulla From/To-historik en gång. Lyckade klubbar markeras i meta;
nätfel lämnas omarkerade och försöks igen vid nästa körning.

Körning:
    cd backend && .venv/bin/python -B scripts/backfill_elohistorik.py
    cd backend && .venv/bin/python -B scripts/backfill_elohistorik.py --max-clubs 5
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import oddset_data  # noqa: E402
from app.storage import Storage  # noqa: E402


HISTORY_FROM = "2024-01-01"
ANCHORS = ("2024-07-01", "2025-07-01")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds") \
        .replace("+00:00", "Z")


def _club_identifiers(club_raw: str) -> list[str]:
    """ClubElo-sidan länkar flerordsnamn med kompakta URL-sluggar."""
    compact = "".join(ch for ch in club_raw if ch.isalnum())
    candidates = [compact]
    words = club_raw.replace("-", " ").split()
    if words and words[0].upper() == "IK" and len(words) > 1:
        candidates.append("".join(words[1:]))
    if len(words) > 1 and words[-1].casefold() in ("grenland", "oslo"):
        candidates.append(words[0])
    candidates.append(club_raw)
    return list(dict.fromkeys(quote(c, safe="") for c in candidates if c))


def _fetch_club_rows(club_raw: str, today: str) -> tuple[list[dict], str]:
    """Prova ClubElos egna slugmönster; godta bara ett entydigt klubbflöde."""
    seen_keys: set[str] = set()
    for identifier in _club_identifiers(club_raw):
        text = oddset_data.fetch_elo_csv(identifier)
        rows = [r for r in oddset_data.parse_elo_csv(text)
                if r["valid_to"] >= HISTORY_FROM and r["valid_from"] <= today]
        keys = {r["club_key"] for r in rows}
        seen_keys.update(keys)
        if rows and len(keys) == 1:
            return rows, identifier
    raise ValueError("ingen entydig ClubElo-slug; "
                     f"observerade {len(seen_keys)} SWE/NOR-identiteter")


def _discover(store: Storage, today: str) -> tuple[dict[str, str], list[str]]:
    clubs: dict[str, str] = {}
    errors = []
    for day in (*ANCHORS, today):
        cached = store.conn.execute(
            "SELECT captured_at FROM oddset_elo_capture WHERE requested_date=? "
            "AND source IN ('daily','backfill-anchor') "
            "ORDER BY julianday(captured_at) DESC, captured_at DESC LIMIT 1",
            (day,)).fetchone()
        if cached:
            rows = [dict(r) for r in store.conn.execute(
                "SELECT * FROM oddset_elo_rating WHERE captured_at=?",
                (cached["captured_at"],)).fetchall()]
            if rows:
                store.oddset_save_elo_history(rows, cached["captured_at"])
                clubs.update({r["club_key"]: r["club_raw"] for r in rows})
                print(f"ankare {day}: {len(rows)} klubbar (cache)", flush=True)
                continue
        try:
            text = oddset_data.fetch_elo_csv(day)
            rows = oddset_data.parse_elo_csv(text)
            if not rows:
                raise ValueError("tom SWE/NOR-ranking")
            at = _now_iso()
            store.oddset_save_elo_capture({
                "captured_at": at, "requested_date": day,
                "source": "daily" if day == today else "backfill-anchor",
                "payload_hash": hashlib.sha256(text.encode()).hexdigest(),
            }, rows)
            store.oddset_save_elo_history(rows, at)
            clubs.update({r["club_key"]: r["club_raw"] for r in rows})
            if day == today:
                current = {r["club_key"]: round(r["elo"]) for r in rows}
                store.meta_set("oddset_elo", json.dumps(current, ensure_ascii=False))
                store.meta_set("oddset_elo_at", at[:19] + "Z")
            print(f"ankare {day}: {len(rows)} klubbar", flush=True)
        except Exception as exc:  # noqa: BLE001 — övriga ankare kan ändå fungera
            errors.append(f"ankare {day}: {type(exc).__name__}: {exc}")
            print(f"⚠ {errors[-1]}", flush=True)
    # En tidigare lyckad dagscapture ger rånamn även om dagens ankare ligger nere.
    for row in store.conn.execute(
            "SELECT club_key, club_raw FROM oddset_elo_rating ORDER BY captured_at"):
        clubs[row["club_key"]] = row["club_raw"]
    return clubs, errors


def run(store: Storage, force: bool = False, max_clubs: int | None = None,
        pause_seconds: float = 0.5) -> dict:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    clubs, errors = _discover(store, today)
    selected = sorted(clubs.items())
    if max_clubs is not None:
        selected = selected[:max_clubs]
    done = skipped = changed = intervals = 0
    for i, (club_key, club_raw) in enumerate(selected, 1):
        state_key = f"oddset_elo_backfill:{club_key}"
        if not force and store.meta_get(state_key):
            skipped += 1
            continue
        try:
            parsed, provider_identifier = _fetch_club_rows(club_raw, today)
            source_keys = {r["club_key"] for r in parsed}
            rows = [r for r in parsed if r["club_key"] == club_key]
            alias_from = None
            # ClubElos datumranking och klubbendpoint använder ibland olika
            # egna namn (Bodoe Glimt→Bodo Glimt, IK Sirius→Sirius). Endast ett
            # entydigt en-klubb-svar får kanoniseras till ankarets identitet.
            if not rows and len(source_keys) == 1:
                alias_from = next(iter(source_keys))
                rows = [{**r, "club_key": club_key} for r in parsed]
            if not rows:
                raise ValueError("lyckat svar men inga PIT-intervall sedan 2024")
            fetched_at = _now_iso()
            changed += store.oddset_save_elo_history(rows, fetched_at)
            intervals += len(rows)
            store.meta_set(state_key, json.dumps({
                "at": fetched_at, "rows": len(rows),
                "from": min((r["valid_from"] for r in rows), default=None),
                "to": max((r["valid_to"] for r in rows), default=None),
                "provider_club_key": alias_from or club_key,
                "provider_identifier": provider_identifier,
            }))
            done += 1
            alias_note = f" (alias {alias_from})" if alias_from else ""
            print(f"[{i}/{len(selected)}] {club_raw}: {len(rows)} intervall{alias_note}",
                  flush=True)
        except Exception as exc:  # noqa: BLE001 — ska förbli retrybar
            errors.append(f"{club_raw}: {type(exc).__name__}: {exc}")
            print(f"⚠ [{i}/{len(selected)}] {errors[-1]}", flush=True)
        if pause_seconds and i < len(selected):
            time.sleep(pause_seconds)
    return {"discovered": len(clubs), "selected": len(selected), "done": done,
            "skipped": skipped, "intervals": intervals, "changed": changed,
            "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-clubs", type=int)
    parser.add_argument("--anchors-only", action="store_true")
    args = parser.parse_args()
    store = Storage()
    try:
        if args.anchors_only:
            today = dt.datetime.now(dt.timezone.utc).date().isoformat()
            clubs, errors = _discover(store, today)
            print(json.dumps({"discovered": len(clubs), "errors": errors},
                             ensure_ascii=False, indent=2))
            return
        result = run(store, force=args.force, max_clubs=args.max_clubs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
