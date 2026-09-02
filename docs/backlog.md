# Backlog — aktuell prioritering

**Skapad 2026-07-26, uppdaterad 2026-09-02 — aktiv arbetslista i avsnittet
Aktivt direkt nedan; allt under det är levererat eller historik.
Arbetsordningen kräver Samans godkännande.**
Detta är projektets enda aktiva backlog. `docs/forbattringar.md` är arkiv (svs-ärvda lärdomar + bokkälls-
kartläggningen), den gamla WP-listan ligger i `docs/status-historik.md` som historik över avslutat arbete.

Metodreglerna i `CLAUDE.md` (observationstid, ANKARE ≠ BOK, transportregeln,
signalversions-disciplin, källgränsen) gäller varje punkt nedan och upprepas
inte per rad.

## Aktivt (2026-09-02)

Ur granskningen 2026-09-02 (Claude, mot `origin/main` = servern), i
prioritetsordning. ⚖ = kräver Samans beslut.

1. ✅ (2026-09-02) **Tystnadsvarningar i UI:t** (beslut 2026-09-02: UI räcker, ingen ntfy).
   `/api/health` ska larma när en källa inte körts på N varv, när senaste
   snapshot är äldre än 2 h och när en produkt saknar samlad omgång; Idag
   visar det. Historiken motiverar det: Topptipset Dagens tyst i fem dygn
   (2026-08-04→09), AWS-DNS 302 varv utan att någon såg.
2. ✅ (2026-09-02) **Tester för `bomben`, `steam`, `clv`, `derive`** — användarsynliga och
   helt otestade (0 testfiler refererar dem).
3. ✅ (2026-09-02) **`cli.py gater`** — varje förregistrerad gate (V2.2, PH5 forward,
   maxtester, poolstyrka, radarblindtest, pooloptimerare) med n/krav/datum på
   ETT ställe. Skörda före nästa nya spår.
4. ✅ (2026-09-02, första skivan: Oddset/lib/components) **Frontend-utbrytning** — `OddsetView` (1 364 rader), `LabbV3` (989),
   `HistorikV3` (723) till egna kataloger med ren logik i `.js` som
   `node --test` når; 13 frontendtester täcker i dag bara `playRec.js` och
   `sourceHealth.js`. Koordineras med Codex, som är aktiv i `App.jsx`.
5. ✅ (2026-09-02) **CLAUDE.md halveras** — berättelsen bakom varje regel flyttas till
   länkade dokument; reglerna står kvar ordagrant.
6. **Skörd av pågående mätningar** — `cli.py gater` 2026-09-02: **PH4 pit-v4
   Topptipset 79/40 har passerat out-of-time-kravet** (Stryk/Europa 6–11/40);
   sharp-CLV MLS + Allsvenskan gröna, Conference League 1X2 ej stöd (n=89).
   **PH4 skördad 2026-09-02** (`scripts/ph4_ablationer.py`, första körningen
   sedan manifest v3 frystes 25/7): Topptipset 48 forward-omgångar, kandidat d
   (Pinnacle + streck + streckrörelse) Δlogloss **+0,0128** mot ren Pinnacle,
   KI90 [−0,005, +0,030] — inte bättre, snarare sämre; även ren omkalibrering
   (b*) +0,0085. **Promotion: NEJ.** Streckrörelse tillför inget utöver
   marknadspriset vid h3. Caveat: c/d/f rapporterar `converged_folds 0/48`
   inom manifestets 800 iterationer — en omprövning av konvergensen kräver nytt
   manifest, aldrig en ändring i v3. Övriga produkter 5–11/40. Beslut: Saman.
   Utbrytningen klar 2026-09-02: AppV3 3 823 → 1 164 rader (`src/historik/`,
   `src/labb/`, `lib/api.js`, `lib/labels.js`, `components/badges.jsx`).
   ✅ **Bokfört 2026-09-02 kväll:** PH4 Topptipset promotion NEJ; MODELLPLAN:ens
   augustidatum är passerade och ersätts av listan nedan (ingen skörd förlorad —
   V2.2, PH5, maxtester och poolstyrka läses via `cli.py gater`).
7. ✅ (2026-09-02) **Chansmotorn exakt** — klotunion i stället för Monte Carlo;
   `0 %` var ett samplingsartefakt (`_round_chance` bevarar ≥ 3 värdesiffror).
   Kvar: chansen är CPU-bunden i en synkron endpoint; varje match utan livepris
   tredubblar arbetet — mät med `chance_unpriced` innan du optimerar.
8. ✅ (2026-09-02) **Pooloptimerare v1 fullsökning** — 10 000 konf., 2 006 omg.
   Ingen arm slog Standard på ROI i slutauditen (402 omg); träff-armen +3
   träffar med KI90 [0; +0,017]. Tre armar fryses framåt som research-familj
   `poolopt` (Topptipset 4309/Stryk 979/Extra 1864→). Grind 40 parade omg;
   avslut 120. `docs/poolopt-v1-forward-2026-09-02.md`. **Nästa version (v2,
   512 rader, X-risk v1 som champion) startas INTE förrän forward har 40.**
9. ✅ (2026-09-02) **Sannolikhetsbas** — EV-byggaren rankar på SvS-odds men
   väljer kandidater på Pinnacle. `prob_base` infört (standard byte-identisk);
   PH3-utmanare `dr1-b256-medel-sharp` i Topptipset-familjen. Retro på pit-v4:
   identiskt facit på 77 omg; radval skiljer i 17 (h3) / 54 (m20) omg. Fynd:
   Pinnacle täcker Topptipset vid h3 i bara 18/87 omg, m20 56/88 — **frågan om
   Topptipsets h3-frysning ska flyttas närmare avspark är ny och obesvarad**
   (⚖ PH3:s horisonter är förregistrerade; ändring = ny generation).
10. ✅ (2026-09-02) **pit-total-v1** — Pinnacles huvudtotal fryst vid
   h24/h3/m20 som syskonserie (pit-v4 orörd). Skörd vid ≥ 40 Topptipsomgångar
   med total på alla åtta: bär totalen P(X) utöver X-priset? Först då vet vi om
   X-skyddet är en riskregel eller en modell. Lägg grinden i `cli.py gater` när
   första raden finns (byggs av `pool-tick`).
