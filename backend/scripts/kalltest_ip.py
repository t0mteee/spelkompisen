"""Käll-test för ny server-IP: svarar alla gratiskällor rent härifrån?

FRISTÅENDE skript (inga app-importer) — kopieras ensamt till en kandidat-VPS
(Netcup/Hetzner/Pi) och körs där. Det härmar EXAKT appens anropsmönster:
samma endpoints, samma headers, browser-TLS (curl_cffi impersonate) för
Sofascore. Transportregeln gäller: status 200 räknas bara som OK om kroppen
också går att TOLKA (JSON + förväntat fält) — CloudFront/Cloudflare kan svara
200 med skräp eller en interstitial.

VIKTIGT: en enda lyckad körning bevisar ingenting. Pinnacle Cloudflare-
blockar I PERIODER på IP-nivå (dokumenterat i CLAUDE.md), så kör på schema
i minst 3–5 dygn innan beslut. Kör också en baslinje från hemma-IP:n att
jämföra mot.

Användning på en naken Debian/Ubuntu-VPS:

    sudo apt install -y python3-venv
    python3 -m venv ~/kalltest-venv
    ~/kalltest-venv/bin/pip install httpx curl_cffi
    # kopiera upp denna fil, sedan ett engångsprov:
    ~/kalltest-venv/bin/python kalltest_ip.py
    # schemalägg var 20:e minut (crontab -e):
    #   */20 * * * * ~/kalltest-venv/bin/python ~/kalltest_ip.py --tyst
    # efter några dygn:
    ~/kalltest-venv/bin/python kalltest_ip.py --rapport

Loggen (kalltest-logg.jsonl, bredvid skriptet) är append-only med tidsstämpel
per KÄLLA (satt efter varje anrop — observationstidsregeln). --rapport
sammanfattar per källa: andel OK, per dygn, senaste fel.

Bedömningsgrund: >95 % OK per källa över ≥3 dygn OCH inga 403-perioder på
Pinnacle/Sofascore/FotMob ⇒ IP:n duger. Enstaka timeouts är normalt brus;
403/skräp-kroppar i kluster är IP-blockning och diskvalificerar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import httpx

try:
    from curl_cffi import requests as cffi
except ImportError:  # Sofascore-testet kräver paketet — säg det tydligt
    cffi = None

LOG = Path(__file__).resolve().parent / "kalltest-logg.jsonl"
TIMEOUT = 15.0
UA_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
             "Safari/537.36")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_json(response, expect_key: str) -> tuple[bool, str]:
    """200 + tolkbar JSON + förväntat fält — annars fel med diagnos."""
    if response.status_code != 200:
        return False, f"status {response.status_code}"
    try:
        data = response.json()
    except Exception:
        encoding = response.headers.get("content-encoding", "-")
        return False, f"otolkbar kropp (content-encoding: {encoding})"
    if isinstance(data, list):
        return True, f"lista, {len(data)} objekt"
    if expect_key not in data:
        return False, f"200 men fältet '{expect_key}' saknas (interstitial?)"
    value = data[expect_key]
    n = len(value) if isinstance(value, (list, dict)) else value
    return True, f"'{expect_key}' ok ({n})"


def check_svenskaspel() -> tuple[bool, str]:
    r = httpx.get("https://api.spela.svenskaspel.se/draw/1/stryktipset/draws",
                  headers={"User-Agent": "Mozilla/5.0",
                           "Accept": "application/json"}, timeout=TIMEOUT)
    return _check_json(r, "draws")


def check_pinnacle() -> tuple[bool, str]:
    r = httpx.get("https://guest.api.arcadia.pinnacle.com/0.1"
                  "/sports/29/matchups",
                  headers={"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
                           "User-Agent": "Mozilla/5.0",
                           "Accept": "application/json"}, timeout=TIMEOUT)
    return _check_json(r, "")


def check_kambi() -> tuple[bool, str]:
    r = httpx.get("https://eu-offering-api.kambicdn.com/offering/v2018"
                  "/svenskaspel/listView/football/sweden/allsvenskan.json",
                  params={"lang": "sv_SE", "market": "SE"},
                  headers={"User-Agent": "Mozilla/5.0",
                           "Accept": "application/json"}, timeout=TIMEOUT)
    return _check_json(r, "events")


def check_sofascore() -> tuple[bool, str]:
    if cffi is None:
        return False, "curl_cffi saknas i venv:et (pip install curl_cffi)"
    r = cffi.get("https://api.sofascore.com/api/v1"
                 "/sport/football/events/live",
                 impersonate="chrome", timeout=TIMEOUT)
    return _check_json(r, "events")


def check_fotmob() -> tuple[bool, str]:
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    r = httpx.get("https://www.fotmob.com/api/data/matches",
                  params={"date": day},
                  headers={"User-Agent": UA_CHROME,
                           "Accept": "application/json, text/plain, */*",
                           "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"},
                  timeout=TIMEOUT)
    return _check_json(r, "leagues")


def check_altenar() -> tuple[bool, str]:
    r = httpx.get("https://sb2frontend-altenar2.biahosted.com/api/Widget"
                  "/GetEvents",
                  params={"culture": "sv-SE", "timezoneOffset": "-120",
                          "integration": "betinia", "deviceType": "1",
                          "numFormat": "en-GB", "countryCode": "SE",
                          "champIds": 3537, "sportId": 66,
                          "eventCount": "50"},
                  headers={"User-Agent": "Mozilla/5.0",
                           "Accept": "application/json"}, timeout=TIMEOUT)
    return _check_json(r, "events")


CHECKS = (
    ("svenskaspel", check_svenskaspel),
    ("pinnacle", check_pinnacle),
    ("kambi", check_kambi),
    ("sofascore", check_sofascore),
    ("fotmob", check_fotmob),
    ("altenar", check_altenar),
)


def run_once(quiet: bool) -> int:
    failures = 0
    with LOG.open("a", encoding="utf-8") as log:
        for name, check in CHECKS:
            started = dt.datetime.now(dt.timezone.utc)
            try:
                ok, note = check()
            except Exception as exc:  # noqa: BLE001 — nätfel är ett mätvärde
                ok, note = False, f"{type(exc).__name__}: {str(exc)[:80]}"
            ms = int((dt.datetime.now(dt.timezone.utc)
                      - started).total_seconds() * 1000)
            row = {"at": _now(), "source": name, "ok": ok,
                   "ms": ms, "note": note}
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            failures += not ok
            if not quiet:
                mark = "✅" if ok else "❌"
                print(f"{mark} {name:12s} {ms:5d} ms  {note}")
    if not quiet:
        print(f"\nlogg: {LOG}")
    return 1 if failures else 0


def report() -> int:
    if not LOG.exists():
        print("ingen logg ännu — kör utan flaggor först")
        return 1
    rows = [json.loads(line) for line in
            LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        print("loggen är tom")
        return 1
    days = sorted({row["at"][:10] for row in rows})
    print(f"Käll-rapport · {len(rows)} mätpunkter · "
          f"{days[0]} – {days[-1]} ({len(days)} dygn)\n")
    verdict_ok = True
    for name, _ in CHECKS:
        mine = [row for row in rows if row["source"] == name]
        if not mine:
            continue
        ok_share = sum(row["ok"] for row in mine) / len(mine)
        last_fail = next((row for row in reversed(mine)
                          if not row["ok"]), None)
        per_day = " ".join(
            f"{day[5:]}:{sum(r['ok'] for r in mine if r['at'][:10] == day)}"
            f"/{sum(1 for r in mine if r['at'][:10] == day)}"
            for day in days)
        flag = "✅" if ok_share > 0.95 else "❌"
        verdict_ok &= ok_share > 0.95
        print(f"{flag} {name:12s} {100 * ok_share:5.1f} % OK av {len(mine)}"
              + (f" · senaste fel {last_fail['at']}: {last_fail['note']}"
                 if last_fail else " · inga fel"))
        print(f"   per dygn: {per_day}")
    print("\nBedömning:", "IP:n ser ren ut — men kräv ≥3 dygn innan beslut."
          if verdict_ok else
          "MINST EN KÄLLA UNDER 95 % — utred felnoterna innan migrering.")
    return 0 if verdict_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tyst", action="store_true",
                        help="ingen utskrift (för cron), bara logg")
    parser.add_argument("--rapport", action="store_true",
                        help="sammanfatta loggen i stället för att mäta")
    args = parser.parse_args()
    sys.exit(report() if args.rapport else run_once(args.tyst))


if __name__ == "__main__":
    main()
