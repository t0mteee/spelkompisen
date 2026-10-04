# Överlämning 2026-10-03 — Oddsets delade identiteter (pin:/svs:)

## Kort

- **Hypotesen stämmer.** `oddset.collect()` länkade bara mot rader inom
  listfönstret [nu−12 h, nu+10 d]. När Pinnacle och Svenska Spel listade samma
  match mer än tio dygn före avspark, i olika varv, fick varje källa en egen
  rad. Käll-id:n är write-once, så raderna slogs aldrig ihop.
- **Commit 6f1db2e (landslag) är inte orsaken.** Den ändrar bara kopplingen
  för ligor med `landslag: True`, och den första delade matchen skapades
  2026-08-30, en månad tidigare.
- **Rättelsen är i drift sedan 2026-10-03T20:45:28Z** (commit 77bc50d, pull
  och omstart av backend). Livekassan b9de5c0 och Smarkets dd1375e hade en
  annan session redan dragit ned 18:46.
  Länkningen prövar nu ligans alla kommande rader. Länkreglerna är oförändrade.
- **De 170 kommande paren är sammanslagna** sedan 2026-10-03T20:46:40Z, efter
  Samans godkännande. Det gjordes med `backend/scripts/migrera_oddset_identitetspar.py`:
  backup först, 0 par kvar, `integrity_check` ok och 0 identitetskonflikter.
  Utfallet står i avsnitt 5.
- **138 passerade par lämnas orörda.** Append-only-tabeller (WP5, V2.2,
  frånvaro) refererar båda raderna.
- **2026-10-04 (Samans beslut):** signalversionen lämnas med datumnot. PSG
  kopplas via källkopplingens eget alias, och de tre delade PSG-paren är
  sammanslagna. Driftvakten fick kontroll H, som larmar när en match får två
  rader (avsnitt 8).

## 1. Mekanismen i koden

| Steg | Kod (före rättelsen) | Följd |
|---|---|---|
| Kandidater | `cands = store.oddset_matches(since=nu−12 h, until=nu+10 d)`. Gränsen infördes i 047f7c5 (2026-07-16, prisnärvaron). | Rader längre fram är inga kandidater. |
| Exakt id | `oddset_match_by_source_id` söker globalt. | Källans egen rad hittas alltid. Den läggs inte i `cands`. |
| Fuzzy | `_resolve_source` → `_resolve` prövar bara `cands` som saknar källans id. | Den andra källan ser aldrig den första källans rad bortom fönstret. |
| Ny rad | `pin:<id>` eller `svs:<id>` läggs i `cands` för resten av varvet. | Länk sker bara om båda källorna dyker upp i **samma varv**. |
| Senare varv | Båda raderna har nu sitt eget id. | Exakt id vinner varje gång. Dubbletten är permanent. |

En precisering av hypotesen: ordningen spelar ingen roll. Det räcker att den
första källans rad ligger utanför fönstret när den andra källan dyker upp. Av
301 sådana par listade Svenska Spel sist i 248 fall och Pinnacle sist i 53.

## 2. Data (läst med `mode=ro` 2026-10-03 cirka 10:30Z)

### Andel delade matcher per startvecka

"Länkade" är matcher med båda id:n på samma rad. "Delade" är par där en ren
Pinnacle-rad och en ren Svenska Spel-rad är samma match enligt insamlingens
egen regel (`_resolve`). Ledtid är tiden mellan första prisobservationen och
avspark.

| Startvecka (mån) | Länkade | Delade | Delad | Median ledtid Pinnacle | Median ledtid SvS | Båda > 10 d |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07-13 | 29 | 0 | 0 % | 5,1 d | 4,2 d | 0/29 |
| 2026-07-20 | 117 | 1 | 1 % | 2,2 d | 1,8 d | 0/118 |
| 2026-07-27 | 170 | 5 | 3 % | 1,9 d | 1,9 d | 0/173 |
| 2026-08-03 | 132 | 0 | 0 % | 4,2 d | 4,1 d | 0/131 |
| 2026-08-10 | 162 | 0 | 0 % | 5,2 d | 5,1 d | 4/162 |
| 2026-08-17 | 147 | 0 | 0 % | 5,1 d | 6,4 d | 19/147 |
| 2026-08-24 | 176 | 2 | 1 % | 6,2 d | 6,7 d | 18/178 |
| 2026-08-31 | 132 | 17 | 11 % | 6,0 d | 7,0 d | 16/148 |
| 2026-09-07 | 123 | 52 | 30 % | 6,8 d | 9,9 d | 58/175 |
| 2026-09-14 | 126 | 61 | 33 % | 7,0 d | 7,0 d | 61/187 |
| 2026-09-21 | 16 | 0 | 0 % | 7,0 d | 7,0 d | 0/16 |
| 2026-09-28 | 28 | 0 | 0 % | 1,3 d | 1,3 d | 0/28 |
| 2026-10-05 | 31 | 75 | 71 % | 20,1 d | 19,1 d | 78/106 |
| 2026-10-12 | 2 | 91 | 98 % | 27,2 d | 26,2 d | 93/93 |
| 2026-10-19 | 0 | 4 | 100 % | 28,4 d | 23,1 d | 4/4 |