11. ✅ (2026-09-02) **jackpot_close** i settlementlagret (9 omgångar bakfyllda
   ur egna snapshots; `docs/db-atgarder.md`). Historik → Prognosträff visar
   prognos mot utfall per jackpotomgång. Prognosen är jackpotblind tills
   `JACKPOT_MODEL_MIN_N` = 30/produkt — ⚖ då: rullande backtest mot den
   jackpotblinda medianen, aldrig fri kurvanpassning.
12. **Öppet efter kvällen:** (a) Topptipsets h3-täckning från Pinnacle (punkt 9)
   — mät om m20 ska bli PH3:s primära horisont för 8-matchsspelen innan nästa
   generation; (b) `chance`-endpointen till en bakgrundsberäkning om Historik
   fortfarande upplevs långsam; (c) `cli.py gater` saknar pit-total-grinden
   tills första raden finns.
13. ✅ (2026-09-02) **Championship i Oddset och live.** Verifierade
    provideridentiteter hos Pinnacle/Kambi/Ninja/Smarkets/Flashscore/FotMob,
    fullt synlig och actionable liga samt ren radarkohort v12 från
    2026-09-02T22:00Z. Football-data `E1` fortsätter ge resultat;
    `MODEL_LEAGUES` och V2.2 är avsiktligt orörda tills separat täckningsaudit
    och kalibrering finns. Följ upp första riktiga liveomgången med
    `cli.py lanklucka`; se `docs/radar-scope-v12-2026-09-02.md`.

## 2026-08-11 — AWS korrekt omtestat och avfärdat

- **❌ AWS Lightsail Stockholm är avfärdat.** En ny adress (`51.20.96.34`)
  testades med rätt endpoint-uppsättning: Svenskaspel, Pinnacle, Kambi,
  Flashscore, FotMob och Altenar fungerade, men samtliga åtta Sofascore-
  modellvägar gav 403. Inget 72-timmarstest behövs. Detta är stark evidens
  mot AWS Stockholm, inte ett bevis mot varje annan leverantör eller region.
  Full rapport och rålogg finns i `docs/serverfragan-avslutad-2026-08-11.md`
  och `docs/kalltest-bevis/`.
- **✅ Båda AWS-instanserna avvecklade 2026-08-12.** Saman raderade dem i
  Lightsail-konsolen; inget AWS-beroende finns kvar i drift. Mätdatan i
  `docs/kalltest-bevis/` behålls som evidens. Nästa serverfråga börjar i så
  fall med ett engångsprov hos en annan leverantör, aldrig ett nytt
  flerdygnstest på AWS.
- **✅ Testverktyget är härdat.** `kalltest_ip.py` provar nu åtta verkliga
  Sofascore-modellvägar separat från live, märker varje körning med `run_id`
  och skiljer både httpx- och curl_cffi-DNS-fel från källfel. Det sparade
  AWS-underlaget visar 302 hela körningar med totalt DNS-bortfall, inte en
  källa som lyckades sporadiskt. Nästa steg är ett engångsprov på en ny billig
  instans; endast `sofa_model 8/8` motiverar ett 72-timmarstest. Flashscore-
  kontrollen skiljer nu också en giltig tom statistikfeed från transportfel.

## 2026-08-10 — prestandapaket levererat

- **✅ Direktvägen Idag → Oddset har fri kapacitet.** Dashboardens controller
  fanns redan, men synkrona backendjobb fortsatte efter klientens abort. Idag
  startar därför inget nätarbete de första 650 ms och sekundära kort väntar
  1200 ms; timers och requests rensas vid vybyte. Byggd mobilvy på ordinarie
  5175 gick från 2472 till 619 ms till första Oddset-lista. Idags första
  poolkort är fortsatt 953 ms. Modellcachens basfit är immutable mellan
  requests och jackpotpayloaden är single-flight vid kall samtidig start.
- **✅ Byggd bundle är nu normalläget.** `start.sh` och launch-konfigurationen
  `frontend` bygger/serverar port 5175. Vite/StrictMode-dev ligger separat på
  5181 som `frontend-dev`.

## 2026-08-10 — senast levererat

- **✅ Poolens lagstyrka mäts nu säkert mot Pinnacle.** Ett isolerat
  forwardspår fryser h24/h3/m20 för 90/10 Pinnacle/lagstyrka, med 80/20 och
  ren modell som diagnostik. Aktuell säsong väger mest genom modellens
  kontinuerliga 240-dagars e-folding (cirka 166 dagars halveringstid).
  Bortfall sparas lika synligt som lyckade länkar; inga gamla sannolikheter
  fylls i och inga poolsystem påverkas. Följ under Historik → Poolmodell.
  Förregistrering: `docs/pool-strength-forward-manifest-v1.json`.
- **✅ xG-luckor återhämtade och räknaren förtydligad.** 83 xG-par
  bakfylldes säkert i Allsvenskan, Superettan, OBOS och MLS utan att en enda
  match lades till eller skrevs om. Allsvenskan 2026 är nu 125/125. Tomma
  lyckade statistik-svar återförsöks i stället för att spärras permanent,
  äldre säsongssidor nås och exakt kanonnamn vinner före alias. Alla andra
  aktuella modellligor kontrollerades; fyra färska matcher saknar xG hos både
  Sofascore och Flashscore och lämnas ärligt saknade. Lagstyrka skiljer nu
  `Spelade` från `Med xG`. Modellens datakontrakt är v5 och V2.2 samlar rent
  under manifest v7.

## 2026-08-09 — tidigare levererat

- **✅ Autopool-historiken visar hela underlaget och rätt omgångsdatum.**
  Dagens 78 frysta förslag fanns i ledgern; de såg ut att saknas eftersom
  "Alla konfigurationer" i praktiken var en global ROI-topp-20 som kunde
  dölja hela produkter. Alla 132 grupper visas nu från start, med frivillig
  topp-20-komprimering. En sorterbar `Datum`-kolumn visar senaste kupongdatum
  per grupp och tabellen öppnas med nyaste datum först. UI:t skiljer automatiskt
  sparade förslag från kuponger
  som användaren markerat som spelade, och båda visar omgångens spelstoppsdatum
  redan före settlement genom fallback till öppna `draws`-raden.
