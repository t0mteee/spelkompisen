# Backlog — aktuell prioritering

**Skapad 2026-07-26, hardening-status uppdaterad 2026-08-01 — aktiv arbetslista
i "MODELLPLAN" längst ned; arbetsordningen där kräver Samans godkännande.**
Detta är projektets enda aktiva backlog. `docs/forbattringar.md` är arkiv (svs-ärvda lärdomar + bokkälls-
kartläggningen), WP-listan i `docs/plan.md` är historik över avslutat arbete.

Metodreglerna i `CLAUDE.md` (observationstid, ANKARE ≠ BOK, transportregeln,
signalversions-disciplin, källgränsen) gäller varje punkt nedan och upprepas
inte per rad.

## Hardening 2026-08-01 — levererat och driftverifierat

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
  namespacade spelar-id:n. V2.2 samlar under manifest v4 från 21:20Z; v3 fick
  0 captures och ersattes när matarligornas alias saknades i fingeravtrycket.
- **Drift:** säkra migrationsskript tog egna backuper och validerade radantal,
  schema, FK och integritet. Exakta produktionsantal finns i
  `docs/db-atgarder.md` och den aktuella överlämningen.

## A. Pågående mätningar — avgör sig själva, rör inte

Dessa kräver inget bygge, bara att serierna växer och utvärderas på sin
förregistrerade kadens. Att "hjälpa" dem i förtid är samma fel som sekventiell
testning.

| Mätning | Läge 2026-08-01 | Beslutspunkt |
|---|---|---|
| **Två ankare** (Pinnacle vs Smarkets, skugga) | 13 mätta, 9 mätta+stängda efter identitetssanering; ankarkrav behåller 3/9 | n ≥ 50 mätta+stängda 1X2 i primärgruppen, veckokadens — regel i `docs/tva-ankare-2026-07-25.md` (~7 dygn vid nuvarande takt) |
| **Modell mot close** (aktuell `model_version`) | modelldata v4 nollställer den jämförbara serien; exakta versions-id:n tas ur ledgern | grind i `docs/modell-mot-close-2026-07-25.md`; close-scriptet väljer exakt aktuell version och historik blandas aldrig |
| **Hörnbaslinje** (aktuell modell + `corner-poisson-total-v1`) | börjar om under modelldata v4; hörnprovider redovisas separat från xG | samma close-grind, sist i ordningen (Samans ordning 2026-07-25) |
| **pit-v4 forward** (`pool-streckmove-v3`) | 4 omgångar | ≥ 40 out-of-time-omgångar per produkt med hela KI90 < 0 |
| **Sharp-CLV-facitet** | historiskt aggregat +2,3 % [1,1..3,4], 272 stängda efter sanering; ny aktiv `s-95e14fca` börjar från nästa capture | veckokadens (`EVAL_INTERVAL_H`), aldrig per varv; grönt beslutas per liga × marknad × version |
| **V2.2 flerliga-shadow v4** | ren samling från 2026-08-01T21:20Z under manifest v4; v1/v2 historik och v3 0 captures | träningsgate 300 kompletta avgjorda/horisont, ≥ 50/liga, ≥ 42 dagar |
| **Live-radar tre källor v4** (shadow) | ren kohort från 2026-08-01T21:00Z; v3 är ogiltig pilot, v2/v3 endast historik | prediktiv lyft: separat momentgate; blind Över-ROI: första aktiva signal/match, ≥200 oddssatta+avgjorda, ≥60 dagar och undre KI90 > 0 — `docs/live-radar-2026-07-25.md` |

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

## MODELLPLAN 2026-07-28 (odds + pool) — aktiv arbetslista

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
- **Nästa V2.2-omfrysning efter manifest v4**: låt först v4 samla orört.
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