Felet följer ledtiden. I juli och augusti listade källorna matcherna 2–6
dygn före avspark. Efter landslagsuppehållet listades omgångarna 19–28 dygn
före. De 39 tidigt listade men länkade augustimatcherna sågs första gången i
samma varv, 2026-07-23 kl. 21Z, när de fyra stora ligorna lades till. Veckorna
21/9 och 28/9 var landslagsuppehåll med få klubbmatcher.

### Ligger motpartsraden utanför fönstret när den andra källan dyker upp?

| Utfall | Par | Kommentar |
|---|---:|---|
| Utanför fönstret | 301 | Ledtid minst 10,0 d (SvS) och 10,3 d (Pinnacle), median 19 d. Mellan källornas första observation: median 15,7 h, 0,04–176,5 h. |
| Inom fönstret | 6 | Juli–augusti, fyra av dem träningsmatcher. Namn som fick alias senare (IBV, Wolves), kod före identitetsfixen 26/7 och avsparkstider som troligen skilde mer än 2 h vid första listningen (Aston Villa–Arsenal 31/8). Historiska tider sparas inte, så det går inte att avgöra per par. |
| Okänt | 1 | Wolves–Racing Santander (träningsmatch) saknar SvS-pris. |
| **Summa** | **308** | sedan 2026-07-16 |

### Exempel

| Match | Avspark (UTC) | Pinnacle-rad, första pris | SvS-rad, första pris |
|---|---|---|---|
| Arsenal–Lille (CL) | 2026-10-13 19:00 | `pin:1636267513`, 2026-09-11 04:28 | `svs:1028943219`, 2026-09-11 08:30 |
| Manchester City–PSG (CL) | 2026-10-14 19:00 | `pin:1636267533`, 2026-09-11 04:28 | `svs:1028943200`, 2026-09-11 08:00 |
| Arsenal–Leeds (PL) | 2026-10-10 11:30 | `pin:1636483914`, 2026-09-13 16:28 | `svs:1028072797`, 2026-09-14 09:31 |
| Manchester City–Ipswich (PL) | 2026-10-17 14:00 | `pin:1637095136`, 2026-09-21 08:57 | `svs:1028072700`, 2026-09-21 09:30 |

Manchester City–PSG är dessutom ett namnfall (se 6). `PSG` och
`Paris Saint-Germain` ger likheten 0,27 och länkas inte ens inom fönstret.

## 3. Följder

### Kommande matcher (170 par, avspark 9–19/10)

- Svenska Spels och Expekts priser ligger på en rad utan Pinnacle. Ingen
  sharp-värdering mot Svenska Spel kan ske för de matcherna.
- Amber-modellflaggor har loggats på Svenska Spel-raderna: 60 i 43 par
  10:30Z och 88 i 44 par vid migreringen. De kan aldrig stängas, eftersom
  raden saknar Pinnacle.

### Passerade matcher (138 par, främst 7–20/9)

| Tabell | På Pinnacle-raderna | På SvS-raderna | Effekt |
|---|---:|---:|---|
| `oddset_value_log` | 0 | 470 (amber, 0 stängda) | Inga sharp-flaggor mot SvS. Modellflaggorna kunde inte stängas. |
| `oddset_prediction_capture` | 684 | 684 | Varje match fångades två gånger. SvS-radernas 1 899 prediktionsrader stängdes aldrig, så close-EV dubbelräknar inget. Pinnacle-radernas sharp-rader saknar SvS-pris. |
| `oddset_v22_shadow_capture` | 270 (248 eligible) | 270 (alla `sharp_missing`, ej eligible) | V2.2-grinden påverkas inte. |
| `oddset_absence_capture` / `_player` | 3 217 / 19 338 | 3 200 / 19 413 | Frånvaron fångades dubbelt (amber). |
| `oddset_live_signal` | 38 | 13 | Ingen match har signal på båda raderna. |
| `oddset_odds` | 69 356 | 40 196 | — |