- **✅ Europatipsets tvåtimmarsfördröjning rättad.** Omgång 2597 var
  finaliserad med publicerad utdelning men visades som väntande. Senaste
  matchens `19:15+02` hade formaterats direkt med `Z`, så omprövningen blev
  21:25Z i stället för korrekta 19:25Z. `_retry_after` konverterar nu till UTC
  före serialisering och har ett explicit sommartidstest. Omgången settlades
  genom ordinarie kod: den spelade kupongen fick 10 rätt och 126 kr.
- **✅ Bolivia + verifierat Island + ren livekohort v9.** Bolivias Primera
  División är synlig/actionable med verifierade identiteter hos Pinnacle,
  Smarkets, Sofascore, Flashscore och FotMob. Kambis giltiga landsväg är tom
  i aktuellt SvS-utbud men fångar automatiskt framtida event. Besta deild
  fanns redan i ordinarie vy/Flashscore, men FotMobs aktuella namn
  `Besta deildin` saknades och är nu explicit mappat; Sofascore UT 188 ligger
  också explicit i radarscopet. Ingen
  av ligorna läggs i målmodellen eller V2.2. Scopeändringen startar rent som
  `chance-gap-shadow-v9` 2026-08-09T18:00Z; trösklarna är oförändrade
  (`docs/radar-scope-v9-2026-08-09.md`).
- **✅ Tre nya toppligor + ren livekohort v8.** Danska Superliga, belgiska
  Pro League och Primeira Liga är verifierade mot aktuella Pinnacle-, Kambi-,
  Smarkets-, Flashscore-, FotMob- och Sofascore-identiteter. De är synliga
  sharp-ligor och resultat settlas, men de ligger utanför MODEL_LEAGUES och
  V2.2 tills separat historik/kalibrering finns. Livepopulationen ändras och
  startar därför rent som `chance-gap-shadow-v8` 2026-08-09T17:15Z; inga
  signaltrösklar ändrades (`docs/radar-scope-v8-2026-08-09.md`).
- **✅ Larm när en poolprodukt slutar samlas.** Topptipset Dagens var TYST utan
  insamling i fem dygn (scanhintet mot kodens statiska seed — se
  `docs/overlamningar/overlamning-2026-08-09.md` punkt 5). `pool_health` kontrollerar nu
  slutartefakterna i stället för att lita på att rätt funktion anropades:
  snapshot per öppen omgång, färskhetskadens, komplett PH3-familj efter
  horisonten, scanhint som ligger bakom och passerad settlement-retry. Syns i
  Idag, `/api/health` och `cli.py kallhalsa`; rent läsande, inga nätanrop.
- **✅ Per-omgångsvärden i panelstate.** Jackpotläckan mellan produkter
  (punkt 3 i överlämningen) var ett `useState` utan omgångsnycklad
  återställning. Nu ogiltigförklaras sena analys-/rörelse-/pott-svar och
  pottdata används bara när både produkt OCH draw_number matchar. Skyddet
  omfattar rubrik, spelvärde, byggare, systemvy och kupong — inte bara
  jackpotfältet.
- **✅ Livekällor och träningsmatcher.** UI/diagnoser läser livekällistan ur
  backend (`flashscore`, `fotmob`). Ensidig friendly-länkning har eget
  15-minutersfönster och faller stängt på saknad/trasig tid.

## Nästa verifiering/arbete

- Förregistrera en ny radarversion om de tre verifierade isländska
  liveidentiteterna (`ÍA`, `Gardabae`, `FH`) ska länkas till Oddset. Statsen
  visas redan, men signaljournalen faller korrekt stängt utan kanoniskt pris;
  ändra aldrig identiteten inne i v9-kohorten.
- Verifiera settlementens nya kadens på första omgång som finaliseras efter
  2026-08-09: SvS-publicering → lokalt facit bör vara högst cirka 15 minuter.
- Utöka det lilla frontend-testskelettet med komponent-/browsernivå när UI:t
  växer. `npm test` låser nu sen-svar-grinden, produkt+omgångsidentiteten och
  källhälsans grönt/partial/stale-semantik utan nya beroenden.
- Nästa metodändring av PH3-familjen ska skapa en namngiven generation i
  stället för att radera/dölja armar i samma familj.

## Historisk hardening 2026-08-01 — levererat, ersatt av statusen ovan

- **Live v4:** `chance-gap-shadow-v4` börjar rent 21:00Z. v3-fönstret
  08:00–21:00Z är ogiltig historisk pilot och får aldrig ge stöd. Tre separata
  provider-serier/presence/health, ≤12 min färskhet, unik start-/lagidentitet,
  strukturell täckningsrankning och exakt minut-/ställnings-/statsproveniens.
  Flashscore/FotMob har capture v2 och score/stats-koherensvakter. Malformed
  tomma svar kan inte tömma presence och partiella detaljfel visas aldrig
  gröna.
- **Livefacit:** provider-id är TEXT, äldre råformat settlas men hålls isär
  och versionen bestäms av capturetid. Momentfacitet använder råproviderns
  egen klocka/ställning; signaljournalens facit behåller exakt den eventuellt
  lånade minut/ställning som användes i den synliga signalen. Close-drift
  väljer och joinar en exakt sharp-version.
- **Modelldata v4:** resultatskelett och providerstatistik är separata;
  football-data vinner atomiskt som normaltidsfacit, xG/hörnor väljs som två
  separata hela providerpar och frånvaro lagras per provider/status med
  namespacade spelar-id:n. V2.2 samlar under manifest **v5** från 2026-08-07T11:05Z; v3 fick
  0 captures och ersattes när matarligornas alias saknades i fingeravtrycket,
  och v4 (12 rader/2 avgjorda) ersattes när Europaligornas lagnamnsalias
  utökades inför xG-bakfyllningen.
- **Drift:** säkra migrationsskript tog egna backuper och validerade radantal,
  schema, FK och integritet. Exakta produktionsantal finns i
  `docs/db-atgarder.md` och den aktuella överlämningen.

## A. Pågående mätningar — avgör sig själva, rör inte

