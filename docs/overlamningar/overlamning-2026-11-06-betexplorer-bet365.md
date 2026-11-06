# Överlämning 2026-11-06 — bet365 via Betexplorer som referensbok

Beslut `2026-11-06-betexplorer-bet365`, val 0: "Ja: samla bet365 från Betexplorer som
referensbok (1X2, Ö/U, AH med tider), visas i Oddset-vyn, aldrig ankare". Genomfört
automatiskt (genomförandet, beslut koordinatorn-2026-10-14-genomfor-beslut-automatiskt).

## Källan

- `GET /football/<land>/<liga>/fixtures/` — ligans kommande matcher med Betexplorers
  åttateckens event-id sist i länken. `max-age=600`.
- `GET /match-odds/<id>/0/<1x2|ou|ah>/odds/?lang=en` — sidans egen JSON
  (`{"odds": "<html>"}`), anropad med `X-Requested-With` och `Referer` som sidan själv gör.
  1X2 ~145 kB, Ö/U och AH ~1,2 MB okomprimerat. `max-age=3600, max-age=1`, Age 0.
- robots.txt spärrar `/ad/`, `/redirect/`, `/bookmaker/` och vissa `?`-parametrar —
  inget av det används. Ingen nyckel, cookie eller utmaning (källgränsen: öppen).
- `/archive-odds/` (prishistorik per bok) används ALDRIG: priser bakfylls inte.

## Format (uppmätt)

- Bokens rad: `data-bookie="bet365"`. Priscellen bär `data-odd` och `data-created`
  (när BOKEN senast ändrade priset). Alla tider på sidan är svensk tid: fixturens
  "Today 21:00" = Everton–Coventry 20:00Z, `data-created` 10:46 = 09:46Z hämtat 09:57Z.
- Ö/U och AH: en `<tbody>` per lina; linan läses ur `table-main__doubleparameter`
  ("-2.5, -3" = kvartslinan −2,75). AH är hemmalagets handikapp, samma tecken som
  Pinnacle lagras med. Huvudlinan = den mest balanserade (som SBOBET).

## Insamlingen (`app/betexplorer.py`, `oddset._collect_betexplorer`)

- Bara djupvarvet (:00/:30) och SIST i det, efter ledgern och notisvakten, så att passets
  upp till fyra minuter aldrig försenar horisontfrysningarna.
- Matcher inom 7 dygn i `LEAGUE_PATHS`; en match frågas igen efter 25 min (≤ 3 h till
  avspark), 115 min (≤ 24 h) eller 715 min (längre). Närmast avspark först.
- Fixtursidan läses bara när en match som ska frågas saknar känt event-id; id:t läses
  sedan ur presence-ledgern. Referensen skapar aldrig matchidentiteter (`_resolve` mot
  befintliga rader, kollisioner rapporteras och hoppas över).
- 3 s mellan anropen, budget 240 s per pass, stopp efter tre transportfel i rad.
- Pris i `oddset_odds` (source `bet365`) med vår observationstid (efter anropet, minus
  Age). En lyckad sida utan bet365 markerar marknaden unavailable; ett transportfel gör det
  aldrig. Startad match sparas aldrig.
- Presence-ledger `oddset_betexplorer_capture` (ny tabell i `storage.py`, append-once per
  observationstid): en rad per anrop och marknad med `ok`, `listed`, huvudlina, antal
  linor, priser och bokens ändringstid (`changed_at`, JSON per tecken).
- Källhälsa `bet365`/`1x2` per liga; källprovet (`kalltest_ip.py`) har `betexplorer` som
  stödkälla. bet365 är passiv källa (`passive_sources`), inte kärnkälla.

## Ligorna (belagda 2026-11-06)

Allsvenskan 8/8, Superettan 8/8, Eliteserien 8/8, OBOS-ligaen 8/8, MLS 15/15, Premier
League 10/10, Championship 12/12, Serie A 10/10, La Liga 10/10, Bundesliga 9/9, Ligue 1 9/9,
Superliga 6/6, Pro League 9/9, Liga Portugal 9/9 (sju dygn), Champions League 18/18
(24–25/11). Europa och Conference League listas hos Betexplorer men vi har inga matcher där
ännu — beläggs då. Besta deild och Bolivia har inga kommande matcher; landslag och
träningsmatcher är inte prövade.

## Provkörning (temporär databas med serverns kommande matcher)

131 matcher att fråga, 14 fixtursidor, 79 anrop på 243 s: 22 matcher fick bet365 i 1X2 och
Ö/U, 21 i AH, inga fel. ~3,7 s per anrop. Behovet med takten ovan är ~40 matcher i timmen,
kapaciteten ~44; vid toppar får de längst bort vänta.

## Rollen

- `oddset_value.REFERENCE_BOOKS = {"bet365"}` ingår i `ANCHOR_SOURCES`: värdemotorn och
  WP5-ledgerns bästa-bok-val hoppar över den. Den är inte i `ANCHOR_BY_MARKET` och inte i
  `sharp_params`, så sharp- och modellversionerna är oförändrade (låst i
  `tests/test_betexplorer.py::RollTests`).
- Oddset-vyn: raden `365` under Sm/SBO i 1X2, Ö/U och AH; tooltipen visar när bet365
  senast ändrade priset (`book_changed_at` ur senaste lyckade svaret, bara när det bar
  samma pris och lina). Källhälsan har en bet365-rad. Poolanalysen är orörd.

## Inte gjort

- Betfair Exchange och BetInAsia (beslut driften-2026-11-06-betexplorer-per-bok) — samma
  modul klarar fler böcker (`BOOKS`), men det är ett eget beslut.
- Ingen jämförelserapport bet365 mot Svenska Spel/Smarkets ännu; underlaget samlas.