De passerade paren slås inte ihop. Deras captures är append-only och finns på
båda raderna. En sammanslagning skulle kräva att mätrader raderas eller skrivs
om. Inga priser eller signaler bakfylls.

## 4. Rättelsen (kod)

`backend/app/oddset.py`, `collect()`:

- `link_cands` = ligans alla rader med avspark från nu−12 h. Pinnacle- och
  Svenska Spel-stegen länkar mot den listan.
- `cands` = samma dict-objekt filtrerade till listfönstret. Den styr som förut
  frånvaromarkering, sidoböcker, Smarkets och Matchbook.
- Lagparsvägen för researchligor (utan tidsankare) stannar i fönstret.
- Oförändrat: `_resolve` (0,55 per sida, 0,75 för paret, ±2 h),
  `_resolve_landslag`, write-once-id, unikhetsindexen och
  `oddset_identity_conflicts`.

En befintlig dubblett läker inte av sig själv. Exakt id vinner fortfarande,
och det är avsiktligt.

Kostnad: 463 kommande rader i hela databasen (193 bortom tio dygn). Frågan
körs en gång per liga och varv.

Tester i `tests/test_oddset_collect.py::IdentityBeyondListWindowTests`:

| Test | Före rättelsen | Efter |
|---|---|---|
| SvS länkar mot Pinnacle-rad 20 d fram | 2 rader (fel) | 1 rad `pin:p1` |
| Pinnacle länkar mot SvS-rad 20 d fram | 2 rader (fel) | 1 rad `svs:k1` |
| Befintlig dubblett slås inte ihop av insamlingen | grön | grön |
| Samma lagpar 3 h ifrån varandra förblir två matcher | grön | grön |

## 5. Migreringen (körd 2026-10-03T20:46:40Z)

### Utfall i drift

Saman godkände körningen 18:4x samma dag. Snapshot-jobbet var vilande när det
stoppades (20:46:35Z) och startades igen 20:47:21Z, så inget varv avbröts.

| Mått | Före | Efter |
|---|---:|---:|
| Godkända par / sammanslagna | 170 | 170 (0 kvar att göra) |
| `oddset_matches` | 3 934 | 3 764 |
| `oddset_odds` totalt | 898 318 | 898 318 |
| Oddsrader på SvS-id | 2 805 | 0 (flyttade: svenskaspel 1 805, expekt 754, smarkets 186, ninjacasino 60) |
| `oddset_sharp_alt` / `oddset_matchbook_liquidity` på SvS-id | 0 / 0 | 0 / 0 |
| Modellflaggor kvar på gammalt SvS-id | 88 i 44 par | 88 i 44 par |
| Pinnacle-rader med Kambi-id (av 170) | 0 | 170 |
| Identitetskonflikter på de sammanslagna raderna | 0 | 0 |
| `integrity_check` | — | ok |

Backup: `backend/data/backups/stryktips-2026-10-03T204640Z-fore-oddset-identitetspar.db`
(895 MB). Torrkörningen 20:46:26Z gav samma 170 par som den granskade planen.
Den gav 0 par efteråt. Arsenal–Lille (`pin:1636267513`, Kambi 1028943219)
bär nu pinnacle, derived, svenskaspel, expekt och smarkets på samma rad.

### Reglerna

`backend/scripts/migrera_oddset_identitetspar.py` slår ihop ett par bara när
allt nedan gäller:

1. Samma liga, en ren `pin:`-rad och en ren `svs:`-rad med självbärande id.
2. Avsparkarna skiljer högst 15 min. Avsparken ligger mellan nu + 49 h och
   2026-10-31. Flashscore-frånvaron fryses 48 h före avspark och WP5/V2.2
   24 h före.
3. Insamlingens egen förstalänk hade kopplat dem. För landslag gäller landskod.
4. Minst ena laget är strikt lika (samma ordmängd, eller en ordmängd som ryms
   i den andra), och truppmarkörerna är lika på båda sidor.
5. Entydigt åt båda hållen.
6. SvS-raden har inga rader utanför `oddset_odds`, `oddset_sharp_alt` och
   `oddset_matchbook_liquidity`. Modellflaggorna i `oddset_value_log` lämnas
   kvar på sitt gamla id (⚖ 2).
7. Paret står i den granskade planen (`--plan`).

Pinnacle-raden är kanon. Kambi-id, Kambis visningsnamn och oddshistoriken
flyttas dit, och SvS-raden tas bort. Antalet oddsrader är oförändrat. En
transaktion (`BEGIN IMMEDIATE`) omfattar allt. Den rullas tillbaka om antalet
rader ändras, om samtidiga prisvarianter uppstår eller om ett godkänt par
finns kvar. `integrity_check` körs efter commit, utanför skrivlåset.