Dessa kräver inget bygge, bara att serierna växer och utvärderas på sin
förregistrerade kadens. Att "hjälpa" dem i förtid är samma fel som sekventiell
testning.

| Mätning | Läge 2026-08-01 | Beslutspunkt |
|---|---|---|
| **Två ankare** | AVFÖRD som aktiv väg: Smarkets hade 56 030 1X2-priser men noll AH/ÖU/hörnor och får inte vara spelbar bok/ankare | Historik i `docs/tva-ankare-2026-07-25.md`; `ANCHOR_SOURCES`-spärren står kvar |
| **Modell mot close** (aktuell `model_version`) | aktuell modellsignal `m-e900ed90`; V2.2 samlar isolerat under manifest v6 | grind i `docs/modell-mot-close-2026-07-25.md`; historiska versioner blandas aldrig |
| **Hörnbaslinje** (aktuell modell + `corner-poisson-total-v1`) | providerpar separeras från xG; fortsatt amber tills samma close-grind håller | samma close-grind, sist i ordningen (Samans ordning 2026-07-25) |
| **pit-v4 forward** (`pool-streckmove-v3`) | 4 omgångar | ≥ 40 out-of-time-omgångar per produkt med hela KI90 < 0 |
| **Sharp-CLV-facitet** | historiskt aggregat +2,3 % [1,1..3,4], 272 stängda efter sanering; ny aktiv `s-95e14fca` börjar från nästa capture | veckokadens (`EVAL_INTERVAL_H`), aldrig per varv; grönt beslutas per liga × marknad × version |
| **V2.2 flerliga-shadow v6** | ren samling från 2026-08-07T14:20Z; v4 12/2 och v5 1/0 är stängda historiska kohorter | träningsgate 300 kompletta avgjorda/horisont, ≥ 50/liga, ≥ 42 dagar |
| **Live-radar två källor v9** (shadow) | Flashscore ankare + FotMob; Sofascore urkopplad. 18-ligorsscope, v9 rent från 2026-08-09T18:00Z | prediktiv lyft separat; blind Över-ROI ≥200 oddssatta+avgjorda, ≥60 dagar och undre KI90 > 0 — `docs/live-radar-2026-07-25.md` |

## B. Fixar ur granskningen 2026-07-26 — ✅ GENOMFÖRDA samma dag (godkända)

Alla fem åtgärdade + en driftbugg (F5c) hittad under arbetet: capture-
valideringen krävde `finished` och hade fällt hela WP9c-insamlingen från
~16:26 när TTL:n släppte — fångad innan dess, rotationsriskdatat flödar nu
för första gången. wp9c-POLICY schema 4 → f22-bump → dåvarande V2.2-manifest
v2 enligt dess egen change_policy (ersatt av manifest v3 och därefter v4
2026-08-01).
292 tester gröna (14 nya regressionsfall).
Detaljer: `docs/db-atgarder.md` (2026-07-26) + STATUS i plan.md.

- **F1 — Bok-ÖU-spökpris** *(litet)*: `oddset.py` ~608 saknar else-gren; när
  matchen finns i Altenar-listsvaret men ÖU-marknaden är plockad markeras det
  gamla ÖU-priset aldrig `unavailable` → draget pris kan flaggas/CLV-loggas i
  upp till 45 min. Hörnvägen gör rätt — spegla mönstret.
- **F2 — SvS-deep bryter observationstidsregeln p.3** *(litet, förelåg före
  passet)*: Kambi-deep sparas med varvstarten `at` (`oddset.py` ~536), inte
  per-anropstid — upp till ~25 min feldatering i en lång ligaloop.
- **F3 — "kvar"-etiketten läser inga Age-huvuden** *(medel)*: bokssidans
  (Kambi/Altenar) `last_seen_at` sätts av anropstid utan cache-huvuden, så ett
  CDN-cachat svar kan "återbekräfta" ett pris efter sharpflytten. Villkoret i
  `oddset_value.py` är rätt byggt och etiketten är display-only — men läs Age
  där huvuden finns, annars tona ned claimen i UI/docs.
- **F4 — Spelade kuponger settlar mot fel källa** *(litet-medel; fixa FÖRE
  första bokförda kupong)*: `pool_played` tar tecken ur draw-payloadens
  `Current`-score positionsvis (sparad `events_order` används aldrig, tyst
  trunkering vid breddskillnad) och räknar struken match som rätt för alla
  rader — medan settlement-kanon (`pool_settlement`) har officiellt
  `outcome`/`cancelled` per event. Settla mot kanon, joina på eventNumber,
  hård breddvakt.
- **F5 — Rotationsrisk: PIT-hål + tyst v22-payloadändring** *(litet-medel)*:
  (a) upserten skriver över `start_at` vid ombokning så
  `oddset_sofa_team_fixtures_as_of` läser dagens tid för historiska `as_of` —
  bevara först-sedd starttid eller capture-historik; (b) `oddset_schedule.POLICY`/
  `feature_version` bumpades inte trots ny insamlingssemantik och nya fält i
  wp9c-payloaden — rader före/efter är versionsidentiska utan att vara
  jämförbara (modellfeatures skyddas av whitelist, inget spelbart ändrat).
  Version + rad i `docs/db-atgarder.md`.

## C. Byggbart nu — kandidater att satsa på

Ordnade efter mitt förslag, inte beslutade.

1. ~~**PH3-settlementaudit**~~ ✅ 2026-07-26: maskineriet håller (30/30
   oberoende omräknade — dist, utspädning, komplett-flaggor), alla timely.
   Rollover-vägen oprövad av skarp data; ROI:erna är brus vid n=5 och citeras
   inte. `docs/ph3-settlementaudit-2026-07-26.md`. KVAR: förregistrera en
   PH3-gate innan ledgern får läsas som bevis.

2. ~~**Devig-ablation**~~ ✅ 2026-07-26: förregistrerad + körd
   (`docs/devig-ablation-2026-07-26.md`). Konsensusflaggor +4,40 %
   [+2,54..+6,14] mot bara-power −0,49 % [−3,50..+2,45] — devig-tvetydighet
   är en äkta filtersignal; facitet är inte en devig-artefakt. Eventuellt
   konsensusfilter tas ihop med två ankare-gatens signal_version-bump.

