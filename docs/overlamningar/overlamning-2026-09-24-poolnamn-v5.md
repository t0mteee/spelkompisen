# Överlämning 2026-09-24 — pool-name-v5 (driftsatt 2026-09-24T14:30:53Z)

## Uppdrag och status

Förbered en ny namn- och tidsregel för poolens Pinnacle-matchning,
`pool-name-v5`. **Driftsatt 2026-09-24T14:30:53Z efter Samans beslut 1A** (datumnot i manifesten, ingen ny manifestversion). Nedan står förslaget som det skrevs före beslutet. Arbetet är gjort i
worktreen `/tmp/spk-v5` på MacBook-servern, gren `pool-name-v5` från main
`0ec4e72`. Ingen merge, push, omstart eller launchctl. Produktionskopian
`~/spelkompisen` är orörd; produktionsdatabasen är bara läst med `mode=ro`.
Inga insamlare körda.

Underlag: Pinnacles publika index 12:25:37Z (granskarens,
`/tmp/spk-audit/B/pinnacle_index.json`, 930 rader) och EN egen read-only-
hämtning 14:12:30Z (Age 284 s, 920 rader). SvS öppna omgångar (spelstopp i
framtiden) hämtade read-only via `app.svenskaspel` 13:55Z: 12 omgångar, 106
matcher (82 unika), plus 13 öppna Bomben-omgångar (39 matcher).

`docs/plan.md`, `CLAUDE.md` och manifesten är inte ändrade. Föreslagna
texter står längst ned.

## Problemet i v4

Av 106 matcher i de öppna omgångarna avvisade v4 39 på namn och 5 som
tvetydiga, fast rätt Pinnacle-rad fanns med exakt samma avspark.
Stryktipset 4972: 0 av 13. Tre orsaker:

1. **Delnamn gav 0.** `team_sim` fäller alla delsträngspar för att skydda
   Inter/Inter Miami och Barcelona/Barcelona SC, så även Plymouth/Plymouth
   Argyle och tio andra engelska kortnamn i 4972.
2. **Tvetydighetsvakten räknade 36 h bort.** England–Spanien fick Finland–
   Spain 27 h tidigare som andra kandidat (England~Finland 0,714);
   Turkiet–Frankrike fick Ukraine–Turkiye dagen efter.
3. **CZE blev Czech Republic**, Pinnacle skriver Czechia.

Nya fynd under arbetet:

- **Bomben 18570, Leksand–Almtuna (HockeyAllsvenskan)**: v4 länkar den i
  dag till fotbollsmatchen Sweden–Poland 28 h senare (speglad, konfidens
  0,808). Orsak: SvS sätter isoCode SWE även på hockeyklubbarna, så
  "Sweden" blev kandidat, och Leksand~Poland är 0,615. Samma klass som den
  historiska felkopplingen Vestmannaeyja–Valur → Iceland–Switzerland.
- **v4 länkar fel när rätt rad saknas.** Med exakta namn och rätt rad
  borttagen ger v4 8 fel i dagens index (England–Spain → Finland–Spain,
  Turkiye–France → Ukraine–Turkiye, Manchester United–West Ham United →
  Chesham United–Maidenhead United, Pachuca–Santos Laguna → en annan rad
  med samma lag i omvänd ordning 4 h senare m.fl.). När alla indexrader läggs på samma avspark ger v4
  dessutom Serbien–Grekland → Georgia–Greece och Skottland–Schweiz →
  Switzerland–Poland.
- Fyra v4-länkar gick redan i dag bara på stavningslikhet mellan landsnamn
  (Georgien–Nordirland 0,846, Turkiet–Italien 0,929, Nordirland–Ungern
  0,846, Skottland–Schweiz 0,912). I v5 är de exakta (nivå A).

## Regeln pool-name-v5

Kod: `backend/app/odds_provider.py` (namnregeln) och
`backend/app/pinnacle.py` (`match_index`, nivåval).

1. **Tidsankare.** När SvS-avsparken är känd prövas bara kandidater vars
   avspark är känd och ligger högst 15 min bort (`POOL_ANCHOR_S`, 15 min
   ingår). Kandidat utan avspark är inte behörig. Är SvS-avsparken okänd
   (saknas eller går inte att tolka) gäller v4-vägen oförändrad
   (`_match_index_v4`, träffen får `match_tier="v4"`). 36 h används kvar
   bara för diagnostikens sökledtrådar, så en flyttad avspark syns där.