### Torrkörning mot produktionen 2026-10-03T10:33Z (`mode=ro`)

Planen ligger i `docs/oddset-identitetspar-plan-2026-10-03.json`.

| Utfall | Antal |
|---|---:|
| Par att slå ihop | **170** (exakt 120, ordmängd 29, ena laget 21) |
| Överhoppade (för nära, referenser, tvetydiga) | 0 |
| Oddsrader att flytta | 2 380 (svenskaspel 1 542, expekt 721, ninjacasino 60, smarkets 57) |
| Modellflaggor kvar på gammalt id | 60 i 43 par |
| Första och sista avspark | 2026-10-09 17:00Z och 2026-10-19 19:00Z |

| Liga | Par | Exakt | Ordmängd | Ena laget |
|---|---:|---:|---:|---:|
| premier_league | 19 | 11 | 8 | 0 |
| serie_a | 18 | 16 | 0 | 2 |
| conference_league | 18 | 11 | 4 | 3 |
| europa_league | 18 | 13 | 3 | 2 |
| la_liga | 17 | 15 | 0 | 2 |
| champions_league | 17 | 12 | 0 | 5 |
| ligue_1 | 16 | 14 | 2 | 0 |
| championship | 12 | 7 | 5 | 0 |
| bundesliga | 9 | 4 | 2 | 3 |
| belgian_pro_league | 9 | 3 | 4 | 2 |
| allsvenskan | 8 | 8 | 0 | 0 |
| danish_superliga | 6 | 3 | 1 | 2 |
| superettan | 3 | 3 | 0 | 0 |

"Ena laget" är till exempel Midtjylland–FC Copenhagen mot FC Midtjylland–FC
Köpenhamn och Augsburg–Bayern Munich mot FC Augsburg–Bayern München. Alla 21
står med namn i planen.

Sidoböcker som har fragment på båda raderna (Expekt i 32 par, Ninja 12,
Smarkets 10) gav inga samtidiga prisvarianter. `oddset_latest` väljer senaste
`fetched_at`, så ett gammalt fragment kan visas som senaste pris tills källan
setts i nästa varv. Värde kräver ändå ett pris som bekräftats inom 45 min.

### Så kördes den

Körningen gjordes i ett pool- och agentfritt fönster (h24/h3 ±45 min, m20 och
agentens 6h-/30m-fönster blockerar). `tjanster.sh` kräver `--ja` utan
terminal. Plisten har `RunAtLoad`, så `start` kör ett varv direkt.

```bash
cd ~/spelkompisen && tools/tjanster.sh stopp snapshot --ja
```

```bash
cd ~/spelkompisen/backend && .venv/bin/python -B scripts/migrera_oddset_identitetspar.py
```

```bash
cd ~/spelkompisen/backend && .venv/bin/python -B scripts/migrera_oddset_identitetspar.py --kor --plan ../docs/oddset-identitetspar-plan-2026-10-03.json
```

```bash
cd ~/spelkompisen && tools/tjanster.sh start snapshot --ja
```

Snapshot-jobbet stoppas så att inget varv med gamla kandidatlistor i minnet
skriver sidoboksodds till en borttagen `svs:`-rad. Skriptet är idempotent: en
ny körning med samma plan slår ihop 0 par och tar en ny backup.

## 6. Namnmissar (separat fynd, inte fönstret)

16 delningar sedan juli beror på namnen och hade skett även inom fönstret.
Ingen av dem är med i planen från 2026-10-03. PSG är rättat 2026-10-04 (avsnitt 8).

| Lag | Pinnacle | Svenska Spel | Par | Varav kommande |
|---|---|---|---:|---:|
| PSG | Paris Saint-Germain | PSG | 10 | 3 (PSG–Le Mans 10/10, Manchester City–PSG 14/10, Strasbourg–PSG 17/10) |
| Žalgiris | Vilnius Zalgiris | Žalgiris Vilnius | 3 | 0 |
| DAC | DAC 1904 | DAC Dunajska Streda | 3 | 0 |

32 ensamma SvS-rader sedan juli har ingen Pinnacle-rad med samma avspark
(träningsmatcher 11, Conference League 6, med flera). Det är källans utbud,
inte länkningen.

## 7. ⚖ Beslut för Saman

1. ✅ **Kör migreringen?** Saman: ja (2026-10-03 18:4x). Körd 20:46:40Z.
2. ✅ **Modellflaggorna på SvS-raderna** (88 vid körningen). Saman godkände
   rekommendationen att lämna dem på sitt gamla id. De loggades med en modell
   utan Pinnacle-ankare, eftersom Pinnacle låg på den andra raden. Med rätt
   länk hade de sett annorlunda ut eller inte funnits. De stängs aldrig,
   precis som tidigare, och utfallsvisningen upphör för dem.
