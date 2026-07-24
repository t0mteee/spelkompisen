# PH0 — käll- och coverage-audit för poolspelshistoriken (2026-07-24)

Läsande audit enligt `docs/overlamning-till-claude-2026-07-24.md`. Skript:
`backend/scripts/ph0_kallaudit.py`; rådata per omgång och prov i
`docs/ph0-kallaudit-2026-07-24.json`. Inga modell- eller DB-ändringar.
157 API-requests med 0,35 s throttling, **0 × 429, 0 transportfel** —
rate limiting var aldrig ett problem i denna volym.

## Kohort A — lokalt observerade omgångar (`cohort=observed_pit`)

Ur `snapshots`/`sharp_snapshots` mot `draws.reg_close_time` (86 passerade
omgångar, en mer än överlämningens 85 — en topptipsomgång passerade i går).
"≤45 m" = omgångar där senaste observationen före horisonten är högst 45 min
gammal; med = medianlagg i minuter.

| Produkt | passerade | SvS T−24h | SvS T−3h | SvS T−20m | SvS close | Sharp T−24h | Sharp T−3h | Sharp T−20m | Sharp close |
|---|---:|---|---|---|---|---|---|---|---|
| Stryktipset | 7 | 7 (6 ≤45m, med 25) | 7 (5, 14) | 7 (6, 9) | 7 (6, 22) | 6 (3, 51) | 7 (5, 14) | 7 (7, 14) | 7 (7, 19) |
| Europatipset | 12 | 12 (10, 27) | 12 (8, 28) | 12 (10, 22) | 12 (11, 6) | 12 (6, 46) | 12 (5, 213) | 12 (10, 22) | 12 (10, 16) |
| Topptipset | 50 | 46 (39, 23) | 49 (46, 19) | 50 (45, 14) | 50 (44, 5) | 45 (25, 36) | 48 (38, 23) | 49 (36, 24) | 49 (38, 20) |
| Topptipset Stryk | 6 | 6 (6, 25) | 6 (4, 36) | 6 (6, 16) | 6 (6, 19) | 6 (3, 51) | 6 (4, 36) | 6 (6, 18) | 6 (6, 19) |
| Topptipset Extra | 11 | 11 (10, 26) | 11 (7, 28) | 11 (9, 22) | 11 (10, 2) | 11 (5, 46) | 11 (5, 213) | 11 (8, 24) | 11 (9, 14) |

Läsning:

- **T−20 min och close är starka överallt** (tätpollen var 5:e min när en
  omgång stänger inom 2 h gör sitt jobb): medianlagg 2–24 min.
- **T−24 h är svagast för sharp-serien** (median 36–51 min, hälften av
  omgångarna > 45 min) — 30-minuterscykeln plus att Pinnacle inte alltid har
  öppnat/matchats ett dygn före stopp. PH2 bör redovisa faktisk lagg per rad
  i stället för att anta horisonten träffad.
- 4 topptipsomgångar upptäcktes senare än 24 h före stopp (daglig produkt,
  nummerscanning) — de saknar T−24h-punkt och ska redovisas som missing,
  aldrig bakfyllas.
- Per-omgång-matrisen (exakta laggar per horisont och källa) ligger i
  JSON-filens `local.products.*.per_draw`.

## Kohort B — API-bakfyllbara äldre omgångar (`cohort=final_only`)

Sondering bakåt från senaste lokala omgång (fib-avstånd + binärsökning av
gränsen, ≤120 requests/produkt). "≥" = allt inom sonderingsbudgeten svarade;
gränsen ligger djupare.

| Produkt | senaste | äldsta åtkomliga | stängde | startOdds t.o.m. | streck/oms/result |
|---|---:|---:|---|---|---|
| Stryktipset | 4963 | **4267 (exakt gräns)** | 2013-01-12 | #4730 (2022-02-26) | hela spannet |
| Europatipset | 2593 | ≥ 1606 | 2016-10-18 | #2216 (2022-11-21) | hela spannet |
| Topptipset | 4233 | ≥ 3246 | 2024-12-08 | hela spannet | hela spannet |
| Topptipset Stryk | 973 | ≥ 363 | 2014-10-04 | #740 (2022-02-26) | hela spannet |
| Topptipset Extra | 1852 | ≥ 865 | 2016-10-16 | #1475 (2022-11-21) | hela spannet |