2. **Nivåer** bland behöriga kandidater och båda orienteringarna:
   A = exakt/alias på båda sidor; B = exakt/alias + generiskt delnamn;
   C = generiskt delnamn på båda; F = stavningslikhet med oförändrade
   trösklar (sida ≥ 0,60, snitt ≥ 0,72). Bästa nivån vinner. Mer än en
   kandidat eller orientering på bästa nivån ⇒ `ambiguous`, ingen länk. En
   lägre nivå blockerar aldrig en högre.
3. **Generiskt delnamn** (`pool_part`): efter `_norm_team` är det kortare
   namnets ord ett sammanhängande prefix eller suffix av det längres, och
   alla övriga ord är klubbformsord (listan nedan). Det kortare namnet måste
   bära minst ett eget ord (Athletic ≠ Athletic Club). Samma trupp krävs,
   inte i `TEAM_REJECTED_LINKS`, inte i den nya poolspecifika
   `_POOL_REJECTED_PARTS`, och inget av namnen får vara ett landsnamn
   (Oman ≠ Oman Club). `team_sim` är orörd: delnamn ger fortsatt 0 där.
4. **Landslag.** ISO-landsnamn blir kandidat endast när SvS-deltagarens namn
   är landets svenska namn för dess isoCode (pycountrys `sv`-katalog, namn
   och common_name, även delen före komma: "Moldavien, republiken"). SvS
   avkortningar godtas: varje ord ett prefix med minst fem tecken totalt
   (Nederländ, Liechtens, Nordirlan, Bosnien/H, För.Arabemiraten) eller
   första ordet (minst fem tecken) följt av enbokstavsförkortningar
   (Bosnien o). St./Sankt/Saint och &/och/and likställs. Truppmarkörer
   följer med (Sverige U21 → Sweden U21). Engelska kandidater:
   `english_name` (med `_ISO_OVERRIDE`), pycountrys name/common_name,
   `{"CZE": ["Czechia"], "TUR": ["Turkiye", "Turkey"]}` och SvS FIFA-koder
   utan ISO-land: ENG, SCO, WAL, NIR, XXK (alla observerade i dagens
   omgångar). Svenska extraformer: DR Kongo (COD, SvS deltagarnamn i 12
   länkade poolrader mot DR Congo) och England (GBR, följer `_ISO_OVERRIDE`). En klubb
   med isoCode får aldrig landsnamn. Alla 57 landslagsdeltagare i dagens
   omgångar och Bomben-omgångar känns igen; ingen klubb gör det. I SvS
   namnhistorik (som saknar landskod) känns bara landsnamn och SvS
   avkortningar av dem igen under någon kod; enda klubbnamnet som skulle
   kunna det är Öster, och då bara under Österrikes kod (Öster har SWE).
5. **Tillägg utöver uppdraget, motiverat av den adversariala kontrollen:
   landsnamn matchas bara exakt.** En sida där SvS-deltagaren är ett igenkänt
   landslag, eller där SvS- eller Pinnacle-namnet är ett landsnamn, kan bara
   bli exakt/alias (samma land i annan skrivform, t.ex. St./Saint, räknas
   som exakt). Stavningslikhet mellan två länder är alltid fel
   (England~Finland, France~Ukraine, Austria~Australia, Iceland~Ireland,
   Slovakia~Slovenia, Niger~Nigeria), och delnamn eller stavning mellan
   klubb och land var Vestmannaeyja- och Leksand-klassen. Kostnaden: ett
   landslag som INTE känns igen (t.ex. om SvS utelämnar isoCode) kan inte
   längre fuzzy-länkas till Pinnacles landsnamn.
