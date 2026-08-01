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
    ~/kalltest-venv/bin/pip install httpx curl_cffi brotli
    # kopiera upp denna fil, sedan ett engångsprov:
    ~/kalltest-venv/bin/python kalltest_ip.py
    # schemalägg var 20:e minut (crontab -e):
    #   */20 * * * * ~/kalltest-venv/bin/python ~/kalltest_ip.py --tyst
    # efter några dygn:
    ~/kalltest-venv/bin/python kalltest_ip.py --rapport

Loggen (kalltest-logg.jsonl, bredvid skriptet) är append-only med tidsstämpel
per KÄLLA (satt efter varje anrop — observationstidsregeln). --rapport
sammanfattar per källa: andel OK, per dygn, senaste fel.

Bedömningsgrund: >95 % transport-OK per källa, minst 72 mätpunkter och
minst 72 verkliga timmar mellan första och sista provet ⇒ IP:n duger. Enstaka
timeouts är normalt brus; 403/skräp-kroppar i kluster är IP-blockning.
En KRITISK källa som faller diskvalificerar IP:n oavsett de andra —
`--rapport` skriver ut vad varje fallerande källa faktiskt kostar.

Flashscores statistik-*täckning* redovisas separat från transporten. Att en
giltig dagsfeed saknar xG/skott för en viss match betyder inte att IP:n är
blockerad, men det får inte längre döljas bakom ett allmänt "OK".
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
MIN_SAMPLES_PER_SOURCE = 72
MIN_SPAN_HOURS = 72.0
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


def check_flashscore() -> tuple[bool, str, bool | None]:
    """Dagsfeed + statistikfeed; transport och täckning är separata svar."""
    headers = {"User-Agent": UA_CHROME, "Accept": "*/*",
               "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
               "Referer": "https://www.flashscore.se/",
               "x-fsign": "SW9D1eZo"}
    base = "https://local-global.flashscore.ninja/2/x/feed"
    r = httpx.get(f"{base}/f_1_0_3_se_1", headers=headers, timeout=TIMEOUT)
    if r.status_code != 200:
        return False, f"dagsfeed status {r.status_code}", None
    text = r.text
    # TRANSPORTREGELN: brotli-kodat svar utan avkodning ser ut som skräp
    if "÷" not in text:
        encoding = r.headers.get("content-encoding", "-")
        return (False,
                f"otolkbar dagsfeed (content-encoding: {encoding})", None)
    live = [chunk for chunk in text.split("~")
            if "AA÷" in chunk and "AB÷2" in chunk]
    if not live:
        return True, "dagsfeed ok, inga livematcher; täckning ej mätbar", None

    # Ett enskilt lågnivåmöte kan legitimt sakna statistik. Prova upp till
    # tre matcher så att rapporten beskriver faktisk täckning utan att blanda
    # ihop den med IP-/transporthälsan.
    tested = 0
    covered = 0
    for chunk in live[:3]:
        match_id = chunk.split("AA÷", 1)[1].split("¬", 1)[0]
        s = httpx.get(f"{base}/df_st_1_{match_id}", headers=headers,
                      timeout=TIMEOUT)
        if s.status_code != 200:
            return (False, f"statistikfeed status {s.status_code} "
                    f"för {match_id}", None)
        # En läsbar Flashscore-feed innehåller fältavgränsaren ÷. SG är
        # själva statistikgruppen och redovisas som täckning nedan.
        if "÷" not in s.text:
            return False, f"otolkbar statistikfeed för {match_id}", None
        tested += 1
        covered += "SG÷" in s.text
    coverage_ok = covered > 0
    return (True, f"{len(live)} live; transport ok; "
            f"statistiktäckning {covered}/{tested}", coverage_ok)


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


# (namn, kontroll, kritisk?, vad den matar — visas när den fallerar)
CHECKS = (
    ("svenskaspel", check_svenskaspel, True,
     "poolspelen: omgångar, streck, omsättning, resultat"),
    ("pinnacle", check_pinnacle, True,
     "sharp-ankaret: hela värdemotorn, CLV-facitet och steam"),
    ("kambi", check_kambi, True,
     "SvS Oddset-priser: det vi faktiskt kan spela"),
    ("sofascore", check_sofascore, True,
     "MODELLENS datarygg: historisk xG, frånvaro, cupresultat och "
     "WP9c-schema (refresh_all) — INTE bara live-radarn"),
    ("flashscore", check_flashscore, True,
     "live-radarns primära chansdata (xG/skott) sedan 2026-08-01"),
    ("fotmob", check_fotmob, False,
     "live-radarns andra öga; radarn tappar täckning men modellen består"),
    ("altenar", check_altenar, False,
     "sidobok (Ninja) för 1X2/Ö/U/hörnor — mjuk bok, inget ankare"),
)


def run_once(quiet: bool) -> int:
    failures = 0
    with LOG.open("a", encoding="utf-8") as log:
        for name, check, _critical, _feeds in CHECKS:
            started = dt.datetime.now(dt.timezone.utc)
            try:
                result = check()
                if len(result) == 3:
                    transport_ok, note, coverage_ok = result
                else:
                    transport_ok, note = result
                    coverage_ok = None
            except Exception as exc:  # noqa: BLE001 — nätfel är ett mätvärde
                transport_ok = False
                coverage_ok = None
                note = f"{type(exc).__name__}: {str(exc)[:80]}"
            ms = int((dt.datetime.now(dt.timezone.utc)
                      - started).total_seconds() * 1000)
            row = {"at": _now(), "source": name,
                   # Behåll `ok` för bakåtkompatibla loggläsare, men ge
                   # det nu den entydiga betydelsen transport/innehållstolkning.
                   "ok": transport_ok, "transport_ok": transport_ok,
                   "coverage_ok": coverage_ok, "ms": ms, "note": note}
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            failures += not transport_ok
            if not quiet:
                mark = "✅" if transport_ok else "❌"
                print(f"{mark} {name:12s} {ms:5d} ms  {note}")
    if not quiet:
        print(f"\nlogg: {LOG}")
    return 1 if failures else 0


