# Överlämning 2026-11-06 — Pinnacle spärrad, SBOBET och Smarkets som referenskällor

## Läget

- **Pinnacle** svarar 403 ("you have been blocked", Cloudflare) på varje anrop sedan
  2026-11-05 09:30Z; sista lyckade hämtning 09:00Z. Även www.pinnacle.com svarar 403 till
  serverns IP. Saman bedömer att Pinnacle stängt Sverige. Att gå runt spärren (VPN, proxy,
  annan IP) är stängt enligt källgränsen. Koden står kvar och källprovet frågar fortfarande,
  nu som stödkälla, så att vi ser om den kommer tillbaka.
- **Betfair** lämnade Sverige 2025-07-16 ("Important Notice: Market Exit - Sweden") och
  spärrar svenska besökare. Stängd av samma skäl. Ingen kod skriven.
- **Saman 2026-11-06:** "låt oss köra sbo, smarket och betfair som tre extra källor".
  Levererat: SBOBET ny källa, Smarkets synlig igen, Betfair stängd (ovan).

## SBOBET (`backend/app/sbobet.py`)

- Publika datumsidor `https://www.sbobet.com/euro/football/<ÅÅÅÅ-MM-DD>` bär alla dagens
  matcher i sidans eget `onUpdate('od',[...])`-block. Ingen inloggning, cookie eller
  utmaning: öppet enligt källgränsen. robots.txt tillåter `/euro/` med `Crawl-delay: 5`;
  `/en/data/` och `/en/rdata/` är förbjudna och används aldrig.
- Sex dagar publiceras (dag 7 svarar 302). Insamlaren läser dag 0–5 på djupvarvet
  (:00/:30), fem sekunder mellan anropen, och slutar vid första opublicerade dagen.
- Sparar 1X2 och handikappets huvudlina (mest balanserade priset) i `oddset_odds`, källa
  `sbobet`, med varje sidas egen observationstid (svaren är `no-cache` utan Age).
  Pågående matcher finns inte med; en match som hunnit starta sparas aldrig. Frånvaro
  markeras bara för matcher inom en publicerad dag.
- Avspark i GMT+8 (alla 45 parade matcher exakt 8 h före UTC). Handikappets lina är vad
  hemmalaget ger; lagras som Pinnacle, alltså hemmalagets handikapp (= −SBOBET:s lina).
- `LEAGUE_IDS`: fjorton ligor belagda genom att para SBOBET:s matcher med våra på båda
  lagnamnen och exakt avspark (sidorna 6–11/11). Cuperna, Besta deild, Bolivia,
  träningsmatcher och landslag saknar belagt id (cupmatcherna 5/11 hade redan börjat).
- Mätt 8/11: handikapp median 4,7 % marginal (min 3,1 %), 1X2 median 15 %. Avviggad 1X2
  skilde sig från Smarkets med median 1,1 pp (45 matcher), samma nivå som Pinnacle mot
  Smarkets i juli. 1X2 är alltså inte skarpt; handikappet är bokens riktiga marknad.
- Roll: referenskälla. `sbobet` ligger i `oddset_value.ANCHOR_SOURCES` (värderas aldrig som
  bok) och skapar aldrig matchidentiteter.

## Smarkets

Redan insamlad (1X2, ~190 matcher). `UI_HIDDEN_SOURCES` är nu tom: Smarkets och SBOBET
visas som referensrader (`Sm`, `SBO`) under Pinnacles plats i Oddset-vyns matchrad, och
SBOBET:s handikapp i AH-cellen. Spärren i `ANCHOR_SOURCES` står kvar för båda.

## Källprovet

`scripts/kalltest_ip.py`: Smarkets och SBOBET tillagda som stödkällor; Pinnacle är
stödkälla i stället för kritisk.

## Provkörning före driftsättning

Mot en onlinekopia av databasen med veckans riktiga sidor länkade insamlaren 127 av 131
kommande matcher i de fjorton ligorna (Superettan 7/8, MLS 14/15, Championship 10/12,
övriga alla), fem rader per match (1X2 + handikappets två sidor).

## Första djupvarvet (2026-11-06T00:30Z)

Alla fjorton ligor fick en lyckad källhälsorad. 127 matcher fick SBOBET-priser: 381 rader
1X2 och 254 rader handikapp, med sidornas observationstider 00:30:09–00:30:19Z (fem
sekunder mellan sidorna). Oddset-API:t visade SBOBET i 37 och Smarkets i 39 av de 40
första matcherna. Exempel: Hammarby–Elfsborg SBOBET 1,326/4,34/6,28 och handikapp
hemma −1,25 (1,86/1,98), Smarkets 1,43/5,39/8,38.

## Driftsättning

Commit `aebe41d`, ff-merge till main 2026-11-06T00:17:05Z, frontenden byggd, backend och
frontend omstartade, push genom kroken (allt grönt).

## Kvar — kräver Samans beslut

- **Ankaret.** Värdemotorn, CLV, steam, notiser, poolens sharp-underlag (bygge, PH3,
  X-skyddets total) och liveblindtestets Pinnacle-del bygger på Pinnacle och står still.
  Att låta Smarkets (1X2, låg marginal) och/eller SBOBET (handikapp) ta Pinnacles plats är
  en ny signalversion, och för poolen en ny datagenererande process med datumnot. Det är
  inte gjort.
- Cupernas SBOBET-id beläggs när nästa cupomgång syns på datumsidorna före avspark.
