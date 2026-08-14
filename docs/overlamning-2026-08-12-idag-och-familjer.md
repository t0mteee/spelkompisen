# Överlämning 2026-08-12 — Idag-vyn, spelfamiljer och två sorters "aldrig spelad"

Läs `docs/plan.md` STATUS-block först. Detta är dagens arbete i detalj.

## 1. Spelfamiljer: Topptipset är ETT spel

Topptipset Dagens/Stryk/Extra är samma spel hos Svenska Spel — åtta matcher,
samma vinstplan (70 %), samma benchmarkfamilj — bara tre omgångsserier med
egna nummer och egna produkt-slugs (pid 25/23/24).

**`svenskaspel.family_of(product)`** är enda källan till grupperingen och
läser `GAME_GROUPS`. Skriv aldrig en parallell lista; frontendens `FAMILY` i
`App.jsx` speglar samma regel.

Sammanslaget:

- **`/api/pool/history?family=1`** expanderar produkten via `GAME_GROUPS`.
  Statistiken (median toppvinst, rullfrekvens, medelomsättning) räknas över
  hela familjen i backend, så den förblir ETT estimand. Varje omgångsrad bär
  sin egen `product` — utan det pekar detaljuppslaget `?draw=1856` på
  `topptipset` i stället för `topptipsetextra` och hittar ingenting.
- **Listan sorteras kronologiskt**, inte på `draw_number`. Familjen har tre
  oberoende nummerserier; dessutom lovade sparkline-etiketten redan
  "äldst → nyast", vilket bara stämmer om ordningen är tidsbaserad.
  `draw_number` är tiebreak — omgångar kan dela stängningstid.
- **`champion_report()` grupperar på FAMILJ.** Pareringen sker på
  `(produkt, omgång)` i `_paired_draw_roi`, så de tre nummerserierna inte kan
  blandas ihop. Utmanarfamiljen är snittet av medlemmarnas `benchmarks_for`,
  som skydd om en framtida grupp skulle blanda spelformer. Effekt: Topptipset
  gick från tre rader med 4/2/1 parade omgångar till **en rad med 7** per
  horisont. Att mäta dem var för sig delade underlaget i tre och gjorde varje
  del för tunn för grinden.
- **Autopools konfigurationstabell** slår ihop rader som skiljer sig bara i
  produkt. Pengar summeras och ROI räknas om ur summorna, aldrig som medel av
  gruppernas ROI, och bara där en sammanslagning faktiskt skedde.
- **Spelade kuponger** filtrerar på familj i stället för exakt slug.
- **Variantetiketterna är borta ur UI:t** (Samans beslut 2026-08-12):
  Topptipset är Topptipset, inte Dagens/Stryk/Extra. Omgångsnumret skiljer dem
  åt där det behövs, och omgångsväljaren i Poolspel är fortsatt entydig
  (`stänger 08-13 18:59 · omg 1857`). `VARIANT` finns kvar i `App.jsx` men
  används inte längre för visning.

**Oförändrat:** produktslug, settlementidentitet, `config_key`,
`benchmarks_for(product)` och alla API-anrop. Detta är en gruppering av vad
som MÄTS ihop och VISAS ihop, inte en omdöpning av identiteter.

## 2. Två saker som aldrig spelas — och såg ut som något annat

### Inställd omgång (Topptipset 4259)

SvS sätter `cancelled: true` på **resultatet** men lämnar `drawState` på
`Finalized`, varje event utan utfall och en distribution med noll vinnare och
0,00 kr. Settlementet läste bara `drawState`, så omgången lagrades som avgjord
med åtta saknade utfall och systemledgern dömde den "utfall saknas för minst
en match".

`settle_draw` skriver nu `draw_state='Cancelled'` (`CANCELLED_STATE`) ur
resultatet, och ledgern skiljer `cancelled` från `unresolvable` i sin rapport:
**en inställd omgång är inte en misslyckad mätning, den är ingen mätning alls.**

Migrering: 56 av 8 324 omgångar, alla Topptipset, 2024-05-08 → 2026-08-10.
Varje kandidat verifierades mot SvS innan skrivning (56 bekräftade, 0
avvisade). Se `docs/db-atgarder.md` 2026-08-12.

### Uppskjuten match (Topptipset 4261)

**`statusId 23` betyder "Uppskjuten", inte en övertidsperiod.** Koden låg i den
GISSADE serien 20–25 i `EXTRA_TIME_STATUS_IDS`. Följden var att
`regulation_over()` blev sann för en match som aldrig spelats: kupongen
redovisade den som avgjord och tecknet lästes ur ett resultat som inte fanns.