def report() -> int:
    if not LOG.exists():
        print("ingen logg ännu — kör utan flaggor först")
        return 1
    rows = []
    malformed_json = 0
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("loggrad är inte ett objekt")
            rows.append(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            # En avbruten skrivning eller manuell skada ska underkänna
            # underlaget synligt, aldrig krascha hela rapportkommandot.
            malformed_json += 1
    if not rows:
        print("loggen är tom eller saknar giltiga JSON-rader")
        return 1
    parsed: list[tuple[dict, dt.datetime]] = []
    malformed = malformed_json
    for row in rows:
        try:
            when = dt.datetime.fromisoformat(str(row["at"]).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=dt.timezone.utc)
            parsed.append((row, when.astimezone(dt.timezone.utc)))
        except (KeyError, TypeError, ValueError):
            malformed += 1
    if not parsed:
        print("loggen saknar giltiga tidsstämplar")
        return 1
    rows = [row for row, _when in parsed]
    days = sorted({row["at"][:10] for row in rows})
    print(f"Käll-rapport · {len(rows)} mätpunkter · "
          f"{days[0]} – {days[-1]} ({len(days)} dygn)\n")
    verdict_ok = malformed == 0
    incomplete: list[str] = []
    missing_sources: list[str] = []
    if malformed:
        print(f"❌ {malformed} loggrader är trasiga eller har ogiltig "
              "tidsstämpel\n")
    broken_critical: list[tuple[str, str]] = []
    for name, _check, critical, feeds in CHECKS:
        mine = [row for row in rows if row["source"] == name]
        if not mine:
            verdict_ok = False
            missing_sources.append(name)
            print(f"❌ {name:12s}"
                  f"{' (kritisk)' if critical else '          '}"
                  " saknas helt i loggen")
            print(f"   kostar: {feeds}")
            continue
        mine_times = [when for row, when in parsed if row.get("source") == name]
        span_h = ((max(mine_times) - min(mine_times)).total_seconds() / 3600
                  if len(mine_times) > 1 else 0.0)
        sample_ready = len(mine) >= MIN_SAMPLES_PER_SOURCE
        span_ready = span_h >= MIN_SPAN_HOURS
        ok_share = sum(bool(row.get("transport_ok", row.get("ok")))
                       for row in mine) / len(mine)
        last_fail = next((row for row in reversed(mine)
                          if not row.get("transport_ok", row.get("ok"))), None)
        per_day = " ".join(
            f"{day[5:]}:{sum(bool(r.get('transport_ok', r.get('ok'))) for r in mine if r['at'][:10] == day)}"
            f"/{sum(1 for r in mine if r['at'][:10] == day)}"
            for day in days)
        transport_healthy = ok_share > 0.95
        ready = sample_ready and span_ready
        healthy = transport_healthy and ready
        verdict_ok &= healthy
        if not ready:
            incomplete.append(name)
        # Ett tidigt fel är ett mätvärde, inte ett domslut. Kritisk
        # diskvalificering får ske först när samma 72-prov/72h-gate som
        # friskförklaring är uppfylld.
        if not transport_healthy and critical and ready:
            broken_critical.append((name, feeds))
        print(f"{'✅' if healthy else '❌'} {name:12s}"
              f"{' (kritisk)' if critical else '          '}"
              f" {100 * ok_share:5.1f} % transport-OK av {len(mine)}"
              + (f" · senaste fel {last_fail['at']}: {last_fail['note']}"
                 if last_fail else " · inga fel"))
        print(f"   mätperiod: {span_h:.1f} h"
              f" ({'✓' if span_ready else '✗'} minst {MIN_SPAN_HOURS:.0f} h)"
              f" · {'✓' if sample_ready else '✗'} minst "
              f"{MIN_SAMPLES_PER_SOURCE} prov")
        print(f"   per dygn: {per_day}")
        coverage = [row.get("coverage_ok") for row in mine
                    if row.get("coverage_ok") is not None]
        if coverage:
            print("   separat statistiktäckning: "
                  f"{sum(bool(value) for value in coverage)}/{len(coverage)} "
                  "mätbara prov hade chansdata")
        if not healthy:
            print(f"   kostar: {feeds}")
    print()
    if verdict_ok:
        print("Bedömning: IP:n ser ren ut — men kräv ≥3 dygn innan beslut.")
    elif broken_critical:
        print("Bedömning: DISKVALIFICERAD — kritisk källa blockerad:")
        for name, feeds in broken_critical:
            print(f"  • {name}: {feeds}")
    elif missing_sources or incomplete or malformed:
        reasons = []
        if missing_sources:
            reasons.append("saknade källor: " + ", ".join(missing_sources))
        if incomplete:
            reasons.append("för kort/gles serie: " + ", ".join(incomplete))
        if malformed:
            reasons.append(f"ogiltiga tidsstämplar: {malformed}")
        print("Bedömning: UNDERLAG OTILLRÄCKLIGT — " + "; ".join(reasons))
    else:
        print("Bedömning: bara icke-kritiska källor faller — utred "
              "felnoterna, men IP:n kan vara användbar.")
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