3. ✅ **Signalversion.** Saman 2026-10-04: låt vara. Datumnoten gäller,
   2026-10-03T20:45:28Z för koden och 20:46:40Z för de sammanslagna paren.
   Ingen `DATA_VERSION`-bump: signalernas innebörd är oförändrad och ingen
   befintlig signal var fel. Skörden redovisar regimen. Samma not gäller
   V2.2, som efter rättelsen ser Kambis visningsnamn på tidigt listade matcher,
   som före september. Ingen ny manifestversion.
4. ✅ **PSG.** Saman 2026-10-04: rätta. Det görs med källkopplingens EGET
   alias (`oddset.ODDS_LINK_ALIASES`, `psg` → `paris saint germain`), inte i
   `TEAM_ALIASES`. Avsnitt 8 förklarar varför. Žalgiris och DAC har inga
   kommande matcher.
5. ✅ **Vaktkontroll.** Saman 2026-10-04: kör. Den finns i vakt-v3 som
   kontroll H, se avsnitt 8.

## 8. 2026-10-04: PSG och vaktkontrollen

### PSG via källkopplingens alias

Förslaget i går var ett alias i `TEAM_ALIASES`. Det hade ändrat `norm_team`,
och den används på fler ställen än källkopplingen:

| Läsare av `norm_team` | PSG-namnen där | Följd av ett globalt alias |
|---|---|---|
| Oddsets källkoppling | SvS `PSG`, Pinnacle `Paris Saint-Germain` | önskad: matcherna kopplas |
| Poolmatcharen (pool-name-v7) | Svenska Spels pool skriver `Paris Saint-Germain` (21 poolhändelser, aldrig `PSG`) | ingen |
| Liveradarns länk (v13, kohort sedan 2026-10-03T08:45Z) | Flashscore `PSG`, FotMob `PSG` eller `Paris Saint-Germain` | ändrad länkväg mitt i kohorten; kohortregeln kräver då en ny radarversion |
| Resultatnormaliseringen (Ligue 1) | en resultatrad `psg` | ändrad modelldata |
| Modellen | Ligue 1 ger inga modellprognoser (0 sedan 21/8) | ingen |

`ODDS_LINK_ALIASES` används bara i `_team_pair_score`, alltså av
`_resolve` (Pinnacle, Svenska Spel, sidoböcker, Smarkets, Matchbook) och av
migreringsskriptet. `norm_team("PSG")` är fortfarande `psg`, vilket ett test
låser. Rättelsen ändrar alltså bara Oddsets källkoppling. Det är samma mönster
som poolens `_POOL_TEAM_ALIASES` och radarns `LIVE_TEAM_ALIASES`.

De tre redan delade paren slogs ihop 2026-10-04T08:32:12Z med samma skript
och en granskad plan (`docs/oddset-identitetspar-plan-2026-10-04-psg.json`):
3 av 3 par, 80 oddsrader flyttade, `integrity_check` ok och 0
identitetskonflikter. Koden (`e3f9507`) driftsattes 08:30:11Z. Detaljer i
`docs/db-atgarder.md`.

| Avspark (UTC) | Pinnacle-rad | Svenska Spel-rad | Match |
|---|---|---|---|
| 2026-10-10 18:45 | `pin:1636549962` | `svs:1027973940` | PSG–Le Mans (Ligue 1) |
| 2026-10-14 19:00 | `pin:1636267533` | `svs:1028943200` | Manchester City–PSG (CL) |
| 2026-10-17 15:15 | `pin:1637154821` | `svs:1027973858` | Strasbourg–PSG (Ligue 1) |

### Vaktkontroll H (vakt-v3)

`check_identitet` i `app/vakt.py` letar efter kommande matcher med en ren
Pinnacle-rad och en ren Svenska Spel-rad. Raderna ska ha samma liga, avspark
högst 2 h isär, samma truppmarkörer och minst ett gemensamt lag (landslag på
landskod). Ett lag spelar en match i taget, så ett gemensamt lag räcker. Då
fångas både listfönsterfelet och namnmissar. Fyndet `oddset_delad_identitet`
är en varning under "Drift att se över" på Idag. Det startar ingen larmkörning
hos agenten, eftersom bara `error` gör det. Före PSG-sammanslagningen hittade
den exakt de tre PSG-paren och inget annat. Trösklar: `docs/vakt.md`.