2b. ~~**Beslutspaket konsensus-gaten**~~ ✅ 2026-07-26:
   `backend/scripts/tva_ankare_beslut.py` kör den förregistrerade
   veckoutvärderingen + devigkonsensus + coverage-kostnad i en läsning.
   Läge: SAMLAR (8/50 mätta+stängda i primärgruppen, ~8 dygn kvar).
   Tidig varning: ankarkravet behåller bara 25 % av kohortens flaggor —
   coverage-kostnaden måste vägas i beslutet.

2c. ~~**PH3-gate förregistrerad**~~ ✅ 2026-07-26:
   `docs/ph3-gate-2026-07-26.md` — n ≥ 40 omgångar, ≥ 60 dagars spann,
   winsoriserad KI > 0, veckokadens; armarna frysta.

2d. ~~**startOdds-semantiken verifierad — UPPLÅST**~~ ✅ 2026-07-26:
   `docs/startodds-semantik-2026-07-26.md` — öppningsodds med tidiga
   revisioner (23 %, median 4 % in i fönstret), därefter fryst; inte
   stängning, trackar inte. Får användas som omgångs-kovariat i
   final_only-analyser (8 278 omgångar), ALDRIG som PIT-observation
   (ingen tidsstämpel).

3. ~~**PH5 v2 vid 256/512 rader**~~ ✅ KÖRD 2026-07-26
   (`docs/ph5-radvalsablation-256-512-2026-07-26.md`): underskottet är
   täthetsberoende (krymper monotont: −8,2 → −5,0 → −2,3 pp mot slump för
   Stryk) men INGEN spelbar budget vänder det — vid 512 rader är metoden i
   bästa fall likvärdig folk-/favoritrad och toppträffarna hamnar hos de
   naiva raderna (2 mot 7/7). Konsekvens: ärlig byggartext för
   Stryk/Europa (levereras i v3-konsolideringen). Ev. gles-täcknings-metod
   (Hamming-spridning) är en egen förregistrerad framtida fråga.

3b. ~~**close-drift-facit v1**~~ ✅ KÖRD 2026-07-26
   (`docs/close-drift-facit-2026-07-26.md`): ingen prediktor passerar gaten —
   momentum FALSIFIERAD h24→h3 och signifikant åt motsatt håll för AH/Ö/U
   (tidiga skift reverserar). Ingen 🔮-radar byggs på detta. **v2-FÖRSLAG
   (kräver godkännande):** förregistrera (a) reverseringshypotesen på NY
   kohort, (b) linjeflytt-som-drift för parmarknaderna (~500 exkluderade
   linjebyten ÄR driften), (c) frånvaro med större fönster.
3c. ~~**close-drift-facit v2**~~ ✅ FÖRREGISTRERAD + FÖRSTA KÖRNING
   2026-07-26 (`docs/close-drift-facit-v2-2026-07-26.md`,
   `scripts/close_drift_facit_v2.py`, veckokadens):
   **(b) Ö/U-LINJEFLYTTAR REVERSERAR** — fortsättningsandel 23,6 %
   [15,3..31,9] (tvåsidigt förregistrerat ⇒ äkta fynd; AH neutral).
   Konsistent med v1:s prisreversering: Pinnacles tidiga Ö/U-rörelser
   överreagerar. (a) reversering forward: SAMLAR (0/100, kohort från
   2026-07-26T21Z). (c) frånvaro brett fönster: ingen signal (n=26),
   utforskande. FÖRE tips krävs: forward-replikering + pris-EV-storlek +
   vanliga trappan. Egen-modell-spåret fortsätter bara i sina gated banor
   (V2.2, hörnbaslinjen).
   **Hardening 2026-08-01:** både v1/v2-scriptet väljer en exakt
   `signal_version` (default aktuell sharp-version). Nycklar och
   linjeflyttsjoin innehåller versionen, så en ny modellversion aldrig kan
   paras med en historisk rad.
   Förregistrerad nästa körning: avgör om 13-matchs-underkännandet är
   budgetberoende (→ täthets-varning i byggar-UI:t) eller strukturellt
   (→ ärlig text: värderad-metoden är fel verktyg för Stryk/Europa).
   Per-omgångs-ROI ligger redan i `docs/ph5-radvalsablation-v2-2026-07-25.json`.

4. ~~**Radar-settlement**~~ ✅ BYGGT (app/live_settlement.py + tester +
   migrering; settlar i `_live_pass` efter varje varv). Kompletterat 31/7 med
   `app/live_signal_ledger.py`: första faktiska Följer/Stark-beslutet, live
   Ö/U, slutresultat och en fryst blind-ROI-gate. Facitet mognar
   ~mitten av augusti enligt A-tabellens gate. Push kräver därefter nytt
   uttryckligt beslut av Saman.

5. ~~**Matchbook som tredje referens**~~ ✅ BYGGD I SKUGGA 2026-07-27
   (Samans "kör backloggen"): öppen publik väg bekräftad (inga konton/
   sessioner — källgränsen hålls), `app/matchbook.py` + likviditetstabell,
   insamling ENBART i 3h-snabbfönstret, sex ligor mappade (MLS/EU-research
   omappade tills url-name observerats). Aldrig i BOOKS/ankare; ny
   SHADOW_SOURCES-spärr i värdemotorn. ≥ 28 dagars ren skugga enligt
   kallplanen innan någon användning föreslås. Ursprungstext:**
   Arbetspaket + acceptans i `docs/bookmaker-kallplan-2026-07-25.md` (börs,
   öppnar sent, likviditet nära avspark; endast shadow ≥ 28 dagar).
   Rekommendation: bygg EFTER två ankare-beslutet — annars bygger vi ankare
   nr 3 innan vi vet om nr 2 ändrar något.

6. ~~**Docs-hygien: komprimera STATUS-loggen**~~ ✅ 2026-07-27: 249 rader
   avslutade milstolpar (2026-07-13→24) flyttade till GAMMAL STATUS under
   egen rubrik; STATUS bär nu bara aktuellt läge + senaste dygnens poster.