Fältmönster (samstämmigt över alla fem produkter):

1. **`svenskaFolket` (slutstreck), `currentNetSale` (slutomsättning) och
   result-endpointen finns kvar över HELA det åtkomliga spannet** — 100 % av
   proverna, ned till 2013 för Stryktipset. Result ger kompletta prisnivåer
   (vinnare + belopp per nivå), utfall per match, `cancelled`-flaggor och
   omsättning. Prover utan result var enbart ännu ej färdigspelade omgångar
   (state `Open`/`Closed`).
2. **`odds` (aktuellt SvS-odds) är flyktigt**: fullt bara på de senaste 1–4
   omgångarna, ibland partiellt (t.ex. 5/13), sedan borta. Aktuella odds kan
   ALDRIG bakfyllas — oddsrörelser existerar bara i kohort A.
3. **`startOdds` når till ~feb 2022** (Stryktipset/Stryk-varianten) resp.
   **~nov 2022** (Europatipset/Extra); Topptipset (yngre serie) har det i
   hela spannet. OBS metodregeln: `startOdds` är INTE en tidsstämplad
   rörelsepunkt förrän dess providersemantik verifierats — får användas som
   statisk öppningsreferens först efter det, och aldrig som "rörelse".
4. **API:ts `drawState` är korrekt (`Finalized`) på gamla omgångar** — det är
   bara lokala `draws.state` som fryser vid senaste refresh. PH1 kan alltså
   läsa settlement-status från API:t; lokala tabellen får inte användas som
   facit (bekräftar överlämningens varning).
5. Inga strukna matcher i just dessa 74 prover (`n_cancelled=0` överallt),
   men fälten finns på både draw- och result-nivå; PH1-backfillen ska bokföra
   dem per event. Produktnamnbyten (t.ex. "VM-tipset") syntes inte i proverna
   och återstår att hantera i backfillen — sluggen är stabil och är den enda
   identitet som ska användas.
6. Varianterna `topptipset`/`topptipsetstryk`/`topptipsetextra` har egna
   nummerserier och svarar alla via sina egna slugs — de ska backfillas
   separat och först grupperas i analyslagret (aldrig i lagringen).

## Konsekvenser för PH1–PH4

- **PH1 (settlementlager) är genomförbart i stor skala**: Stryktipset ~700
  omgångar (2013→), Europatipset/Extra ~1000+ (2016→), Stryk-varianten
  ~600 (2014→), Topptipset ~1000 (2024→, daglig). Slutstreck + omsättning +
  full utdelning + utfall överallt; `final_only`-stämpel obligatorisk.
- **Radpris**: `rowPrice` finns på alla sonderade omgångar (1 kr; Topptipset
  varierande insats) — spara den, fältprognoser behöver den.
- **Rörelseanalys (odds/streck över tid) kan bara göras i kohort A** och
  växer med ~5–10 omgångar/vecka framåt. Ingen bakfyllnad kan ändra det.
- **Backfill-takt**: 0,35 s/request utlöste ingen throttling; en full
  PH1-backfill (~3 500 omgångar × 2 anrop) tar ~40 min i den takten och bör
  köras i omgångar med resumability ändå.
- Äldsta-gränsen för Europatipset/varianterna är inte uttömd — PH1-backfillen
  upptäcker den naturligt genom att gå tills 404-serien blir permanent
  (Stryktipsets hårda gräns #4267 är redan belagd).

## Nästa steg (överlämningens ordning)

PH1: förslag på exakt settlement-schema + testfall, därefter migrationsskript
med backup och rapport i `docs/db-atgarder.md`. Byggaren rör inte befintliga
`snapshots`-semantiker.