6. **Behållet:** kontextaliaset Estudiantes/Lanús (räknas som exakt när dess
   egen regel håller, annars ingenting), kända falska par, truppmarkörer,
   hörn-/kortfiltret och alla befintliga poolalias. Nya poolalias, var och
   ett belagt i indexet 2026-09-24 med exakt avspark, samma motståndare och
   entydigt namn: `nashville → nashville sc` (Toronto FC, id 1636866540),
   `bucaramanga → atletico bucaramanga` (Once Caldas, id 1636734323),
   `internacional de bogota → inter bogota` (Pereira/Deportivo Pereira via
   generiskt delnamn, id 1636816733; klubben hette La Equidad till 2025).
   **Medvetet inte alias:** Aguilas (indexet har både Aguilas–Hercules i
   Spanien och Aguilas Doradas), Fortaleza (Fortaleza och Fortaleza CEIF),
   America (Club America och America Mineiro) — samma klass som Estudiantes.
7. `POOL_MATCH_VERSION = "pool-name-v5"`. Träffen bär `match_tier` (A/B/C/F,
   eller "v4" för vägen utan SvS-avspark). Konfidens: A 1,0, B 0,9, C 0,8,
   F snittet som förut; beslutet ligger i `match_tier`. Avslagsdiagnostiken
   är oförändrad i form (samma nycklar till `pool_match_diagnostic`, upp till
   fem sökledtrådar) och har fått `qualifying_tier`;
   `qualifying_candidates` räknar nu kandidaterna på bästa nivån.
   `match_tier` sparas inte i databasen, precis som `match_version` i dag —
   ingen schemaändring.
8. **Bomben** går via `Pinnacle.match` → samma `match_index`. Kontrollerad
   nedan; `swapped`-speglingen av xG är oförändrad.

### Klubbformsorden, ord för ord

Prövat mot dagens index (1 500 lagnamn), dagens SvS-namn och hela SvS
namnhistorik i `pool_event_settlement` (2 674 namn, read-only). "Indexpar" =
två lagnamn som Pinnacle själv listar och som ordet skulle göra till
varandras delnamn. Enda sådana par i indexet är Dundee FC/Dundee United
(united), som står i `_POOL_REJECTED_PARTS`; därefter inga. Skript:
`/tmp/spk-audit/v5/word_audit.py`; `word_audit_fore_avvisningar.json` är
provet före avvisningarna (där de olika klubbarna syns), `word_audit.json`
och `word_audit_slutlig.txt` den slutliga listan.

| Ord | Dagens nya länkar | SvS-historik → index, samma klubb | Olika klubbar (→ `_POOL_REJECTED_PARTS`) | Beslut |
|---|---|---|---|---|
| united | Cambridge, Colchester, Galway, Peterborough, Rotherham | Carlisle, Ebbsfleet, Hartlepool, Maidenhead, Maidstone, Scunthorpe, Southend, Sutton, Telford, Torquay, Treaty, West Ham m.fl. (18) | Dundee/Dundee United (båda finns i indexet) | med |
| town | Cheltenham, Fleetwood, Grimsby, Shrewsbury, Swindon | Aldershot, Athlone, Braintree, Halifax, Harrogate, Longford, Slough, Yeovil m.fl. (13) | — | med |
| county | Newport, Stockport | samma två | — | med |
| alexandra | Crewe | Crewe | — | med |
| rovers | Tranmere | Tranmere, Forest Green | — | med |
| stanley | Accrington | Accrington | — | med |
| argyle | Plymouth | Plymouth | — | med |
| albion | Burton | Burton, West Bromwich | — | med |
| wanderers | Wycombe | Wycombe, Bolton, Dorking | — | med |
| gremio | Novorizontino | Novorizontino | — | med |
| deportivo | Pereira | Pereira, Toluca | Deportivo Municipal/Municipal (PER/GUA), Morön BK/Deportivo Morón | med + avvisningar |
| club | Tijuana | Tijuana, León, Libertad Asunción, Olimpia Asunción, Nacional de Football, Sportivo Luqueño, Defensor Sporting | America/Club America, Guarani/Club Guarani, Club Aurora/Aurora FC | med + avvisningar |
| city | — | Bradford, Cardiff, Cork, Exeter, Norwich, Salford, Stoke, York | Oxford/Oxford City (SvS Oxford = Oxford United), Bangor City/Bangor (NIR), Eskilstuna City/AFC Eskilstuna | med + avvisningar |
| athletic | — | Charlton, Oldham, Scarborough | — | med |
| harriers | — | Kidderminster | — | med |
| forest, hotspur | — | inget par utöver poolaliasen Nottingham/Tottenham | — | UTE (inget belägg) |
| atletico | — | — | Albacete/Atletico Albacete, Las Palmas/Las Palmas Atletico (B-lag), Paris FC/Paris 13 Atletico | UTE (uppdraget) |