7. ~~**v3-KONSOLIDERINGEN**~~ ✅ KLAR 2026-07-26 (alla fyra stegen samma
   dag på Samans order): Labb-vyn, klickbara värdekort, PH5-byggartext,
   default-byte OCH v2-vyn RIVEN (−412 rader; App.jsx = komponentbibliotek).
   Dessutom: spelläge-pillret (spela/spela smått/avstå) i Poolspel + Idag,
   🎟 Dina kuponger-kort med livestatus på Idag, personligt kupongfacit
   (PlayedPanel) överst i Historik. Småpunkterna stängda 2026-07-27:
   rek-historik i matchdetaljen (📒-sektion via /api/oddset/match-flags),
   Bomben-spelläge (rullpott-styrd pill) OCH Samans rek-per-match: "Rek"-
   kolumn i Oddset-vyn för följda ligor (ej träningsmatcher/research) med
   delade oddsetBestValue/oddsetValueTier så 💰-kort, Idag och Rek aldrig
   glider isär; "avstå" när inget kvalar. Ursprungsplanen:**
   *(medel-stor; UI-spårens svar på spretigheten)*
   Diagnosen stämmer: två UI:n (v2 default + v3-experimentet) och mätspår
   utspridda över paneler. Plan, i ordning:
   1. **Städregel omedelbart:** nya ytor byggs BARA i v3; v2 är
      underhållsfryst (buggfixar ja, paneler nej).
   2. **Ny vy i v3: 🧪 Labb** — samlar ALLA mät-/shadow-spår på ETT ställe:
      signal-facit per grupp, två ankare-/beslutspaketets läge (SAMLAR n/50),
      modell-mot-close, devigkonsensus, live-radar + radar-facit,
      PH3-ledger med gate-status, pit-v4-läge, kommande 🔮-driftradar.
      Tydlig märkning: mätning ≠ tips — Labb är bevisytan, Idag/Oddset/
      Poolspel är beslutsytan, Historik är facityta.
   3. **Tips-klasserna i Oddset-vyn** (delad komponent): 💰 utstick
      (actionable) + 🔮 drift (shadow tills close-drift-facitet bär).
   4. **Default-byte till v3** när Labb landat och Saman kört v3 skarpt en
      spelhelg utan att sakna något — därefter rivningsbeslut för v2
      (aldrig före; mobilflödena sitter i muskelminnet).

### Småpunkter (efter Besta deild-passet 2026-07-27)

- **Förkortningsalias i oddsmatchningen**: Kambis "ÍB Vestmennaeyjar" och
  Pinnacles "IBV" mergar inte (en dubblettrad 1/8). Lös via explicit
  aliaslista för odds-resolven — ALDRIG via sänkt fuzzy-tröskel
  (identitetssaneringens läxa). Liten.
- **Island → SOFA_UT** (xG/frånvaro/WP9c) vid nästa naturliga
  V2.2-omfrysning; Matchbook-slug för Island när den observerats.

## D. Väntar på Saman — beslut eller handling

- **NTFY-återaktivering** — pausad på egen begäran 2026-07-16. Notisvakten +
  källhälsan finns nu; utan pushar tävlar systemet inte i latens mot manuell
  inspektion. Säg till så slås den på (eget topic, inte svs:s).
- **🎟 Spelade kuponger** — funktionen finns sedan 2026-07-25 men 0 kuponger
  bokförda. Vänta med första bokföringen tills F4 är fixad; börja sedan
  bokföra vid varje riktig inlämning så det egna facitet får data.
- **bwin-test från eget nät** — `curl` mot CDS-endpointen; 403 härifrån är
  WAF. Svarar den 200 hos dig är klienten trivial — men bwin är inte
  svensklicensierat, så det är också ett policybeslut.
- **Servermigrering** (Pi 5 / N100, launchd → systemd) — öppet sedan tidigare;
  checklista utlovad när beslutet tas.
- **🎯 "Bara signaler" som mobil-default** — produktbeslut, öppet sedan v3-passet.
- **Bomben-filrubrik** — overifierad (inloggningsskyddad spec); verifiera vid
  nästa skarpa uppladdning.

## E. Parkerat / avfört — med skäl (ta inte upp utan ny anledning)

- **Betsson** — header-löst men events-table är CloudFront-403 utanför browser;
  ingen session-replay (källgränsen). Omprövas bara om en cookie-fri väg dyker upp.
- **Coolbet** (Imperva), **bet365/Betano** (botskydd) — stängda enligt källgränsen.
- **Flashscore är INTE parkerad längre** — 2026-07-25-domen upphävdes när en
  publik pipe-feed/persisted query verifierades. Källan är i drift för live
  och framåtriktad modelldata sedan 2026-08-01. **Opta** är fortsatt avfört:
  gratisvägen är renderade bilder, feeds kräver betald outlet-nyckel.
- **Fler Kambi-/Altenar-skins** — samma prisfeed, noll ny information
  (uppmätt 2026-07-24). Expekt kvar bara som diff-visning.
- **X-bias-korrigering** — backtest v4 (2026-07-16): ingen X-korrigering. Avfört.
- **Opening-line-ankare** — ledgerns T−24h-horisont täcker frågan;
  Pinnacle-opening är uttryckligen avvisad ur q-facitet. Avfört.
- **Polymarket som extra sharp** — tunn klubbtäckning; Smarkets löste behovet.
- **ClubElo-vy för poolspelen** — Elo finns PIT för Oddset-modellen; pool-sidan
  mäts via pit-v4-features i stället.
- **V2.1-modellen** — vilande; kräver ny hypotes + nytt fryst outer-manifest.
- **startOdds-semantik** — rått sparad men SPÄRRAD för analys tills verifierad.
- **Altenar-altlinor** — kräver book-lager som bär flera linor utan att blanda
  tecken; bygg först vid konkret behov.
- **Idélista, låg prio** (gamla svs-punkter, giltiga men oprioriterade):
  diversifiering i Värderader (Hamming-straff), multinivå-Kelly, andelsspel,
  "din rad vs folkets"-överlapp, Måltipset (pid 8), veckodagsviktad
  omsättningsprognos.

## MODELLPLAN 2026-07-28 (odds + pool) — arbetslista (datumen ersatta 2026-09-02)

