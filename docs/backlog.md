# Backlog — aktuell prioritering

**Skapad 2026-07-26 (Fable 5). UTKAST — prioriteringen under "Förslag" kräver
Samans godkännande innan arbete startar.** Detta är projektets enda aktiva
backlog. `docs/forbattringar.md` är arkiv (svs-ärvda lärdomar + bokkälls-
kartläggningen), WP-listan i `docs/plan.md` är historik över avslutat arbete.

Metodreglerna i `CLAUDE.md` (observationstid, ANKARE ≠ BOK, transportregeln,
signalversions-disciplin, källgränsen) gäller varje punkt nedan och upprepas
inte per rad.

## A. Pågående mätningar — avgör sig själva, rör inte

Dessa kräver inget bygge, bara att serierna växer och utvärderas på sin
förregistrerade kadens. Att "hjälpa" dem i förtid är samma fel som sekventiell
testning.

| Mätning | Läge 2026-07-26 | Beslutspunkt |
|---|---|---|
| **Två ankare** (Pinnacle vs Smarkets, skugga) | 13 mätta, 9 mätta+stängda efter identitetssanering; ankarkrav behåller 3/9 | n ≥ 50 mätta+stängda 1X2 i primärgruppen, veckokadens — regel i `docs/tva-ankare-2026-07-25.md` (~7 dygn vid nuvarande takt) |
| **Modell mot close** `m-c4ee7c5d` | ny aktiv version, 0 cases tills nästa capturefönster; `m-3c7789ac` historisk efter DATA_VERSION 3 | grind i `docs/modell-mot-close-2026-07-25.md`; äldre versioner blandas aldrig över identitetsfixen |
| **Hörnbaslinje** `m-c4ee7c5d:corner-poisson-total-v1` | ny aktiv version, fryser från nästa horisont | samma close-grind, sist i ordningen (Samans ordning 2026-07-25) |
| **pit-v4 forward** (`pool-streckmove-v3`) | 4 omgångar | ≥ 40 out-of-time-omgångar per produkt med hela KI90 < 0 |
| **Sharp-CLV-facitet** | historiskt aggregat +2,3 % [1,1..3,4], 272 stängda efter sanering; ny aktiv `s-95e14fca` börjar från nästa capture | veckokadens (`EVAL_INTERVAL_H`), aldrig per varv; grönt beslutas per liga × marknad × version |
| **V2.2 flerliga-shadow** | samlar | träningsgate 300 kompletta avgjorda/horisont, ≥ 50/liga, ≥ 42 dagar |
| **Live-radar + FotMob** (shadow) | samlar sedan 2026-07-25 | ≥ 200 signalögonblick och ≥ 40 avslutade matcher per signaltyp, ≥ 28 dagar — `docs/live-radar-2026-07-25.md` |

## B. Fixar ur granskningen 2026-07-26 — ✅ GENOMFÖRDA samma dag (godkända)

Alla fem åtgärdade + en driftbugg (F5c) hittad under arbetet: capture-
valideringen krävde `finished` och hade fällt hela WP9c-insamlingen från
~16:26 när TTL:n släppte — fångad innan dess, rotationsriskdatat flödar nu
för första gången. wp9c-POLICY schema 4 → f22-bump → nytt V2.2-manifest v2
enligt dess egen change_policy. 292 tester gröna (14 nya regressionsfall).
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
   Förregistrerad nästa körning: avgör om 13-matchs-underkännandet är
   budgetberoende (→ täthets-varning i byggar-UI:t) eller strukturellt
   (→ ärlig text: värderad-metoden är fel verktyg för Stryk/Europa).
   Per-omgångs-ROI ligger redan i `docs/ph5-radvalsablation-v2-2026-07-25.json`.

4. **Radar-settlement** *(medel; bygga nu, facit mognar ~mitten av augusti)*
   Settla radarsignaler mot de två förregistrerade utfallen (mål inom 15 min /
   ytterligare mål före full tid) villkorat liga × minut × ställning, separata
   facit för xG- och proxy-signal. Steg 2–3 i `docs/live-radar-2026-07-25.md`.
   Push kräver därefter nytt uttryckligt beslut av Saman.

5. **Matchbook som tredje ankare/reservankare** *(medel-stor)*
   Arbetspaket + acceptans i `docs/bookmaker-kallplan-2026-07-25.md` (börs,
   öppnar sent, likviditet nära avspark; endast shadow ≥ 28 dagar).
   Rekommendation: bygg EFTER två ankare-beslutet — annars bygger vi ankare
   nr 3 innan vi vet om nr 2 ändrar något.

6. **Docs-hygien: komprimera STATUS-loggen i plan.md** *(liten)*
   STATUS-sammanfattningen är > 500 rader logg; flytta daterade poster äldre än
   2026-07-24 till GAMMAL STATUS och behåll en kort lägesbild + pekare hit.
   (Faktafel i källtabell/portar rättade 2026-07-26; resten är omflyttning.)

7. ~~**v3-KONSOLIDERINGEN**~~ ✅ KLAR 2026-07-26 (alla fyra stegen samma
   dag på Samans order): Labb-vyn, klickbara värdekort, PH5-byggartext,
   default-byte OCH v2-vyn RIVEN (−412 rader; App.jsx = komponentbibliotek).
   Dessutom: spelläge-pillret (spela/spela smått/avstå) i Poolspel + Idag,
   🎟 Dina kuponger-kort med livestatus på Idag, personligt kupongfacit
   (PlayedPanel) överst i Historik. KVAR SOM SMÅPUNKTER: rek-historik i
   matchdetaljen (kräver flags i detail-payloaden), Bomben-spelläge (saknar
   payouts-flöde). Ursprungsplanen:**
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
- **Flashscore** — 401 är en avsiktlig grind och innehållet ger inget FotMob
  inte redan ger (mätt 2026-07-25). **Opta** — gratisvägen är renderade bilder,
  feeds kräver betald outlet-nyckel.
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

## Förslag: satsa på detta härnäst (kräver godkännande)

1. **B-fixarna F1–F5** — F1 och F4 först (F1 kan skapa felaktiga flaggor i
   drift; F4 måste in innan första kupongen bokförs). Allt är småfixar utan
   signalversions-risk utom F5b som är en medveten versionbump.
2. **C1 PH3-settlementaudit** — litet, tidskritiskt att göra rätt (första
   riktiga systemfacitet; feltolkad ROI här förgiftar allt nedströms).
3. **C2 devig-ablationen** — metodfrågan bakom hela +2,4 %-siffran, gratis data.
4. **C3 PH5 256/512** — avgör vad byggaren ärligt får lova för 13-matchsspelen.

Två ankare-gaten (A) avgör sig själv inom ~en vecka; Matchbook (C5) först
därefter. C4 radar-settlement kan byggas när som helst — facit mognar ändå
inte förrän ~mitten av augusti.