Även ute: sc (Barcelona ≠ Barcelona SC), rangers (Queens Park ≠ QPR),
wednesday (Sheffield), real, sporting och siffror/årtal (Paris 13).

## Offlinekontroll mot verkligheten

Skript och resultat under `/tmp/spk-audit/v5/` (se filförteckningen sist).
v4 = `git archive` av main `0ec4e72`, v5 = worktreen. Båda indexen gav
identiskt utfall.

| Omgång | v4 länkade | v5 länkade | Matcher |
|---|---:|---:|---:|
| Europatipset 2610 | 12 | 13 | 13 |
| Topptipset Extra 1869 | 8 | 8 | 8 |
| Topptipset 4349 | 6 | 8 | 8 |
| Topptipset 4350 | 5 | 8 | 8 |
| Stryktipset 4972 | 0 | 13 | 13 |
| Topptipset Stryk 982 | 0 | 8 | 8 |
| Topptipset 4351 | 5 | 8 | 8 |
| Topptipset 4352 | 7 | 8 | 8 |
| Topptipset 4353 | 8 | 8 | 8 |
| Topptipset 4354 | 3 | 3 | 8 |
| Topptipset 4355 | 7 | 8 | 8 |
| Topptipset 4356 | 1 | 1 | 8 |
| **Totalt** | **62** | **94** | **106** |

Unika matcher: 82. Oförändrade länkar 49 (alla nu nivå A), nya 21,
ändrade 0, förlorade 0. Inga länkar på nivå F i dag.

Nya länkar, alla med avstånd 0 min och samma id i båda indexen.
Rimlighet: power-devigat Pinnacle mot power-devigade SvS-odds.