**2026-09-02:** beslutsdatumen nedan (augusti) är passerade. Det som skördats
står i **Aktivt** punkt 6–11; det som fortfarande samlar läses via
`cli.py gater`. Planen behålls som historik över VARFÖR spåren startades.

**Samans beställning 2026-07-28: "vad mer bör vi köra för att förbättra
modellerna (odds, pool)?" Ersätter det gamla Förslag-avsnittet (alla dess
punkter ✅ ovan).** Grundprincip oförändrad: förregistrerade gater, aldrig
sekventiell testning, marknadspriser äger facitet.

### Spår 1 — Skörda pågående mätningar (ingen kod; beslutspunkter i ordning)

Detta är den billigaste modellförbättringen som finns: mätningarna är redan
byggda och betalda — de behöver bara läsas på sin kadens och omsättas i
beslut. Uppskattade beslutsdatum:

1. **Två ankare-gaten** (~första augustiveckan): kör
   `scripts/tva_ankare_beslut.py` veckovis. Vid grönt: konsensusfilter
   (devig-ablationens +4,40 % [+2,54..+6,14] mot bara-power −0,49 %) ihop
   med signal_version-bump — EN bump, inte två. Väg coverage-kostnaden
   (ankarkravet behöll bara 25 % av flaggorna vid första mätningen).
2. **Close-drift v2 (a)** — forward-replikering av Ö/U-linjeflytts-
   reverseringen (23,6 % [15,3..31,9] fortsättningsandel; kohort samlar
   sedan 26/7): vid replikering → förregistrera pris-EV-storlek → trappan.
   Först därefter ev. 🔮-tips. Detta är närmaste kandidaten till en HELT NY
   signalklass sedan sharp-CLV.
3. **Radar-settlementets facit** (~mitten av augusti): xG-signal vs proxy
   villkorat liga × minut × ställning. Grönt → beslut om liveflagga (Samans
   explicita beslut; shadow tills dess).
4. **V2.2 forwarddom**: research-ligorna har premiärer 15/8; gaten (300
   kompletta/horisont, ≥ 50/liga, ≥ 42 dagar) avgör om egen modell någonsin
   får actionability. Passivt — rör inte.
5. **pit-v4** (pool, ≥ 40 out-of-time-omgångar/produkt) och **PH3-gaten**
   (n ≥ 40, ≥ 60 dagars spann): passiva, veckoläsning i Labb räcker.

### Spår 2 — Byggbart nu, ordnat efter modellutdelning per timme

**P1. Kappa-kalibrering av medvinnarmodellen** *(pool; medel; störst
   modellvinst)*. `pool_mc.simulate_pool_portfolio` har medvinnar-
   kalibreringen `kappa` men runtime kör okalibrerat 1,00 ("tills ett
   oberoende tidsfönster motiverar annat" — det fönstret finns nu:
   Historikfacit 697 Stryk / 1 371 Europa / 4 154 Topp med full utdelning).
   Förregistrera: skatta kappa per produkt genom att jämföra oberoende-
   antagandets utdelningsprognos (fält × P_folk) mot faktisk utdelning per
   vinstnivå; out-of-time-split (träna ≤ 2024, validera 2025–26); KI per
   produkt. Folk spelar korrelerade rader — EV-per-rad är idag systematiskt
   fel åt optimistiska hållet för folkrader och pessimistiska för skräll.
   Runtime-kappa byts BARA efter out-of-time-validering + Samans beslut.

**P2. Resultatväg för icke-football-data-ligor** *(odds; medel;
   facitlucka)*. `refresh_results` läser bara football-data-CSV:erna —
   cupernas nya flaggor, Besta deild, MLS och friendlies får CLV-mot-close
   men ALDRIG ROI-facit (BH-FDR-grupperna kan aldrig settla). Bygg
   resultatinsamling via Sofascore-event (resultat är facit, ingen
   PIT-fråga; källan används redan) med Kambi settled som rimlighetskoll.
   Besta deild: prova football-datas new/ISL-fil först. Acceptans: cup-/
   bestadeild-/mls-flaggor settlar i Signal-facit; inga modellhärledda
   källor i facitet.

**P3. Förkortningsalias i odds-resolven** *(odds; liten; växande behov)*.
   IBV-fallet + cupernas ~100 nya klubbnamn över fyra källor gör explicit
   aliaslista akutare än när punkten skrevs. ALDRIG sänkt fuzzy-tröskel
   (identitetssaneringens läxa).

**P4. Veckodagsviktad omsättningsprognos** *(pool; liten)*. Dagens
   `_projected_turnover`-median per produkt missar veckodags-/jackpoteffekt;
   EV-per-rad ärver felet linjärt. Median per produkt × spelstoppsveckodag
   × jackpotläge ur Historikfacit; redovisa prognos-mot-utfall i Labb.
   Komplement till P1 — båda sitter i samma EV-formel.

**P5. PH5:s förregistrerade uppföljning** *(pool; liten; redan definierad)*.
   Avgör om 13-matchs-underkännandet är budgetberoende (→ täthetsvarning i
   byggar-UI) eller strukturellt (→ ärlig byggartext). Därefter, som egen
   förregistrerad fråga: gles täckning via Hamming-spridning.

**P6. Kalibreringsläsning per liga × marknad i Labb** *(odds; liten)*.
   `oddsetcalibrate` finns som CLI — sätt den på veckokadens i Labb så
   power-devigens k följs per liga. Cuperna är nya prismiljöer (annan
   overround, tvåbenta möten) och Besta deild har tunn likviditet — fel
   devig-form där äter edge-marginalen tyst.

### Spår 3 — Väntar på beslut eller kalender

- **NTFY-återaktivering** (Samans D-punkt): utan pushar tävlar close-drift-
  och steamfynden aldrig i latens. Rekommenderas ihop med Spår 1.2-beslutet.
- **Nästa V2.2-omfrysning efter manifest v5**: låt först v5 samla orört.
  Ta senare in Island OCH ev. cuperna i SOFA_UT/xG/frånvaro i EN framtida
  omfrysning (inte tre); det kräver ett nytt manifest och ny shadow-version.