Bara 20 ("Första övertidsperioden") är observerad, så serien krymper till den.
**Skyddsnätet mot okända övertidskoder ligger i klartexten** SvS levererar
bredvid koden (`EXTRA_TIME_STATUS_WORDS`) — inte i gissade nummer. Samma
princip gäller framåt: lägg aldrig in en statuskod i en mängd innan den
observerats.

`match_postponed()` är en egen fråga, matchen exponeras som `postponed` till
UI:t, och settlementets omprövning hoppar över den — en uppskjuten match blir
aldrig färdigspelad och dess `matchStart` kan flyttas veckor fram.

SvS lottar fram ett tecken för en struken match, men **först vid finalisering**.
Fram till dess är tecknet okänt och kupongen håller matchen öppen.

## 3. Idag-vyn ombyggd

- **Nästa spelstopp:** en box per rad i spelstoppsordning (inte produktordning).
  Visar omsatt hittills med prognosen som spelvärdet räknas mot.
- **Toppraden** har explicita kolumnbredder (0,85/1,15/1,15) i stället för
  auto-fit, så värde- och rörelselistorna får plats.
- **Värdespel:** fem rader, sorterade på KVALITET (Kelly-andel) — det stod
  ingenstans förut, så ordningen såg slumpmässig ut. Visar
  `svenskaspel 1.55 mot Pinnacle 1.48 devigad`, alltså priset edgen faktiskt
  räknas mot (1/fair), inte Pinnacles noterade kvot.
- **Rörelser:** `Pinnacle 3.10 → 2.31 på 24 h` plus det andra fönstret i pp.
  `steam` och `value.fair` mäter samma storhet, så oddsskiftet härleds utan ny
  insamling. Det andra fönstret avgör om rörelsen PÅGÅR eller avstannat.
- **Forskningsligor** renderas bara när en liga faktiskt är märkt research.
- **Signal-facit** kokat till en statusrad; bara grupper som bytt läge får rad.
- **Systemfacit** summerat per produkt, deterministisk ordning, horisonter i
  minuter. ROI döljs under `ROI_MIN_N` (=10) — en rättad omgång gav +898 %.
- **Historikfacit** visar senast settlade omgång med toppvinst i stället för
  ett arkivantal som aldrig ändras.

## 4. Spelläge-etiketten (`PlayRec`)

Spelvärdet är `payout_ratio` (konstant per produkt: 0,598/0,637/0,700) plus
jackpot delat med omsättningen. Alla tre konstanterna ligger under
tunt-tröskeln 0,80, så **utan jackpot är "avstå" aritmetiskt tvunget** — inte
en bedömning av raderna. Etiketten bär därför avståndet till nästa tröskel
(`omgången: avstå · tunt vid +2,5 Mkr`), räknat mot samma omsättningsbas som
spelvärdet. Räknandet ligger i `frontend/src/playRec.js` med egna tester.

## 5. Övrigt

- **⚓ borta ur hela UI:t** (nivån "OMTVISTAD EDGE", markeringar, CSS). Smarkets
  kopplades bort som andra ankare 2026-08-07. Mätningen fortsätter i skugga och
  spärren i `ANCHOR_SOURCES` står kvar — den är en säkerhetsspärr, inte en
  visning.
- **Emojier med textpresentation** (`🎟 🏋 ⚠ ℹ`) saknade `U+FE0F` och
  renderades som monokrom glyf eller tom ruta. 21 tecken rättade. `↔` i
  `App.css` står i en kommentar och lämnades som textpil.
- **Git:** `origin` är nu SSH (`git@github.com:t0mteee/spelkompisen.git`) med
  nyckel på MacBook-servern; repo-lokal identitet `Saman
  <saman@MacBook-Pro-SERVER.local>`. Pushar fungerar även från
  icke-interaktiva sessioner.
- **Båda AWS-instanserna är avvecklade** 2026-08-12.

## Öppet

- **Draw 4261** väntar på sin sista match (GKS Katowice–Hapoel Tel Aviv,
  avspark 2026-08-12 16:00Z) och på att SvS lottar tecknet för den uppskjutna
  D. Tolima–Independiente.
- **Topptipset 4259 m20 frystes aldrig**, men omgången ställdes in och är
  därför ingen förlorad modellobservation. Utred bara schedulerhändelsen om
  driftspåret behöver granskas; den ska inte prioriteras som ett datahål.

## Codex-granskning 2026-08-12

Hela sviten, produktionsdatabasen och mobilvyn granskades. Följande luckor i
det nya familje-/inställt-kontraktet rättades:

- inställda omgångar finns kvar i direktarkivet men exkluderas ur historikens
  antal, omsättning, toppvinst och rolloverfrekvens;
- systemledgern redovisar dem som `n_cancelled`, inte `n_unresolvable`;
- Poolmodellens Topptipsfilter expanderar till alla tre familjeprodukter och
  deduplicerar samma match över kuponger;
- ett obelagt tecken under förlängning hålls öppet i rad- och chansräkningen
  tills ordinarie resultat verkligen hämtats;
- prognosgrunden renderas som text i stället för `[object Object]`, och
  historikens detaljcache använder produkt + omgång som identitet.
- V2.2 v7 samlade noll användbara rader: dess manifest jämförde ledgerns
  sammansatta sharp-version mot sharpens basversion. V8 är en ren kohort med
  rätt versioner (`s-2f14f9a6` / `s-ccdfecc0`) och manifestbunden
  featureversion `f22-d6baf69c`; v7:s fyra ogiltiga rader lämnas som historik.

Migreringsskriptets framtida backup använder SQLite onlinebackup, så DB och
WAL inte kan kopieras i olika ögonblick.

Verifiering: 691 backendtester, 12 frontendtester och produktionsbygget är
gröna. Före rättningen gav produktionslagret Topptipset-familjen 58
rollovers; rätt population (inställda exkluderade) ger 5.

### Automatisk V2.2-vakt (Codex, samma dag)

`oddset_v22.health()` jämför aktiva manifestets fyra frysta identiteter mot
runtime: sammansatt sharp-signalversion, sharp-basversion, V2.2-modellversion
och featureversion. Därmed blir ett versionsfel synligt i `/api/health`
**innan första capture**. Vakten larmar också om någon aktuell rad bär
`*_source_version_changed`, samt om minst fem rader samlats men noll är
eligible av andra orsaker.

`/api/health.status` blir `degraded`, menyn visar att datastatus kräver
tillsyn och Idag-vyn skriver den konkreta V2.2-orsaken. Kontrollen är helt
lokal och rent läsande. V8 verifierades efter driftsättning som `ok` med alla
fyra versioner lika och 0/0 nystartade rader; nästa riktiga horisontcapture är
första dataprov.

## Oddslistan på mobil 2026-08-14

Tre ändringar i Oddset-flikens Matcher-lista, alla i frontend.

**1X2-rutorna ligger tre i bredd.** `.movement-cell` (pp-talet) delade
`order: 3` med de tre `.oc`-cellerna i mobilkortets flexrad och åt ~90 px, så
bara två av tre 28 %-rutor fick plats och `2` hamnade ensam på egen rad.
Pp-talet ligger nu på lagraden (`order: 2`, `margin-left: auto`) och
oddsrutorna har raden under för sig själva. Verifierat: alla tre `.oc` har
samma `offsetTop`.

**Bokens `–`-platshållare är borta på mobil.** AH, Ö/U och HÖRNOR ritade alltid
ut en rad med `–` ovanför Pinnacles linje. `cellPair` sätter nu `noquote` på
bokraden när priset saknas och `noprice` på hela cellen när varken bok eller
sharp har något; mobilblocket döljer dem. **Desktoptabellen är oförändrad** —
där behövs `–` för kolumnjusteringen (verifierat: 19 `.noquote` synliga vid
1280 px, 0 vid 375 px).

**Nytt filter "Dölj utan odds", PÅ som standard.** Se CLAUDE.md för kontraktet.
Kort: 28 av 190 matcher saknade pris hos alla spelbara böcker. Samans
invändning — Pinnacle är ju också en bok man kan spela hos, och CLV-logiken
säger att man ska spela tidigt — är principiellt rätt, men uppmätt tar
Pinnacle **11,53 % median 1X2-marginal på just de 28** mot **5,56 % på de
132** som har bokpris. Det är matcher ingen bok vill prissätta skarpt, och
edgen skulle behöva överstiga overrounden; uppmätt closing-drift är 0,3–0,6 pp.

Filtret är rent visuellt, och det verifierades i drift snarare än antogs:
insamlingsvarvet bekräftade priser för Segesta Sisak, Haro Deportivo och
Alcoyano kl. 08:39:59Z — fem minuter efter att de försvunnit ur listan. De
syns dessutom kvar under Rörelser med filtret påslaget, vilket är regeln:
en match utan bokpris kan inte bära en värdeflagga (värde kräver bokpris mot
sharp) men kan bära en Pinnacle-rörelse.