| SvS-match (avspark UTC) | Pinnacle (id) | Nivå | SvS 1/X/2 | Pinnacle 1/X/2 | L1 | Samma favorit | Omgångar |
|---|---|---|---|---|---|---|---|
| Turkiet – Frankrike (25/9 18:45) | Turkiye – France (1636333025) | A | 0.14/0.19/0.67 | 0.12/0.19/0.69 | 0.042 | ja | Europa 2610, TT 4349 |
| Galway – Shelbourne (25/9 18:45) | Galway United – Shelbourne (1636875773) | B | 0.34/0.27/0.39 | 0.36/0.27/0.37 | 0.028 | ja | TT 4349 |
| Novorizontino – Sao Bernardo FC (25/9 22:30) | Gremio Novorizontino – Sao Bernardo (1637012425) | B | 0.60/0.23/0.17 | 0.62/0.23/0.15 | 0.036 | ja | TT 4350 |
| Once Caldas – Bucaramanga (26/9 01:15) | Once Caldas – Atletico Bucaramanga (1636734323) | A | 0.50/0.27/0.23 | 0.49/0.28/0.23 | 0.023 | ja | TT 4350 |
| Tijuana – Atlas (26/9 03:00) | Club Tijuana – Atlas (1636937860) | B | 0.48/0.27/0.26 | 0.47/0.27/0.25 | 0.013 | ja | TT 4350 |
| Cambridge – Wimbledon (26/9 14:00) | Cambridge United – AFC Wimbledon (1636963352) | B | 0.52/0.26/0.22 | 0.52/0.26/0.21 | 0.015 | ja | Stryk 4972, TT Stryk 982 |
| Plymouth – Burton (26/9 14:00) | Plymouth Argyle – Burton Albion (1636986820) | C | 0.64/0.21/0.15 | 0.61/0.21/0.17 | 0.061 | ja | Stryk 4972, TT Stryk 982 |
| Stockport – Peterborough (26/9 14:00) | Stockport County – Peterborough United (1637002824) | C | 0.69/0.18/0.13 | 0.72/0.16/0.12 | 0.065 | ja | Stryk 4972, TT Stryk 982 |
| Wycombe – Reading (26/9 14:00) | Wycombe Wanderers – Reading (1637002799) | B | 0.36/0.27/0.37 | 0.36/0.26/0.37 | 0.011 | ja | Stryk 4972, TT Stryk 982 |
| Cheltenham – Chesterfield (26/9 14:00) | Cheltenham Town – Chesterfield (1637086511) | B | 0.29/0.27/0.44 | 0.32/0.24/0.44 | 0.052 | ja | Stryk 4972, TT Stryk 982 |
| Fleetwood – Rochdale (26/9 14:00) | Fleetwood Town – Rochdale (1637080855) | B | 0.52/0.26/0.22 | 0.51/0.25/0.24 | 0.024 | ja | Stryk 4972, TT Stryk 982 |
| Newport – Grimsby (26/9 14:00) | Newport County – Grimsby Town (1637090724) | C | 0.24/0.26/0.50 | 0.21/0.25/0.54 | 0.080 | ja | Stryk 4972 |
| Rotherham – Crewe (26/9 14:00) | Rotherham United – Crewe Alexandra (1637086512) | C | 0.48/0.25/0.27 | 0.44/0.25/0.31 | 0.080 | ja | Stryk 4972 |
| Shrewsbury – Colchester (26/9 14:00) | Shrewsbury Town – Colchester United (1637080856) | C | 0.37/0.28/0.35 | 0.37/0.29/0.34 | 0.013 | ja | Stryk 4972 |
| Swindon – Accrington (26/9 14:00) | Swindon Town – Accrington Stanley (1637080857) | C | 0.44/0.28/0.28 | 0.43/0.26/0.32 | 0.071 | ja | Stryk 4972 |
| Tranmere – Walsall (26/9 14:00) | Tranmere Rovers – Walsall (1637086513) | B | 0.37/0.27/0.36 | 0.37/0.31/0.32 | 0.074 | ja | Stryk 4972 |
| England – Spanien (26/9 18:45) | England – Spain (1636346499) | A | 0.32/0.27/0.40 | 0.33/0.28/0.39 | 0.021 | ja | Stryk 4972, TT Stryk 982, TT 4351 |
| Tjeckien – Kroatien (26/9 18:45) | Czechia – Croatia (1636333033) | A | 0.28/0.26/0.46 | 0.28/0.27/0.45 | 0.024 | ja | Stryk 4972, TT Stryk 982, TT 4351 |
| Pereira – Internacional de Bogota. (26/9 21:00) | Deportivo Pereira – Inter Bogota (1636816733) | B | 0.27/0.29/0.45 | 0.29/0.27/0.43 | 0.052 | ja | TT 4351 |
| Nashville – Toronto FC (27/9 00:30) | Nashville SC – Toronto FC (1636866540) | A | 0.68/0.19/0.13 | 0.68/0.18/0.14 | 0.026 | ja | TT 4352 |
| Tjeckien – England (29/9 18:45) | Czechia – England (1636866906) | A | 0.14/0.22/0.64 | 0.13/0.20/0.67 | 0.054 | ja | TT 4355 |

Högsta L1 är 0,080; alla har samma favorit. Bland de oförändrade länkarna
har bara Nederländerna–Tyskland annan "favorit", och där skiljer 1 och 2
under 1 pp (L1 0,009).

**Fortfarande olänkade (12 unika):** nio landskamper som Pinnacle inte
listar i något av indexen (Japan–Venezuela, Sydkorea–Uruguay, Haiti–Costa
Rica, Surinam–Martinique, Jamaica–Honduras, St. Lucia–Bermuda, St. Kitts &
Nevis–Grenada, Guatemala–El Salvador, Australien–Brasilien — Pinnacle har
Australia–Brazil 25/9 10:00Z mot SvS 29/9 10:00Z, alltså olika datum; v4
länkade den inte heller) samt tre tvetydiga kortnamn utan alias:
Fortaleza–Deportes Tolima, America–Juventude och Deportivo Cali–Aguilas.

### Adversarial kontroll

`adversarial.py`, körd på båda indexen med samma utfall:

| Prov | v5 | v4 |
|---|---|---|
| Rätt rad borttagen, varje länkad SvS-match | 70 länkade, 0 fel | 49 länkade, 0 fel |
| — varav landskamper | 41 landskamper, 32 länkade, 0 fel; de 9 olistade länkar ingenting | — |
| Pinnacle-rad frågad med klubbformsorden bortstrippade (Plymouth Argyle → Plymouth) | 158: 147 rätt, 11 inget, 0 fel; rad borttagen: 0 fel | 158: 18 rätt, 140 inget, 0 fel; borttagen: 0 fel |
| Pinnacle-rad frågad med exakta namn, sedan borttagen | 930: 930 rätt; borttagen: 0 fel | 930: 916 rätt; borttagen: **8 fel** |
| Stresstest: rätt rad bort, alla övriga rader flyttade till SvS-avsparken | 70: 0 fel | 49: **2 fel** (Serbien–Grekland → Georgia–Greece, Skottland–Schweiz → Switzerland–Poland) |

Siffrorna gäller indexet 12:25Z; 14:12Z-indexet gav samma nollor för v5
(strip-provet 157 frågor, 147 rätt, 10 inget) och samma fel för v4.

De 11 "inget" i strip-provet är avsiktliga avslag: avvisade par
(Dundee, Oxford City, Club America, Club Guarani, Deportivo Morón),
landsnamn (Arab Emirates, Oman) och ord strippade mitt i namnet.

### Bomben

`bomben_check.py`: 39 Bomben-matcher (varav många hockey). v4 ger modell
för 13, varav en fel (Leksand–Almtuna → Sweden–Poland). v5 ger 15: samma
tolv korrekta plus Turkiet–Frankrike, England–Spanien och
Tjeckien–Kroatien, och inte Leksand. Befintliga Bomben-tester gröna.

### Historisk omspelning (kompletterande)

`hist_replay.py` spelar om alla 106 avslag i `pool_match_diagnostic` med
deras sparade sökledtrådar som pseudoindex. v5 länkar 31 fler, t.ex.
West Ham–Fulham (B), Puebla–Toluca (B), Ceará–Novorizontino (B),
Nashville–Chicago Fire (A), Pachuca–Tijuana (B), Wigan–Blackpool (B),
Gillingham–Cambridge (B), Oldham–Fleetwood (C). De 5 som v4 länkar men inte
v5 är England–Spanien och Turkiet–Frankrike: diagnostiktabellen saknar
isoCode, så v5 känner inte igen landslagen där; v4 länkade dem i
omspelningen bara för att pseudoindexet saknade den konkurrerande raden.
Live, med isoCode, länkar v5 båda på nivå A. Omspelningen saknar odds och
dåtidens hela index och är därför bara en ledtråd.

## Tester

- `backend/tests/test_pool_name_v5.py`, 23 nya tester: Plymouth–Burton
  (C, samma total), Cambridge–Wimbledon (B, spegling), klubbformsord och
  identitetsord, belagda olika klubbar, Dundee/Dundee United (annan och
  samma motståndare, derbyt), Inter/Inter Miami och Barcelona/Barcelona SC
  vid exakt motståndare och avspark, ankaret 15/16 min åt båda håll,
  kandidat utan avspark, v4-vägen utan SvS-avspark, två kandidater och två
  orienteringar på samma nivå ⇒ ambiguous, lägre nivå blockerar inte högre,
  England–Spanien med och utan rätt rad (även omärkt rad vid samma
  avspark), Turkiet–Frankrike med och utan rätt rad, Tjeckien–Kroatien,
  Real Madrid–PSG mot Spain–France, Vestmannaeyja–Valur, Leksand–Almtuna,
  igenkänning av landslag och avkortningar, landsnamn bara exakt, nya och
  medvetet uteslutna alias, Estudiantes, hörnrader, diagnostik till
  `pool_match_diagnostic`.
- Ändrade: `test_tackning_ae.test_flera_kandidater_avstar_oavsett_ordning_och_pris`
  (Inter–Lazio ett dygn senare gör inte längre rätt rad tvetydig; samma
  prov med kandidat 10 min bort och utan SvS-avspark behåller tvetydigheten)
  och `test_pool_names_4346` (versionssträngen v5, kontextaliaset = nivå A).
- `tools/kontroll.sh` i worktreen: backendtester (1 009), frontendlint och
  frontendtester gröna.

## Kvarvarande risker och avslag