- **Rotationsrisk/frånvaro som flaggfilter**: wp9c-serien flödar sedan
  26/7 (F5c) — förregistrera filterfrågan när serien har ~6 veckors volym
  (≈ början av september).
- **September, ligafasstart**: verifiera Kambi-/Smarkets-/FotMob-
  huvudslugs för cuperna (mönsterhärledda idag, kommenterade i koden).
- **Servermigrering** (Pi 5/N100): egen checklista när beslutet tas.

### Arbetsordningen KÖRD 2026-07-28 (Samans "kör samtliga i ordning")

- **P1 ✅** — men som KONSISTENSFIX, inte ny skattning: mätningen fanns
  redan (PH4, 7 754 omgångar); det trasiga var att portföljsimuleringen
  körde κ=1,00 medan radvalet var κ-korrigerat. `kappa_by_tier` in i
  pool_mc + /api/system. `docs/kappa-kalibrering-2026-07-28.md`.
- **P2 ✅** — OMFORMULERAD efter kartläggning: Signal-facit settlar på
  close-EV, ingen outcome-kolumn fanns alls. Nu: outcome i value_log,
  resolve_outcomes (1X2, modellspårets join), resultat-ROI som display,
  RESULT_ONLY_UT (cuper/bestadeild/friendlies via Sofascore, normaltid,
  inga statistik-anrop; SOFA_UT orörd). Skarpt: 370 resultat, 176
  settlade — resultat-ROI −1,6 % mot close-EV +2,5 % (n lågt, brus).
- **P3 ✅** — TEAM_ALIASES i norm_team (IBV-fallet). DB-skanningen fann
  även SPEGELPAR i odds-flödet (Pau–Espanyol m.fl.) → egen designpunkt:
  merge kräver teckenspegling av oddsen. EJ byggd — kräver design.
- **P4 ✅** — veckodagsviktad prognos ur lokala settlementlagret (0
  nätverksanrop; Europatipset to 7,36 M mot blandade 4,33 M).
  Jackpotdimension utelämnad: settlementlagret saknar jackpotkolumn.
- **P5 🔄** — 256/512-körningen var redan gjord (26/7). Den öppna frågan
  (Hamming-spridning) FÖRREGISTRERAD (`docs/ph5-hamming-forregistrering-
  2026-07-28.md`) + arm inlagd; fullkörning pågår.
- **P6 ✅ (omskopad)** — utfalls-ROI + 🌡-kalibrering i Signal-loggen,
  prognosgrund som tooltip. `oddsetcalibrate` på veckokadens återstår
  som driftbeslut (CLI:n gör nätverksbacktest).

## 2026-08-12 — spelfamiljer, Idag-vyn och två sorters "aldrig spelad"

- **✅ Topptipset är ETT spel överallt.** Historik (`?family=1`),
  championrapporten, Autopools konfigurationstabell, spelade kuponger och
  Idag-korten går på `svenskaspel.family_of()`. Championens underlag gick från
  tre rader med 4/2/1 parade omgångar till en med 7. Variantetiketterna
  (Dagens/Stryk/Extra) är borta ur UI:t. Produktslug, settlementidentitet och
  `config_key` är oförändrade.
- **✅ Inställd omgång skiljs från saknad data.** 56 av 8 324 omgångar bar
  `cancelled: true` på resultatet men `Finalized` i `drawState` och lagrades
  som avgjorda med saknade utfall. Migrerade efter verifiering mot källan.
- **✅ `statusId 23` är "Uppskjuten", inte förlängning.** Den gissade serien
  20–25 gjorde en aldrig spelad match till avgjord. Bara observerade koder får
  ligga i statusmängder; klartexten är skyddsnätet.
- **✅ Idag-vyn ombyggd** — spelstopp per rad i spelstoppsordning, bredare
  värde-/rörelselistor med devigade Pinnacle-odds och oddsskift, dolda
  forskningsligor, summerat system- och signalfacit, dagsfärskt historikfacit.
- **✅ Spelläge-etiketten bär avståndet** till nästa tröskel i stället för att
  upprepa en konstant (`frontend/src/playRec.js`).
- **✅ ⚓/andra ankaret borttaget ur UI:t.** Mätningen och spärren i
  `ANCHOR_SOURCES` är orörda.

### Öppet efter 2026-08-12

- **Topptipset 4259 m20 frystes aldrig**, men omgången ställdes in och är
  därför ingen förlorad modellobservation. Schedulerhändelsen är bara värd att
  utreda som driftspår, inte som ett prioriterat datahål.

### Codex-granskning 2026-08-12

- **✅ Inställda omgångar påverkar inte längre facitstatistik.** De bevaras i
  direktarkivet men räknas inte som settlade omgångar, rullpotter, omsättning
  eller toppvinster. Topptipsets familj gick från 58 skenbara rollovers till
  5 verkliga. Systemledgern särredovisar dem som `n_cancelled`.
- **✅ Familjefiltret gäller även Poolmodell.** Topptipset inkluderar alla tre
  slugs och samma match dedupliceras över kuponger.
- **✅ Obelagt förlängningstecken faller stängt.** Rader och chans visas som
  ett öppet spann tills ordinarie resultat är belagt; Current-score får inte
  presenteras som poolfacit.
- **✅ UI-/identitetshärdning.** Prognosgrunden visas läsbart och historikens
  detaljcache nycklas på produkt + omgång. 691 backendtester, 12
  frontendtester och produktionsbygget är gröna.
- **✅ V2.2:s nollinsamling hittad.** V7 hade 4/4 rader underkända eftersom
  manifestet bar sharp-basversionen där prediction-ledgerns sammansatta
  signalversion skulle stå. V8 börjar rent med rätt versionspar; de fyra
  ogiltiga v7-raderna lämnas orörda som diagnostisk historik. Ny manifest-
  identitet ger enligt kontraktet featureversion `f22-d6baf69c`.
- **✅ Automatisk V2.2-kontraktsvakt.** `/api/health` faller nu från grönt om
  manifestets fyra versioner inte matchar runtime, om en aktuell capture får
  `source_version_changed`, eller om fem rader samlats utan en enda eligible.
  Idag-vyn visar orsaken; menyns befintliga datastatus blir röd.