1. **Nivå C saknar exakt ankare.** Delnamn på båda sidor blir fel om båda
   samtidigt pekar på andra klubbar vid samma avspark och rätt rad saknas
   (typfallet Oxford–Cambridge mot Oxford City–Cambridge City). Skydd:
   ankaret, tvetydighetsvakten och de belagda avvisningarna. Stresstestet
   gav 0 fel. Sex av dagens 21 nya länkar är C.
2. **Landslag som inte känns igen** (SvS utan isoCode, ny namnform) länkas
   inte längre via stavningslikhet mot Pinnacles landsnamn. Alla 57 i dag
   känns igen.
3. **Pinnacle-namn utanför kandidaterna** ger inget: Congo Republic (COG),
   framtida namnbyten. Konservativt, som v4.
4. **U21/dam:** Pinnacle listar U21 utan truppmarkör, så "Sverige U21"
   länkas aldrig (som v4). En omärkt U21-rad med samma två länder vid samma
   avspark som A-landskampen blir tvetydig, eller fel om A-raden saknas.
   SvS "Dam" är ingen truppmarkör i koden (oförändrat).
5. **Identiska normaliserade namn på olika klubbar** (t.ex. Athletic Club i
   Brasilien och Spanien) länkas exakt, som i v4; ankaret smalnar av risken.
6. **Bomben blandar sporter.** En hockeymatch med samma lagnamn som en
   fotbollsmatch vid samma avspark skulle länkas. Risken fanns i v4 med 36 h.
7. Aliaset `internacional de bogota` är belagt mot motståndaren via
   generiskt delnamn, inte exakt.
8. `_POOL_REJECTED_PARTS` blockerar också rätt kortnamn om SvS en dag
   menar den andra klubben (Oxford för Oxford City, Guarani för Club
   Guaraní, Moron för Deportivo Morón). Det ger missar, aldrig fel odds.
9. **v4-vägen** (okänd SvS-avspark) behåller enligt uppdraget v4:s
   svagheter: ISO-landsnamn även för klubbar och inget tidsfönster.
10. `match_tier` sparas inte (ingen schemaändring); kräver det
    efterhandsanalys behövs en migrering enligt DB-regeln.
11. En av 15 fulla körningar av backendsviten hade 1 fel som inte gick att
    återskapa (inte fångat; den körningen gick långsamt, 74 s mot normala
    49 s). De 14 övriga, inklusive `tools/kontroll.sh`, är gröna. Inget
    samband med matcharen är visat, men felet är inte heller identifierat.
12. Kontrollen täcker dagens 12 omgångar vid två indexögonblick. Nya länkar
    domineras av engelska League One/Two; Sydamerika och landskamper är få.
13. **Avsparksdrift.** En match där SvS och Pinnacle skiljer mer än 15 min
    (flyttad match, olika källdata) länkas inte längre; den syns i
    diagnostiken med `cand_start`. Inte observerat: i dagens två index har
    alla 70 länkar avstånd 0 min, och i `pool_match_diagnostic` sedan 14/9
    har alla 50 kandidater med exakt namn eller delnamn på båda sidor
    avstånd 0 min.

**Avstått:** unikhetsregel för nivå C över hela indexet (hade inte
skyddat Oxford–fallet, där Oxford United saknades i indexet); alias för
Aguilas, Fortaleza och America (tvetydiga; ett kontextalias à la
Estudiantes är möjligt per match); igenkänning av landslag utan isoCode
(uppdraget kräver landskoden); Dam → women; lagring av `match_tier`.

## Driftsättning, när Saman beslutat

Ren server → merge och ff-pull → starta om bara backend
(`tools/tjanster.sh omstart backend`); pooljobbet läser ny kod nästa tick.
Ingen migrering. Därefter: uppdatera STATUS i `docs/plan.md` och
poolmatcharens rad i `CLAUDE.md` (förslag nedan), lägg in
insamlingsnoterna nedan, och kör `scripts/pool_tackning_rapport.py
--sedan <driftdatum>` samt `adversarial.py` mot ett färskt index.

### Förslag: insamlingsnot i `docs/pool-ph4-forward-manifest-v3.json`

Nytt första element i `collection_notes` (datum = driftsättningsdagen):

```json
{"date": "2026-09-XX", "match_version": "pool-name-v5",
 "change": "Poolmatcharen med känd SvS-avspark prövar bara Pinnacle-kandidater inom 15 minuter (36 h gäller bara vägen utan SvS-avspark, som är v4 oförändrad, och diagnostiken). Nivåer bland behöriga kandidater: A exakt/alias båda sidor, B exakt/alias + generiskt delnamn, C generiskt delnamn båda, F stavningslikhet med oförändrade trösklar 0,60/0,72; bästa nivån vinner och flera på bästa nivån är ambiguous. Generiska delnamn enbart via prövade klubbformsord med belagda undantag. ISO-landsnamn enbart för landslag (SvS-namnet är landets svenska namn för isoCode, inklusive SvS avkortningar), och landsnamn matchas bara exakt. Tre belagda poolalias (Nashville, Bucaramanga, Internacional de Bogotá). Inga globala modellalias, trösklar, källor, presence-regler eller bakfyllningar ändras. Samma PIT-kontrakt inom insamlingsbeslutet 2026-09-14; särredovisa v4/v5-regimen vid skörd.",
 "expected_effect": "Fler giltiga Pinnacle-kopplingar: de öppna omgångarna 2026-09-24 gick från 62 till 94 av 106 matcher (Stryktipset 4972 från 0 till 13 av 13) utan ändrade eller förlorade länkar. Tvetydiga landskamper och engelska kortnamn kopplas. Kvar som avslag: olistade matcher och tvetydiga kortnamn (Aguilas, Fortaleza, America).",
 "doc": "docs/overlamningar/overlamning-2026-09-24-poolnamn-v5.md"}
```

### Förslag: datumnot i `docs/pool-pit-total-v1-2026-09-02.md`

Överst bland datumnoterna:

> **Datumnot 2026-09-XX, pool-name-v5:** poolmatcharen kräver med känd
> SvS-avspark en Pinnacle-avspark inom 15 min och väljer på nivå (exakt,
> exakt + generiskt delnamn, delnamn båda, stavning). Landslag känns igen på
> svenskt landsnamn och matchas bara exakt; klubbar får aldrig landsnamn.
> Total och 1X2 följer fortfarande samma match-id. Ingen ny oddskälla eller
> historisk bakfyllning; skilj v4/v5 vid skörd.
> Se `docs/overlamningar/overlamning-2026-09-24-poolnamn-v5.md`.

### Förslag: poolmatcharens rad i `CLAUDE.md` (arkitekturlistan)

> `app/odds_provider.py` NAMNREGELN för poolmatcharen (aktuell version i
> plan.md): med känd SvS-avspark bara kandidater inom 15 min; nivå A
> exakt/alias, B exakt + generiskt delnamn (klubbformsord, belagda undantag
> i `_POOL_REJECTED_PARTS`), C delnamn båda, F stavning 0,60/0,72; bästa
> nivån vinner, flera på den ⇒ `ambiguous`. ISO-landsnamn bara för landslag
> (svenskt landsnamn för isoCode), landsnamn bara exakt. SC bevaras
> (Barcelona ≠ Barcelona SC). Utan SvS-avspark gäller v4-vägen. Globala
> modellalias orörda.

## Filer

- Kod: `backend/app/odds_provider.py`, `backend/app/pinnacle.py`.
- Tester: `backend/tests/test_pool_name_v5.py` (ny),
  `backend/tests/test_tackning_ae.py`, `backend/tests/test_pool_names_4346.py`.
- Kontroll (serverns `/tmp/spk-audit/v5/`, utanför repot): `fetch_svs.py`,
  `fetch_pinnacle_once.py`, `classify.py`, `compare.py`, `adversarial.py`,
  `word_audit.py`, `bomben_check.py`, `hist_replay.py`, `hist_landslag.py`;
  resultat `svs_draws.json`, `pinnacle_index_fresh.json`, `cls_v{4,5}*.json`,
  `jamforelse_v4_v5.md`, `jamforelse_v4_v5_fresh.md`, `adv_v{4,5}*.json`,
  `word_audit*.json`, `bomben_v{4,5}*.json`, `hist_v{4,5}.json`,
  `unittest_run_*.log`. `v4root/` är `git archive` av `0ec4e72`.
