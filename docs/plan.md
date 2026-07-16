# Spelkompisen — färdplan

## STATUS-SAMMANFATTNING (2026-07-17 — läs detta först i ny session)

**Appen är komplett och i drift** (backend 8002, frontend 5175, launchd var 30 min):
- **6 ligor**: Allsvenskan, Superettan, Eliteserien, OBOS-ligaen, MLS (nytt 2026-07-13),
  Träningsmatcher. Källor per match: SvS (Kambi), Pinnacle (sharp, AH/ÖU/hörnor),
  Expekt (Kambi expektse — ≈identisk med SvS, visas bara vid diff), Betinia (Altenar).
- **Signaler**: grön = sharp-ankrat värde, KVALITETSVIKTAT q=edge/(odds−1) (Kelly-andel;
  högoddsare kräver mer); 🔥 steam (devigade pp, radar-panel); ⇄ linjeflytt; 🚑 frånvaro
  (Sofascore missingPlayers, spelarstatus-viktad); ✓XI bekräftade elvor.
- **Modell (amber)**: xG-viktad **Poisson-styrkefit med DC-korrektion (ρ) i
  prediktionen** (per liga-pool, SWE/NOR-pooler; kalla den inte "Dixon-Coles-MLE" —
  granskningen 2026-07-13), Elo-prior, temperatur-kalibrerad (Allsv T=1.0, Elite
  T=0.85), prisar 1X2+AH/ÖU+hörnor. Backtest: nära marknaden i Allsvenskan (±0 %
  bästa pris), svag Eliteserien. **GRÖNT-KRITERIUM v2 (beslut 2026-07-13)**:
  ≥50 stängda flaggor OCH undre 90 %-KI-gränsen > 0 (kluster-bootstrap per match,
  close-EV winsoriserad ±20 %), per liga × marknad × modellversion — positivt
  snitt ensamt räcker inte. Flaggor stämplas med semantisk signalversion + git-hash.
- **UI**: spelkort m. Kelly + stödchips, radar, amber-lista, detaljvy (klick på match),
  loggtabell (📒), 🔔 larmhistorik, 🎯 bara-signaler, ℹ-prickar + legend;
  källhälsa och prisets bekräftelseålder visas direkt i Oddset-vyn.
- **Insamling (A1 ✅ 2026-07-13)**: launchd kör `cli.py smart` var 30:e min —
  fullt varv (alla källor + deep + modelldata + poolspel), och därefter SNABBVARV
  var 4:e min så länge någon match startar inom 3 h (Pinnacle + böckernas 1X2
  för ligorna i fönstret samt SvS deep-marknader för just 3h-matcherna).
  Poolspels-tätläget (var 5:e min när omgång stänger inom 2 h) väver i samma pass.
- **Granskningsrunda 2026-07-13** (Codex + Claude-verifiering, full rapport i
  `docs/granskning-2026-07-13.md`): 8/10 områden bekräftade med evidens.
  Åtgärdat samma dag: identitetslager light (WP3 — MLS-fitten 1648→1270 rader,
  304 datum-dubbletter borta, LA Galaxy en identitet, xG 57→73 %, straff-
  kontaminerade slutspelsresultat rättade/raderade, normaltime i stället för
  current), grönt-kriterium v2 (KI + modellversion), ärlig decay-text.
  **P0-sanningslagret är nu klart:** WP0–WP5 ✅ (se backloggen).
- **Granskningen runda 2 åtgärdad (2026-07-16)**: WP0 klar (WAL, busy_timeout,
  batch-transaktioner), WP2-mini klar (**notisvakten**: notiser kräver att både
  bok- och Pinnacle-priset observerades i det aktuella lyckade varvet — presence-
  set genom collect→log_and_notify, gated-räknare i loggen), version-split klar
  (`model_version` = semantiskt fingeravtryck `s-`/`m-` per tier; `git_hash` =
  exakt kodversion; migration via `scripts/migrera_signalversion.py`, se
  `docs/db-atgarder.md`). Facitet är ett **interimistiskt flaggfacit** tills
  WP5-ledgern finns; grönt beslutas **per signalgrupp** (aldrig per tier) med
  v3-trappan i WP5. Överlämning till Codex: `docs/overlamning-2026-07-16.md`.
- **Codex-fortsättning (2026-07-16)**: WP1 klar — Ö/U-ankringen matchar nu
  settlement-sannolikheten för hel/halv/kvart **efter** temperaturjustering;
  modellversionen byts automatiskt till `m-9b5389a7`. Verifierat med roundtrip-
  tester och 35 aktuella ankrade matcher (linjer 2.25–3.75). Akuta delen av WP8
  klar: transient Sofascore-statistikfel sparar resultatet men lämnar eventet
  för retry; 404/410 avslutas som permanent statistik-saknad. Första automatiska
  sviten finns i `backend/tests/` (57 `unittest`-fall, inga nya dependencies).
  **WP2 full klar:** prisförändring (`fetched_at`) och senaste bekräftelse
  (`last_seen_at`) är separerade; lyckade svar markerar plockade/suspenderade
  priser, källfel gör det inte. Värde, steam, modellkanter och closing-facit
  kräver tillgängligt pris bekräftat inom 45 min. Källhälsa + prisålder visas i
  UI och SvS-deep ingår i 3h-snabbvarvet. Slutliga signalversioner efter
  närvaroregeln: sharp `s-0f1355fb`, modell `m-fce3b64e`.
  **WP4 klar:** CLV-identiteten är nu match × marknad × tecken × lina ×
  signalversion. Stängning sparar både flagglina och slutlina; linjeflytt blir
  ett eget, selektionsriktat facit i stället för censur. 110/110 gamla rader
  bevarades vid migreringen och nya versionsrader loggas separat.
  **WP5 klar:** prediction-ledgern fryser alla sharp-/modellprediktioner och
  oflaggade kontroller en gång vid T−24 h/T−3 h/T−20 min. Separata
  capture-markörer bevarar även källfrånvaro; sena starter sparas men får inte
  kvalificera en grupp. V3-statusen är amber → candidate → out-of-time green,
  med kluster-KI per match, kluster-signflip-p-värde och BH-FDR 10 % för
  utforskande grupper. Träningsmatcher är utforskande, aldrig primär "liga".
  Första livepasset: 220 prediktioner/30 tier-captures; bootstraprader som
  startade mitt i en horisont sparades men timingvakten släpper bara 4 captures
  till valideringsfacitet. Nya matcher bygger rena serier automatiskt.
  **WP6a klar:** jackpot/rullpott ingår nu i EV-toppens och färgreduceringens
  toppnivå redan när rader väljs, och samma jackpot används i systemvyns EV/ROI.
  **WP6b κ-audit klar:** backtestskattaren är nu exponeringsviktad
  (`Σ vinnare/Σ prognos`) med 90 % blockbootstrap. 100 omgångar gav Stryk
  0,98 [0,90..1,05] och Europa 0,91 [0,81..0,97]. Eftersom κ<1 skulle höja
  visad EV lämnas runtime konservativt på 1,00 tills ett oberoende tidsfönster
  bekräftar effekten. UI:t märker nivåer under toppvinsten som approximationer.
  **WP6c portfolio klar:** Topptipset räknar alla 6 561 utfall; 13-matchskuponger
  använder reproducerbara 10 000 utfall. Utfallsberoende medvinnare integreras
  som `E[1/(W+k)]`, egna rader delar potten och UI visar EV, pluschans, nollrisk,
  percentiler och MC-fel. 2 048 rader tar ~0,38 s. Full metodrapport:
  `docs/wp6-portfolio-2026-07-16.md`.
  **WP8b frånvarohistorik klar:** varje lyckat Sofascore-lineup-svar får en
  tidsstämplad capture även vid tom lista; spelarrader bevarar provider-ID,
  position, orsakskod/beskrivning, slutdatum, matcher och rating. Första
  livevarvet gav 14 captures och 75/75 spelare med ID+position; 15 äldre
  senaste-payloads backfylldes som legacy utan påhittade identiteter.
  **WP8c PIT-Elo klar:** dagliga rankingar sparas som immutabla captures och
  ClubElos egna inkluderande From/To-intervall kan läsas med `as_of`. Tre
  säsongsankare fann 39 klubbar; full historik hämtades för 36 och gav totalt
  4 197 intervall. KFUM Oslo, Odd Grenland och Sirius har verifierade
  ankarintervall men fulla klubbendpoints timeoutar och förblir retrybara.
  Effektiv täckning med modellens namnmatchning: Allsvenskan 507/581 (87,3 %),
  Eliteserien 483/587 (82,3 %), men Superettan 19/600 och OBOS 11/600 — Elo får
  därför fortsatt bara vara en sporadisk prior i andradivisionerna.
  **WP3-tillägg fuzzy-audit klar:** varje automatisk icke-exakt/icke-alias-länk
  redovisar likhet, berörda matcher och verified-status. Tolv entydiga
  provider-varianter flyttades till verifierade alias. Auditen hittade en riktig
  felkoppling: Egersund hade blivit Haugesund i 3 kvalmatcher vid likhet 0,706.
  Auto-gränsen är nu 0,75; länken är explicit verifierad som avvisad och kan
  inte mergas. Modellversionen byts till `m-c00f8a09`; sharp ligger kvar på
  `s-0f1355fb` eftersom dess facit inte påverkas.
- **UI v3-pass klart (2026-07-16):** global status visar nu dataålder först och
  teknisk insamlingsstatus i en expander; poolspelen prioriterar prognostiserat
  spelvärde vid spelstopp och har fasta mobilgenvägar till byggare/kupong.
  Oddset visar fyra viktigaste värdespel först, har kollapsad marknadsradar och
  källhälsa, separata liga-/verktygsrader samt riktiga mobilkort utan sidscroll.
  Liga-/verktygsraden är sticky, sekundära bokodds ligger bakom `Fler odds`,
  tom Hörnor-kolumn döljs och detaljgraferna skalar med skärmen. Panelval sparas
  mellan besök och laddning, tomt resultat samt fel har tydliga egna tillstånd.
  Bomben visar faktisk modellsannolikhet bredvid värdekvoten, tonar ned extrema
  lågchansutfall och håller radbyggaren synlig på desktop/nåbar från mobil.
  PWA-manifest, maskbar 1–X–2-ikon och Apple-hemskärmsmetadata ger appidentitet
  i fristående läge utan offline-cache som kan göra oddsdata missvisande gammal.
- **Kvalitetspaket + Backtest v4 klart (2026-07-16; 98 tester efter V2-B):** tester täcker nu även
  power-devig, event/tidszon, post-kickoff/closinglina, analytisk poolutdelning,
  klusterbootstrap, signalgrupp och versionsisolering. Backtest v4 mäter den
  förregistrerade q-policyn med matchblock-KI och X-frekvens per liga; full rapport
  i `docs/backtest-v4-2026-07-16.md`. Beslut: q=1,5 % och edgegolv 2 % behålls,
  ingen X-korrigering, modellen fortsatt amber. B365 täcker bara ~20 %; Max
  closing är ett optimistiskt tak, så prediction-ledgern förblir domaren.
  Pinnacle-opening avvisas uttryckligen från q-facitet.
- **Modell v2 (V2-A klar 2026-07-17):** marknadsankrad residualmodell med
  PIT-dataset, nested walk-forward, fryst outer-testdom och forward-skuggläge.
  Featureinputs fryses nu samtidigt med ledgern, versioneras semantiskt och
  redovisar resultat/xG-cutoff+hash, PIT-Elo-intervall, saknasfält och öppna
  laglänkar. Coverage behåller tomma/missade captures i nämnaren; rekonstruerade
  historikrader kan aldrig bli promotionsbevis. Första audit: 5 horisontrader/
  4 matcher, komplett fit+Elo, 0 läckor/dubbletter och marknadsidentitet
  max |Δp| 2,78e−17. Outer-manifestet är fryst före modellarbete. Rapport:
  `docs/v2-a-audit-2026-07-17.md`; plan: `docs/modell-v2-plan.md`.
  **V2-B-motorn är klar men modellen STOPPAD (2026-07-17):** deterministisk
  multinomial ridge, träningsfönster-standardisering/missing-indikatorer och
  nested matchdags-walk-forward är verifierade. Äkta ledgermatcher har ännu
  inget facit. Ett separat, icke-promoverbart Pinnacle-closing-upper-bound gav
  1 097 OOT-developmentprediktioner: total Δlogloss −0,00126, KI
  [−0,00745..+0,00511]; Allsv +0,00168, Elite −0,00437. Kompletta features var
  positiva (+0,00230), missing-rader negativa (−0,00426), så kriteriet att alla
  matcher ska hålla missades. **Ingen V2-C/skugga och ingen live-ändring.**
  Rapport: `docs/v2-b-backtest-2026-07-17.md`.
- **EJ GJORT ÄNNU**: NTFY/notifieringsspåret **PAUSAT på Samans begäran
  2026-07-16**; beslut om mobil-default för `Bara signaler` återstår;
  P1/P2-backloggen finns nedan. Villkoret WP0–WP5 för att
  ompröva stora Europa-ligor är uppfyllt, men expansionen startar inte utan ett
  separat produktbeslut (fler ligor är inte automatiskt nästa prioritet).

## Backlog (WP-struktur efter granskningen 2026-07-13, prioriterad)

Research-grund: steam-värde dör på minuter, inte halvtimmar ("if you're seeing the
same price after 10-20 min, the value is gone" — [SportBot om steam](https://www.sportbotai.com/blog/steam-moves-betting-explained-ai-data),
[Arbusers teknisk analys](https://arbusers.com/how-to-find-value-bets-on-sharps-by-odds-movements-aka-technical-analysis-t10188/),
[CLV-metodik](https://www.wunderdog.com/sports-betting/how-to-beat-the-closing-line-in-sports-betting));
Dixon-Coles-familjen står sig som guldstandard — XGBoost m. 40–100 features slår
den sällan med >1 pp ([Wilkens 2026](https://journals.sagepub.com/doi/10.1177/22150218261416681)) →
jaga inte ML, jaga LATENS, DATAKVALITET och ÄRLIGT FACIT. Granskningsevidens och
acceptanskriterier per WP: `docs/granskning-2026-07-13.md`.

**Metodregler (tillägg 2026-07-13/16, viker aldrig):**
- Asiatiska sannolikheter hanteras alltid settlement-aware (push/half-win) —
  i ankring såväl som prissättning.
- Notiser kräver närvaro-bekräftat bokpris (sett i senaste varvet) — aldrig larm
  på pris som kan vara plockat/suspenderat (✅ notisvakten, 2026-07-16).
- Alla prediktioner loggas vid fasta horisonter med modellversion — flaggor är
  ett urval för handling, aldrig underlaget för utvärdering (WP5).
- **Grönt beslutas per signalgrupp** (tier × liga × marknad × version) — aldrig
  per tier eller aggregat; aggregatraden är enbart översikt.
- **DB-ändringar = skript + backup + rapport** (`docs/db-atgarder.md`) — aldrig
  ad-hoc-SQL.
- Versionspolicy: `signal_version` (s-/m-fingeravtryck av signalrelevanta
  parametrar + T-kalibrering + DATA_VERSION) grupperar facitet; `git_hash` ger
  reproducerbarhet. Docs/UI-commits får aldrig fragmentera facitet.

**Klart ur granskningen:** *(2026-07-13)* WP3 identitetslager light (alias +
datumtolerans ±1 dygn + audit-lista; MLS-fitten sanerad inkl. straff-resultat,
normaltime-fixen), grönt-kriterium v2 (kluster-bootstrap-KI + versionsstämpel),
decay-benämningen, A1-snabbpollen (`cli.py smart`). *(2026-07-16, runda 2)*
WP0 (WAL/busy_timeout/`bulk()`), WP2-mini (notisvakten), version-split
(signal_version + git_hash, migrerad). *(2026-07-16, Codex)* WP1 settlement-
ankring + testgrund, WP2 full prisnärvaro/källhälsa, WP4 CLV-identitet +
linjeflytt-facit, WP5 prediction ledger + grönt v3, WP8a Sofascore seen/retry.

**P0 — sanningslager & matematik (i ordning):**
- **WP1 ✅ 2026-07-16**: settlement-aware ÖU-ankring för hel/halv/kvart;
  rotlösningen mäter den slutliga temperaturjusterade matrisen så T inte bryter
  ankaret. `pair_fair` och ankaret delar settlement-matematik; `anchor` bumpad i
  MODEL_PARAMS. Historisk T är fortfarande fittad på oankrade 1X2-prediktioner —
  omkalibrera inte skenbart utan historiska Ö/U-linjer; WP5-ledgern ger PIT-data.
- **WP2 full ✅ 2026-07-16**: persistent `last_seen_at` per selektion
  (uppdateras vid dedup-skip), available/suspended, källhälsa, 45-minutersvakt
  i värde/modell/steam/facit, bekräftelseålder i UI och SvS-deep i 3h-varvet.
  Misslyckade källanrop ändrar aldrig availability. Migration + backup +
  rapport finns i `docs/db-atgarder.md`.
- **WP4 ✅ 2026-07-16**: CLV-identitet = `(match_id, market, sign, line_key,
  model_version)`; `line_key` är heltalsnormaliserad lina och 1X2 har sentinel.
  Stängningen använder färskt exakt-line-pris för jämförbart close-EV och
  sparar samtidigt `closing_line`, `line_delta` och selektionsriktat
  `line_move_score` (>0 = marknaden rörde sig med spelet). Finns inte färsk
  exakt lina redovisas `linje flyttad`, aldrig ett fabricerat close-EV.
  Skript, backup och produktionsutfall finns i `docs/db-atgarder.md`.
- **WP5 ✅ 2026-07-16**: prediction ledger — ALLA prediktioner vid fasta
  horisonter (T−24h/−3h/−20m) med sharp-fair/modell-fair, bästa bokpris,
  availability, kontrollgrupp och komposit signalversion. Capture-markören är
  atomär och skrivs även vid tomt källutfall; missade horisonter bakfylls aldrig.
  Timingvakt: max 45/15/10 min sen för 24h/3h/20m i valideringsfacitet.
  **Grönt-kriterium v3 på ledgern**:
  status per grupp amber → candidate (n_flags ≥ 50 OCH n_matches ≥ 30 OCH
  span ≥ 28 d OCH undre 90 %-KI > 0) → green (bekräftad out-of-time: ≥15 nya
  matcher EFTER candidate-datumet med KI_lo > 0); förregistrerade primära
  grupper = sharp × 1x2 × de fem riktiga ligorna, övriga (inkl.
  träningsmatcher) är utforskande och kräver BH-FDR-korrigering (10 %) på
  kluster-signflip-p-värden före candidate. Rapporten visar n_flags/n_matches/
  n_weeks/span, kontrollantal och timing; KI märks instabilt under 10 matcher.
  Modellen fittas i snabbvarv endast när en ny horisont saknas. Ersätter gamla
  A2 (öppningslinje = första horisonten) och ger gamla A3 (odds-band-facit)
  gratis.

**P1 — EV-ärlighet, integritet, validering:**
- **WP6 ✅ 2026-07-16** (S+M): jackpot före radvalet; κ̂-metod och
  100-omgångsaudit; runtime κ=1,00 enligt konservativ riktning. Portfolio-
  värderingen räknar alla 6 561 Topptipsetutfall eller 10 000 reproducerbara
  13-matchsutfall, utfallsberoende Poisson-medvinnare, egna raders konkurrens,
  EV/risk/percentiler och jämförelse mot snabbformeln.
- **WP7 ✅ 2026-07-16** (S): ärliga benämningar — "xG-viktad Poisson-
  styrkefit med DC-korrektion i prediktionen" i kod och alla centrala UI-
  förklaringar; T:s in-sample-status visas och ledgern pekas ut som oberoende
  forward-facit.
- **WP8 ✅ 2026-07-16** (S/M): insamlingsintegritet — seen/retry,
  tidsstämplad frånvaro med spelar-ID/position och PIT-Elo. Elo har både
  observerade dagscaptures och providerintervall för historisk `as_of`-läsning;
  källtimeout lämnar klubben omarkerad för retry. Tre klubbhistoriker är ännu
  partiella enligt statusblocket, aldrig tyst klassade som kompletta.
- **WP-test** (M, löpande): testgrund ✅ med standardbibliotekets `unittest`
  (pytest-kompatibel, ingen dependency). 98 fall täcker bland annat
  settlement/push/kvart, temperatur-roundtrip, normaltime, seen-retry/404,
  bulk-rollback, prisnärvaro, Elo-PIT/retry samt CLV-identitet/linjeflytt och
  WP6:s Poissonandel, portföljkonkurrens, full enumeration och reproducerbar MC.
  Nya regressionsfall läggs före varje framtida fix.
- **WP3-tillägg ✅ 2026-07-16** (S): fuzzy-links-audit — ALLA icke-exakta/
  icke-alias-länkar visar likhet + antal berörda matcher + verified-flagga.
  Godkända länkar ligger i TEAM_ALIAS/meta; kända falska länkar ligger i en
  verifierad avvisningslista. Auto-gräns 0,75, review-band 0,55–0,75. Scope:
  WP3 light löser resultatmergen — INTE pre-match-eventidentitet/spelare/
  arenor/provider-ID generellt.
- **Backtest v4 ✅ 2026-07-16:** q-grid med förregistrerad policy q=1,5 %,
  edgegolv 2 %, matchblock-KI, B365-täckning/Max-tak och X-frekvens per liga.
  Ingen policyändring; se `docs/backtest-v4-2026-07-16.md`.

**P1 — datakällor (efter WP3, identiteten är förutsättningen):**
- **WP9a**: ASA (American Soccer Analysis) som oberoende MLS-kontroll — **cert-
  fel härifrån 2026-07-13** (hostname mismatch via både httpx och Chrome-TLS);
  verifiera åtkomst innan planering. xG blandas ALDRIG mellan providers — egen
  kolumn/tagg.
- **WP9b**: Sofascore coverage-matrix per liga/säsong/endpoint/fält (script →
  docs). Verifierat 2026-07-13: shot-xG+xGOT finns för Eliteserien (30/30),
  saknas för Allsvenskan (0/31) — match-xG via /statistics finns för båda.
- **WP9c**: Sofascore team-events (alla tävlingar per lag) → vilodagar/resor
  (gamla B6) utan cup-blindhet.

**P2 — senare:**
- Frånvaro-modellering (gamla B5) — när WP8-historiken samlats; amber tills facit.
- MLS-kalibrering `oddsetcalibrate` + mls (gamla B7) — efter WP1+WP3 (nu sanerad
  data, men ankringen först).
- Hörn-värde grön väg (gamla B8) — efter WP5.
- Officiell MLS-frånvarorapport, NFF fiksId-sidor (JS-RE), Fogis-spaning,
  Open-Meteo point-in-time-väder, domare/underlag — features med liten väntad
  effekt; Betfair Historical: skip tills konkret behov.
- Manuell spel-journal i appen (skild från forskningsfacitet) — Samans beslut B8
  i granskningen, öppet.

**C. UI/mobil (Samans punkt: inte optimalt än — parallellspår, blockerar inget)**
9. ✅ UI v3-pass: spelkorten är 1 kolumn utan sidscroll; 💰 visar fyra först;
   📈 är kollapsad; datakällor ligger i expander; pool/Bomben har fasta
   mobilåtgärder; panelernas öppet/stängt-läge sparas och detaljgraferna är
   responsiva. Kvar som produktbeslut: om 🎯 Bara signaler ska vara mobil-default.
10. ✅ Oddset-städning: Hörnor-kolumnen döljs när allt innehåll saknas;
   sekundära bokrader (E/B) styrs med `Fler odds`; liga-/verktygsraden är sticky.
11. ✅ PWA: manifest, maskbar SVG/PNG-ikon och Apple touch-ikon ger
    hemskärms-appen egen identitet. Ingen offline-cache — odds ska vara färska.
    iOS kan lägga sidan på hemskärmen direkt; Chromium kräver HTTPS utanför
    localhost för att själv erbjuda installation (Tailscale Serve är separat).

**D. Stora ligorna — FORTSATT PAUSADE; WP0–WP5-gaten är nu uppfylld.**
Fler ligor löser inte automatiskt nästa problem och ledgerserierna behöver tid
att mogna. Id-tabellen behålls som förberedelse; expansion kräver ett separat
produktbeslut, inte bara att den tekniska gaten passerats.
| Liga | football-data | Sofascore ut | Kambi-väg | Pinnacle |
|---|---|---|---|---|
| MLS ✅ (inlagd, i säsong) | new/USA.csv | 242 | football/usa/mls | 2663 |
| Premier League | mmz4281/{säsong}/E0.csv | 17 | football/england/premier_league | proba v. säsongsstart |
| Bundesliga | .../D1.csv | 35 | football/germany/bundesliga | proba |
| La Liga | .../SP1.csv | 8 | football/spain/la_liga | proba |
| Serie A | .../I1.csv | 23 | football/italy/serie_a | proba |
| Ligue 1 | .../F1.csv | 34 | football/france/ligue_1 | proba |
OBS: huvudligornas filer ligger under mmz4281/-strukturen (inte new/) — parsern
behöver ett litet format-grepp (Div/FTHG/FTAG-kolumner). FÖRVÄNTNING: dessa
marknader är extremt effektiva — SvS/Pinnacle-gap blir mindre och stängs fortare;
värdet sitter i tidiga linjer + mindre marknader. Kärnvärdet förblir Norden/MLS.
Verifiera alltid Sofascore-id:ns SPORT (handbolls-läxan).

**E. Infra/övrigt**
12. NTFY/notifieringar — pausat 2026-07-16; återuppta först när Saman ber om det.
13. Betsson (egen oddsmotor) — kräver browser-RE av OBG-API:t.
14. Servermigrering (Pi 5/N100, launchd→systemd) — beslut öppet sedan tidigare.
15. Altenar-champ för träningsmatcher/MLS hos Betinia (GetSportMenu-sväng).

## GAMMAL STATUS (historik — nyaste överst)

**2026-07-12 — Etapp 0 + Etapp 1 KLARA.**
Etapp 0: repo klonat från svs, portar 8002/5175/5181, eget venv, DB seedad, Oddset-flik.
Prober gröna; omtestning av "blockade" källor gav genombrottet **Sofascore-xG i
browser-kontext** (xG-risken struken). App-URL (Tailscale): `http://100.122.85.66:5175`.
Etapp 1: `app/kambi.py` + `app/oddset.py` (LEAGUES, Pinnacle-ligaindex, klubbnamns-
matchning, insamling med dedup), tabeller `oddset_matches`/`oddset_odds`,
`/api/oddset/matches` + `/api/oddset/refresh`, `cli.py oddset`, OddsetView (tidsordnad
lista, dagrubriker, liga-visa/dölj i localStorage, SvS + P-odds, AH/ÖU huvudlinor,
rörelsepilar med serie-tooltip). Verifierad i browser (desktop + mobil): 23 matcher,
11 med båda källorna korrekt ihopslagna (KFUM↔KFUM Oslo, HamKam↔Hamarkameratene).
launchd-plist + snapshot.sh (oddset + snapshot-smart) klara — EJ laddade: Saman kör
`cp backend/scripts/com.saman.spelkompisen.snapshot.plist ~/Library/LaunchAgents/ &&
launchctl load ~/Library/LaunchAgents/com.saman.spelkompisen.snapshot.plist`.
OBS: Kambis träningsmatch-listView är tom just nu (SvS lägger upp nära avspark) —
Pinnacle-only-matcher visas med P-odds tills dess. Rörelsepilar syns när serien växer.
Etapp 2 (samma dag): `app/oddset_value.py` — power-devigad Pinnacle = fair; edge =
fair × SvS-odds − 1; AH/ÖU bara på samma linje; P~ (härlett) visas med ° men loggas
ALDRIG i CLV. UI: 💰 Värdespel-panel (edges ≥2 % sorterade), gröna edge-pills i
tabellen, 🔥 steam-badge (devigade pp-skift 6/24 h, ≥3,5 markant / ≥6 stark),
📒 Signal-logg-rad (CLV: first/best per flagga, stängning = devigad Pinnacle före
avspark, close-EV i rapporten). ntfy-notiser: edge ≥3 % (💰) + 6h-steam ≥5 pp (🔥,
träningsmatch-caset), dedup i meta — **kräver NTFY_TOPIC i backend/.env (EGET topic,
inte svs:s) — EJ satt ännu = avstängt.** Starta-knappen fixad: installerar plisten
själv + laddar; launchd-jobbet är LADDAT och kör (verifierat).
Första riktiga fynden direkt: SvS 10.0 på Kalmar borta vs fair 7.78 (+28,6 %),
IFK Göteborg borta 4.10 vs fair 3.70 (+10,8 %) — loggade i facitet.
Etapp 3 (samma dag) — egen modell, allt amber-tier:
- **curl_cffi ERSATTE Playwright**: Sofascore-API:t svarar 200 med Chrome-TLS-
  imitation (`impersonate='chrome'`) — xG-hämtningen kör direkt i pipelinen,
  inget browserberoende. (Ny dep i requirements.txt.)
- `app/oddset_data.py`: football-data.co.uk bulk (SWE/NOR, säsonger ≥2024, 12h-
  throttle), Sofascore-xG + hörnor + resultat (6h-throttle, pacad 1.2 s/anrop,
  ~90 matcher/liga backfillade), ClubElo hela rankingen dagligen (SWE+NOR-filter).
  `merged_results()` kanoniserar Sofascore-namn till football-data-namnen och
  dedupar (annars splittras lag som djurgardens/djurgarden i fitten — hittad bugg).
- `app/oddset_model.py`: iterativ DC-fit per liga (att/def per lag, hemmafördel,
  tidsavklingning 240 d, effektiva mål = 0.65·xG + 0.35·mål), rho −0.13 (klubb-
  litteratur, refit i Etapp 5), MIN 8 viktade matcher per lag. Totalnivån ankras
  mot devigad sharp Ö/U-linje när Pinnacle finns (bisektion på skalfaktor,
  bevarar modellens styrkeförhållande). Sanity: modell 1.49/5.29/7.04 vs
  Pinnacle 1.38/5.48/7.02 (Hammarby–Kalmar); prediktioner + Elo även för nästa
  omgång INNAN Pinnacle öppnat.
- UI: 🧪 Modell-toggle (localStorage), amber M-rad under P-raden, amber-pill vid
  modell-edge ≥5 % (högre ribba än sharp), Elo/μ i tooltip på matchnamnet.
  Modellen är UTANFÖR värdelistan och CLV-facitet (vm-metodregeln).
- `cli.py modeldata` tvingar datauppdatering; insamlingen kör refresh_all throttlat.
**Etapp 4 SKIPPAD (Samans beslut 2026-07-12):** nyheter/lineups som egen funktion
tillför inte — det vi jagar är ODDSRÖRELSEN när lineups släpps, och den fångas
redan av steam-flaggan + ntfy (Etapp 2). Bevaka inte nyheter.

**Etapp 5 KLAR (2026-07-12)** — `app/oddset_backtest.py` + `cli.py oddsetbacktest`:
walk-forward mot Pinnacle-STÄNGNING (football-data PSC), fit endast på matcher före
resp. matchdag, eval 2024-07→ (n=351 Allsvenskan, 330 Eliteserien). **Domen:**
- Allsvenskan: modell-logloss 1.029 vs marknadens 1.010 — nästan marknadskvalitet;
  optimal blandvikt w=0.1; beslutsregel-ROI −1..−2 % mot Pinnacle-pris, ±0..+1 %
  mot bästa pris. Imponerande för ren DC, men INTE bättre än sharpen.
- Eliteserien: klart sämre (0.991 vs 0.958, w=0, ROI −11..−15 %) — giftig som
  spelregel. Amber-status är alltså RÄTT och kvarstår; grön = sharp-ankrat förblir
  enda spelbara signalen. Obs: backtestens säsonger saknar xG (Sofascore täcker
  bara nuvarande) — live-modellen med xG-viktning kan vara något bättre.
- **rho REFITTAD: −0.01** (grid-minimum i BÅDA ligorna; klubblitteraturens −0.13
  överkorrigerar — samma mönster som vm fann för landslag). DC_RHO_CLUB uppdaterad.
- Kalibreringstabellen ser sund ut (deciler pred ≈ verklig träff ±3 pp).

**Samma pass (Samans önskemål):**
- **Expekt** tillagd som sidobok: Kambi-operatör `expektse` (verifierad — samma
  event-id:n som svenskaspel, trivial matchning). `BOOKS`-listan i oddset.py;
  1X2 sparas som source `expekt`; värdemotorn räknar edge mot BÄSTA bok-odds och
  posten säger vilken bok (💰-listan: "@ 15.00 hos Expekt"). ATG (`atg`) verifierad
  och kan läggas till som en rad till i BOOKS.
- **Altenar VÄNTAR**: deras API kräver operatörens `integration`-namn (webdemo/
  pixelbet gav 400; sb2.altenar.com svarar ej). Behöver veta VILKEN Altenar-sajt
  Saman spelar hos — då är det en BOOKS-rad + liten klient.
- **Hörnor tillagda**: Pinnacle hörn-specials (units='Corners', barn-matchup →
  förälder, huvudlinje) + Kambi "Antal hörnor" → market `cor`, egen kolumn i UI,
  med i värdemotorn (samma-linje-regeln). Verifierat live: P och SvS båda på
  9.5/10.5 för dagens matcher.
- **Live-skydd**: startade matcher sparas ej (odds), värderas ej, modelleras ej —
  och 54 live-förorenade rader städades ur DB (räddade rörelseserierna).
- **Översikts-UI**: ℹ-förklaringspanel (vad raderna/pillsen/pilarna/🔥 betyder, vad
  som är spelbart vs spaning, backtest-domen inbakad), 🧪-amber-lista med modell-
  avvikelser under 💰-listan, bok-namn i värdelistan, backtest-ärlighet i tooltips.
**Senare samma dag:**
- **Betinia (Altenar) LÖST**: `integration=betinia` mot
  `sb2frontend-altenar2.biahosted.com/api/Widget` — GetSportMenu → soccer=66,
  champ-id:n Allsvenskan **3537**, Eliteserien **3458**, Superettan **4825** (!).
  `app/altenar.py`; BOOKS har nu expekt + betinia; matchning fuzzy namn+avspark.
- **Expekt ÄR Kambi, bekräftat**: LeoVegas Group (inkl. Expekt) kör Kambi Turnkey
  t.o.m. 2027 (Kambi-pressrelease). `expektse`-flödet = produktionsodds.
- **Live-flagg-sanering**: 14:52-körningen (före live-skyddet) hann flagga live-odds
  mot förmatch-fair (+112 % "edges") — 4 rader raderade; guards finns nu i BÅDE
  collect (inga live-sparningar), attach_value och attach_model. Kvarvarande facit
  är rent (2 äkta stängda flaggor, båda positiva).
- **Modellens forward-logg**: modell-edges ≥5 % loggas som tier='model'
  (market 'm1x2'), notifierar aldrig, egen rad i 📒-panelen. Grönt-kriteriet
  nedan avgörs av denna logg.
**Nästa:** se "Modellplan" nedan; Superettan som egen flik (Altenar 4825 + Pinnacle
+ Kambi-väg finns); hörn-modell på Sofascore-datat.

**Rörelse-radarn + OBOS-ligaen (2026-07-12 kväll):**
- **📈 "Största rörelserna"-panel** i Oddset-vyn: största devigade Pinnacle-skiften
  (6/24 h, ≥1,5 pp, sorterade) över ALLA ligor oavsett flikfilter (träningsmatch-
  caset får inte missas). Varje rad visar P-oddsets väg + om någon bok står kvar
  på gamla priset (grön pill = agera). Startade matcher exkluderas.
  Verifierad live direkt: GAIS +3,5 pp/6h med "Expekt kvar på 1.87 (+2%)";
  Yverdon–Sion (träningsmatch) flyttade 8,2 pp/6h.
- **Steam-fallback**: _probs_at använder äldsta punkten när serien är yngre än
  fönstret men äldre än halva (skift på kortare tid = starkare signal; annars
  är steam blind tills 6/24 h-historik samlats — hittad när radarn var tom).
- **OBOS-ligaen tillagd**: Pinnacle 2331, Kambi `football/norway/obos-ligaen`,
  Sofascore ut 1420; FIT_POOLS: Norge-pool (Eliteserien + OBOS) — samma grepp
  som Sverige-poolen, riktat mot Eliteseriens svaghet (nykomlingar). Ingen
  Betinia/Altenar-champ för OBOS. Backfill av resultat/xG kör i bakgrunden.

**Parmarknaderna kompletta (2026-07-12 kväll, Samans önskemål):**
- **Rörelser på AH/ÖU/hörnor**: punktserierna bär nu LINJEN; UI visar pilar för
  prisrörelse på nuvarande linje + ⇄-märke när själva linjen flyttats (ofta
  starkare signal än priset) — för både SvS och Pinnacle. Serie-tooltip med
  [linje] odds per punkt.
- **Modell på AH/ÖU**: `pair_fair` prisar båda sidor vid SvS:s linje ur DC-
  matrisen (push på hellinjer, kvartslinjer som split — asiatiska regler).
  M-rad i cellerna + amber-pill ≥5 %; AH bär modellens egen supremacy (kan
  avvika på riktigt), ankrad ÖU ligger nära sharpen per konstruktion (edgen
  mäter mest bokens marginal — dokumenterat i tooltip). AH/ÖU-avvikelser med
  i amber-listan och forward-loggas som market mah/mou (facit per marknad).
- **Ridge-shrinkage i fitten** (att/def ^0.98 per iter): skydd mot skala-drift
  i svagt kopplade pool-subgrupper. Sanity-backtest: logloss 1.0229 vs 1.0216
  (brusnivå), ROI oförändrad/bättre — behållen.
- **OBOS-datat**: Sofascore-id 1420 visade sig vara HANDBOLL (48–19-resultat
  i fitten — base exploderade till 29 och avslöjade det), 28937 volleyboll;
  rätt id är **ut 22 "Norwegian 1st Division"** (verifierad: riktiga lag + xG
  finns). 370 handbollsrader utrensade, ombackfill körd. Läxa inskriven i
  oddset_data: verifiera ALLTID sporten på Sofascore-id:n.

**UI 2.0 + kalibrering (2026-07-12 kväll, Samans 5 punkter + mer):**
- **Spelkort med mänskliga etiketter**: "2 · Halmstads BK @ 14.00" i stället för
  "1X2 2" (tecknet smälte in i marknadsnamnet), "Degerfors +0.5 AH", "Under 3.5 mål".
  `selLabel()` används i kort, radar, amber-lista.
- **¼-Kelly på korten** (bank-input i panelhuvudet, localStorage svs_oddset_bank).
- **Matchdetalj vid klick**: 3 odds-grafer (SvS grön/Pinnacle blå per tecken),
  parmarknadsserier med linjer, modell-μ/fair/T/Elo, matchens alla loggade flaggor.
- **Signal-loggen som tabell**: klick på 📒-raden → full tabell (flagga, bok, odds,
  edge, bäst, stängnings-EV, tier).
- **🎯 Bara signaler**-läge (filtrerar tabellen till matcher med någon signal).
- **🔔 Larm-historik**: ALLA triggade larm loggas nu i meta (JSON med sent-flagga)
  även utan NTFY_TOPIC ("ej pushad") — /api/oddset/notices + panel.
- **Info-städning**: all förklaringstext borta från ytan — ℹ-prickar (hover) per
  panel + legenden som full referens.
- **Temperatur-kalibrering (steget mot icke-amber)**: `cli.py oddsetcalibrate`
  fittar T per liga på walk-forward-prediktioner (hela målmatrisen p^(1/T)) och
  sparar i meta; attach_model tillämpar live (Superettan/OBOS ärver pool-huvud-
  ligans T). Resultat: **Allsvenskan T=1.0 (redan välkalibrerad!), Eliteserien
  T=0.85** (underkonfident — skärpning förbättrar logloss 0.981→0.980).
  Kvar mot grönt: forward-loggens facit (M3-kriteriet ≥50 stängda, positivt snitt).

**Mer modelldata — utredning + Sofascore-frånvaro (2026-07-12 sen kväll):**
- **Opta (performfeeds)**: vm-outleten är scopad till VM-flödena — 403 på
  tournamentcalendar/authorized. Stängd väg för våra ligor utan ny outlet-nyckel.
- **allsvenskan.se**: wp-json ger 403 (botskydd). Flashscore: feed svarar men
  odokumenterat teckenprotokoll och inget vi saknar (resultat/xG/hörnor har vi
  bättre via Sofascore). Båda nedprioriterade.
- **Den verkliga guldådern: Sofascore /event/{id}/lineups** — strukturerade
  FRÅNVAROLISTOR (missingPlayers med orsakskod) + bekräftade elvor, gratis från
  källan vi redan kör. `refresh_absences` (2h-throttle, matcher <48 h, pacad):
  `oddset_absence_capture`/`oddset_absence_player` bevarar PIT-historik med
  spelar-ID/position; meta `oddset_abs:{match_id}` är senaste-kompatibilitet.
  🚑N-märke med spelarnamn/position i tooltip + ✓XI när elvorna bekräftats
  (= kolla radarn för sen sharp-rörelse!) + lista i detaljvyn. Verifierat live:
  första historikvarvet gav 75/75 spelare med ID+position. Orsakskoder verifierade
  mot råbeskrivningen: 0 annat, 1 skada, 11/12/13 kortavstängningar. Nästa steg
  när data samlats: viktad frånvaro-styrka in i modellen (amber tills facit).
- **Buggfix**: .lgtag-CSS:en var scopad till tabellen — utanför den klistrades
  ligataggen mot lagnamnet ("SÖsters IF"). Nu global chip-stil.

**Kvalitetsviktning (2026-07-12 natt, Samans poäng):**
- **Värdesignaler väger nu edge mot oddsnivån**: kvalitet q = edge/(odds−1)
  (= Kelly-andelen). Samma edge är mycket skörare på höga odds — ett halvt
  procentenhets fel i fair blåser upp en 15.0-edge enormt (och backtestens
  ≥8 %-band var giftigt). Kort sorteras + nivåsätts på q (STARK ≥4 %, EDGE
  ≥2 %, SVAG ≥0,75 %; under golvet visas ingen pill), notiser triggar på
  q ≥1,5 % i stället för rå edge. Facit-LOGGEN förblir bred (edge ≥2 %
  oavsett odds) så vi kan mäta högoddsar-flaggornas verkliga utfall per band.
  Kvitto: Hammarby @1.33 +2,1 % toppar nu (q 6,4 %), Halmstad @14 +2,8 %
  försvann ur korten (q 0,2 %).
- **Frånvaro viktas efter spelarstatus**: refresh_absences hämtar säsongs-
  matcher + rating per saknad spelare (Sofascore player-statistics, pacad);
  🚑-siffran räknar bara etablerade (≥5 matcher eller okänd), marginella
  listas i tooltip som "— marginell". Verifierat: Marqués 8 m/6.84,
  Boman 11 m/6.65.

## Modellplan — vägen till en modell att lita på (efter backtest-domen)

**Ersatt 2026-07-16 av den förregistrerade marknadsankrade v2-planen i
`docs/modell-v2-plan.md`. Punkterna M1–M5 nedan bevaras som historik.**

Backtesten visade: DC-modellen är nära marknaden i Allsvenskan men slår den inte,
och är svag i Eliteserien. Att slå Pinnacles STÄNGNING på 1X2 är fel mål — planen
är att vinna där marknaden är svag:

- **M1 — xG-viktad fit ✅ MÄTT (backtest v2, 2026-07-12)**: backfill klar
  (978 nya matcher; totalt ~574+390 med xG). Dom: **xG lyfter modellen i BÅDA
  ligorna** (logloss 1.029→1.022 Allsvenskan, 0.991→0.980 Eliteserien; bättre
  kalibrering). Allsvenskan blev t.o.m. lönsam vid låga trösklar: **+13,4 % ROI
  vid edge ≥2 % (n=326), +10,4 % vid ≥5 %** mot Pinnacle-stängning — MEN bara
  ~1,4σ från noll (snittodds ~4) = inom bruset, och ≥8 % vänder negativt
  (modellens största avvikelser är dess största fel). Eliteserien fortsatt
  giftig (−16..−20 %). rho-grid: −0.01/−0.04 bekräftad. Beslut: amber kvarstår,
  modell-loggtröskeln sänkt till 2 % (2–8 %-bandet är det intressanta) så
  forward-facitet (M3) byggs snabbare.
- **M2 — Elo-prior för tunna lag ✅ (2026-07-12)**: lag som saknas i fitten eller
  har <8 viktade matcher får styrkor ur ClubElo relativt liga-medlet
  (q = 10^(Δelo/400); att = q^0.35, def = q^−0.35; tunna lag blandas
  proportionellt). `_ensure_priors` i oddset_model; ⚠-not i M-radens tooltip
  (`model.prior`). Grov mappning — forward-loggen utvärderar även denna.
- **M3 — forward-test i produktion (IGÅNG)**: modell-flaggor loggas live
  (tier='model', aldrig notis/spel) och jämförs med Pinnacle-stängningen.
  **Grönt-kriteriet per liga: ≥50 stängda modell-flaggor med positivt snitt
  close-EV.** Facitet avgör — inte känsla, inte backtest ensam.
- **M4 — marknader där böcker är slöa**: modellens realistiska nisch är inte
  Pinnacles 1X2 utan (a) tidiga linjer innan sharpen öppnat (redan synligt:
  modell + Elo finns för nästa omgång före Pinnacle), (b) hörnor/lagmål där
  vi har egen Sofascore-data, (c) mindre ligor. **Superettan TILLAGD som liga
  (2026-07-12)**: Pinnacle 2476 + Kambi `football/sweden/superettan` + Altenar
  4825 + Sofascore ut 46 (MED xG!); ingen football-data → Sofascore är
  resultatkälla (MODEL_LEAGUES-gaten). Egen flik, full värdemotor + modell.
- **M5 — blend som referens**: backtesten fann w=0.1 modell + 0.9 marknad ≥
  marknaden ensam i Allsvenskan — modellen bär EN nypa egen information.
  När M1–M2 höjt den kan blenden bli "husets fair" för matcher med tunn sharp.

## Beslut (Saman, 2026-07-12)

1. **Startpunkt:** kopia av svs som bas — poolspelen funkar dag 1, vm-moduler portas in.
2. **Datakällor:** enbart gratis. Undersök även återanvändbara öppna källor som Flashscore
   och ligornas officiella sajter. Rena betalspår (the-odds-api betald, API-Football) =
   framtida projekt.
3. **Framtid:** svs fryses (bara kritiska fixar) när spelkompisen nått paritet.
4. **Namn:** spelkompisen, katalog `/Users/saman/spelkompisen`.

## Mål

Behålla hela poolspels-analysen (Stryktipset/Europatipset/Topptipset/Bomben) och lägga
till en **Oddset-del**: enskilda matcher i tidsordning (visa/dölj ligor) med aktuella odds,
oddsrörelser, sharp-jämförelse och tips — 1X2, asian handicap, asian över/under, hörnor.
Start-ligor: **Allsvenskan, norska Eliteserien, träningsmatcher**. Tips kommer från två
håll: (a) snabba oddsrörelser där någon bok hänger efter (paradexempel: träningsmatch
där lineups läcker och sharpen rör sig före svenska böcker), (b) egen modell (styrkor,
xG-proxy, form, skador) — alltid med vm-lärdomen: modell utan sharp-ankare = amber-tier.

## Etapper

### Etapp 0 — Skelett ✅ (2026-07-12)
Klon, portar (backend 8002, frontend 5175, preview 5181), venv, DB-seed, namnbyte,
Oddset-flik (platshållare), detta dokument, CLAUDE.md omskriven.

### Etapp 1 — Matchlista + odds ✅ (2026-07-12)
- Porta från vm: `pinnacle.py`-utökningarna (matchups + straight för AH/ÖU, inte bara
  moneyline), Kambi-klienten (operator `svenskaspel`, listView + betoffer per event),
  `odds_snapshot`-tabellen med dedup (skriv bara när odds/linje ändrats) och `movement()`.
- Ligaupptäckt Pinnacle: VERIFIERAT (prober nedan) — Allsvenskan 1728, Eliteserien 2333,
  Club Friendlies 1863 (+ 1864 dam). Bygg ändå en `LEAGUES`-tabell (id, namn, Kambi-väg,
  ESPN-slug) så fler ligor bara är en rad till.
- Kambi-vägar: VERIFIERAT — `listView/football/sweden/allsvenskan`,
  `.../norway/eliteserien`, `.../club_friendly_matches` (alla 200; `football/matches` finns EJ).
- Matchnyckel: klubblag, inte landslag → matchning på normaliserat lagnamn + avsparkstid
  (vm:s iso2-matchning funkar inte för klubbar; kolla `names.py`-mönstret + fuzzy).
- Backend: `oddset_matches`-tabell + `/api/oddset/matches` (tidsordnad, liga-filter),
  `/api/oddset/match/{id}` (odds + rörelseserie).
- UI: matchlista i tidsordning, visa/dölj ligor (sparas i localStorage), odds + rörelse
  (samma hover-punktserie-mekanik som analysvyn), flaggor/loggor där de finns.
- Launchd: `com.saman.spelkompisen.snapshot` (30 min; förtäta nära avspark som svs
  snapshot-smart). Saman kör `launchctl load` själv.

### Etapp 2 — Värde + steam + notiser ✅ (2026-07-12)
- Porta `value.py`-mönstret: power-devigad Pinnacle = fair; edge mot Svenska Spel (Kambi)
  per marknad. AH/ÖU jämförs ENDAST på samma linje.
- Steam i devigade procentenheter (6/24/72 h) per match/marknad; 🔥-flaggor i listan.
- ntfy-notiser: (a) sharp-edge ≥ tröskel, (b) snabb sharp-rörelse nära avspark —
  träningsmatch-caset: Pinnacle flyttar ≥X pp inom 30–60 min medan Kambi står still →
  notis medan det höga oddset lever. EGET NTFY_TOPIC (inte svs:s).
- CLV-logg från dag 1 (first/best, stängning = sista devigade Pinnacle före avspark) —
  bara sharp-ankrade flaggor får logga.

### Etapp 3 — Egen modell ✅ (2026-07-12)
- Datainsamling per liga: resultat, tabeller, form. Kandidater: ESPN (`swe.1`, `nor.1` —
  scoreboard + `/summary` med skott/hörnor/possession), football-data.co.uk (SWE.csv,
  NOR.csv — resultat + historiska odds, perfekt backtest-facit), ClubElo (klubbstyrkor,
  täcker nordiska ligor).
- ~~Undersök fler källor~~ GJORT 2026-07-12 (se Prober): **Sofascore = xG-källan**
  (Playwright-hämtare); Flashscore/FBref/FotMob/football-data.org skippas (detaljer i
  källtabellen); allsvenskan.se kvar som lågprio-spår.
- Modell: xG-viktad Poisson-styrkefit per liga med DC-korrektion i prediktionen
  (vm:s `model.py` som bas; rho refittas för klubbfotboll,
  vm fann −0.04 landslag vs litteraturens −0.13 klubbar), hemmafördel per liga,
  ClubElo som prior/korsreferens. **xG från Sofascore** som primär offensiv-/defensiv-
  styrkesignal; ESPN-skottdata som fallback-proxy.
- μ kalibreras mot devigad sharp ÖU-linje där Pinnacle finns (linje ≈ median, inte medel).
- Output: modell-tips som AMBER-tier (bakom toggle, UR CLV) tills backtest (Etapp 5)
  visar att de håller. Sharp-ankrade tips förblir enda gröna.
- Träningsmatcher: modellen får låg vikt (rotationsrisk) — där är steam/lineup-signalen
  (Etapp 2/4) huvudverktyget.

### Etapp 4 — Skador, lineups, nyheter ⛔ SKIPPAD (beslut 2026-07-12: steam täcker caset)
- Google News RSS per lag/match (vm-mönstret: sv+en, dedup, cap).
- X syndication-flödet (vm `twitter.py`): klubbkonton + relevanta journalister; 429-paca.
- Lineup-bevakning: källa oklar — undersök gratis-vägar (klubbarnas konton är mest
  realistiskt; strukturerade lineups utan betal-API är svårt). Kopplas till notiserna:
  "lineup-nyhet + sharp-rörelse + bok står still" är guldsignalen för träningsmatcher.
- Skador: nyhetsbaserat (fritext-flaggor per lag), inte strukturerad data (betalspår).

### Etapp 5 — Backtest + kalibrering ✅ (2026-07-12 — resultat i STATUS-blocket)
- football-data.co.uk SWE/NOR: modell mot historiska stängningsodds — samma beslutsregel-
  validering som svs backtest. Kalibrera trösklar (edge-%, steam-pp) innan de blir "gröna".
- CLV-uppföljning: håller flaggorna mot stängningslinjen? (Facit växer från Etapp 2.)
- Först härefter kan modell-tips ev. flyttas från amber till grönt, marknad för marknad.

### Senare / backlog

- ~~Cross-liga-fit~~ ✅ KLAR (2026-07-12): fit_league tar nu rader från flera
  ligor — lagstyrkor delas, base + hemmafördel per liga (FIT_POOLS: Allsvenskan
  + Superettan = Sverige-pool; Eliteserien egen). Backtest v3 (xG + pool,
  Allsvenskan): samma precision (logloss 1.0216 vs 1.0217) men **+8 matcher
  täckta** = nyuppflyttades matcher som tidigare saknade prediktion. Behållen.
- **Hörn-förväntan (M4b)** ✅ (2026-07-12): `corner_model` per liga ur egen
  Sofascore-data (~1400 matcher med hörnor): liga-snitt-total + hemmaandel ~
  xG-supremacy (OLS). Visas som M-rad i Hörnor-kolumnen (modell-toggle).
  ENDAST förväntan — inga pills/logg (vm-lärdomen: hörn-värde kräver sharp linje).
  OBS: ClubElo täcker bara ~7/23 Superettan-lag, så M2-priorn når inte alla där.
- Hörnor: Pinnacle hörn-specials (units='Corners', ~nära avspark) = sharp referens;
  vm-lärdomen: totalen är nästan konstant (~8.5–10.6), lag-hörnor följer favoritskapet
  (0.507 + 0.108·supremacy, R²≈0.97) — lag-hörnor är den intressanta marknaden.
- Fler ligor (Superettan? Damallsvenskan? danska Superligaen?) när flödet är bevisat.
- Polymarket som andra sharp-källa (tunn täckning klubbfotboll — låg prio).
- Menyn: gruppera flikarna (Poolspel: Stryk/Europa/Topp/Bomben | Oddset) om det blir trångt.
- Betalspår (framtida projekt): the-odds-api betald (multi-book), API-Football (skador/
  lineups/xG strukturerat).

## Datakällor (gratis) — status

| Källa | Vad | Status |
|---|---|---|
| Pinnacle Arcadia | sharp 1X2/AH/ÖU (+hörn-specials nära avspark) | ✅ verifierad 2026-07-12 (liga-id:n nedan); Cloudflare-block i perioder, IP-nivå |
| Kambi (operator svenskaspel) | Svenska Spels sportsbok, alla marknader, milliodds | ✅ verifierad 2026-07-12 — vägar nedan |
| ESPN | scoreboard/tabeller/matchstats (skott, hörnor) för swe.1/nor.1 | ✅ verifierad 2026-07-12 — 5 matcher/liga i svaret |
| football-data.co.uk | historiska resultat + odds SWE/NOR | ✅ verifierad 2026-07-12 — `new/SWE.csv`/`new/NOR.csv`, Pinnacle-stängning (PSC*) sedan 2012 |
| ClubElo | klubbstyrkor, gratis API | ✅ verifierad 2026-07-12 — `api.clubelo.com/Hammarby` ger full historik; vm har `elo.py` |
| Google News RSS | nyheter per lag | ✅ beprövad (vm) |
| X syndication | klubbkontons flöden | ✅ beprövad (vm), 429-känslig |
| **Sofascore (browser-kontext)** | **xG (!), hörnor, 43 statfält/match** för Allsvenskan & Eliteserien | ✅ verifierad 2026-07-12 — curl får 403 men riktig browser passerar; kräver Playwright-hämtare (mönster: `vm/tools/opta_token.py`). Detaljer under Prober. |
| Flashscore | live/odds/lineups (inofficiellt) | 🟡 feed-endpointen svarar (200 med `x-fsign: SW9D1eZo`) men formatet kräver reverse-engineering — nedprioriterad nu när Sofascore ger xG |
| allsvenskan.se / eliteserien.no | officiell statistik | 🟡 WordPress med wp-json — undersök vid behov, låg prio |
| FBref (browser-kontext) | tabeller/grundstats | 🟡 browser passerar Cloudflare (verifierat) men INGEN xG för Allsvenskan (22 tabeller kollade) — lågt värde, skippa |
| Blockerade (omtestade 2026-07-12 från hemma-IP, slösa inte tid) | FotMob (gamla API:t 404:ar — kräver signerad `x-mas`-header numera), football-data.org (Allsvenskan i katalogen men datat kräver betald tier), Opta-webben (Akamai) | ⛔ — men Opta performfeeds data-API var öppet (showcase-outlet, `vm/backend/app/opta.py`) |
| ASA (American Soccer Analysis) | MLS: xG/xPass/Goals Added/löner/domare/arenor — oberoende MLS-kvalitetskontroll | 🔴 certfel 2026-07-13 (hostname mismatch, både httpx & Chrome-TLS) — verifiera åtkomst innan planering (WP9a). Blanda aldrig providers' xG i samma fält. |
| Sofascore shotmap | shot-xG + xGOT per skott | ✅ probat 2026-07-13: Eliteserien 30/30 skott med xG — Allsvenskan 0/31 (fältet saknas för SWE). Coverage-matrix (WP9b) innan features byggs. |
| Sofascore team-events | lagets ALLA tävlingar (cup/Europa) | 🟡 ej probat — nyckeln till vilodagar/resor utan cup-blindhet (WP9c) |
| Open-Meteo Historical Forecast | väder med äkta point-in-time-prognoser | 🟡 dokumenterat gratis-API; liten väntad effekt → P2 |
| Betfair Historical | exchange-stängningar | ⛔ skip tills konkret behov — kontokrav, marginell nytta över Pinnacle-close för våra ligor |

## Kända risker

- ~~xG för Allsvenskan/Eliteserien saknar gratiskälla~~ **LÖST 2026-07-12**: Sofascore har
  xG för båda ligorna, åtkomlig i browser-kontext (se Prober) — kräver Playwright-hämtare,
  vilket är ett nytt beroende (browser i insamlingskedjan = skörare än ren httpx; ESPN-
  skottproxy kvarstår som fallback om Sofascore stänger).
- Pinnacles täckning av träningsmatcher varierar (stora klubbar ok, mindre = tunt eller
  bara nära avspark) — utan sharp-ankare blir de matcherna steam/nyhets-drivna, inte modell.
- Klubbnamnsmatchning (Pinnacle ↔ Kambi ↔ ESPN ↔ ClubElo) är mer jobb än landslags-iso2 —
  bygg en `team_alias`-tabell tidigt, den behövs i varje etapp.

## Prober (körda 2026-07-12 — Etapp 1 kan lita på dessa)

- **Pinnacle** `GET /0.1/sports/29/leagues?all=false` (guest-key): Allsvenskan = **1728**
  (6 matchups), Eliteserien = **2333** (5), Club Friendlies = **1863** (11),
  Club Friendlies Women = 1864. Matchups per liga: `/0.1/leagues/{id}/matchups`
  + `/0.1/sports/29/markets/straight` (vm-mönstret).
- **Kambi** (operator svenskaspel, `eu-offering-api.kambicdn.com/offering/v2018/svenskaspel`):
  `listView/football/sweden/allsvenskan.json` ✅ (9 events), `.../norway/eliteserien.json` ✅,
  `.../club_friendly_matches.json` ✅. `football/matches.json` = 404.
  Param: `?lang=sv_SE&market=SE`. Per match: `betoffer/event/{id}.json`.
- **ESPN**: `site.api.espn.com/apis/site/v2/sports/soccer/{swe.1|nor.1}/scoreboard` ✅
  (dagens omgång komplett, korrekta avsparkstider). Matchstats via `/summary?event=` (vm-mönstret).
- **football-data.co.uk**: `www.football-data.co.uk/new/{SWE|NOR}.csv` ✅ — kolumner
  PSCH/PSCD/PSCA (Pinnacle closing), Max/Avg, säsonger från 2012. Perfekt backtest-facit.
- **ClubElo**: `api.clubelo.com/{Klubbnamn}` ✅ (CSV, full historik; namnformat utan å/ä/ö
  — alias-tabellen behövs här också).
- **Sofascore** (omtestad från hemma-IP 81.234.x, Telia — vm:s 403-tester gick via VPN):
  `api.sofascore.com` ger 403 för curl ÄVEN från hemma-IP (bot-skydd på klientnivå), men
  **riktig browser passerar**: `www.sofascore.com/api/v1/...` ger ren JSON i browser-kontext.
  Verifierade id:n: Allsvenskan = unique-tournament **40** (säsong 2026 = **87925**),
  Eliteserien = **20**. Flöde: `/unique-tournament/{ut}/seasons` →
  `/unique-tournament/{ut}/season/{sid}/events/last/{page}` →
  `/event/{id}/statistics` — innehåller **"Expected goals"** (verifierat: Örgryte–Häcken
  4–3, 2026-07-11 → xG 1.48–1.78) + Corner kicks + 41 fält till.
  Implementeras som Playwright-hämtare i Etapp 3 (körs efter avslutad omgång, ~16 matcher/
  vecka totalt — snällt tempo, paca anropen).
- **FBref**: curl 403, browser passerar Cloudflare — men INGEN xG för Allsvenskan
  (alla 22 tabeller sakna xG-kolumner). Skippa.
- **FotMob**: gamla `/api/leagues` är borta (404, HTML tillbaka) — nutida API kräver
  signerad `x-mas`-header. Skippa (Sofascore täcker behovet).
- **Flashscore**: `d.flashscore.com/x/feed/...` svarar 200 med header `x-fsign: SW9D1eZo`
  — åtkomsten finns men feed-formatet är odokumenterat teckenprotokoll. Nedprioriterad.
- **football-data.org**: `/v4/competitions` listar Allsvenskan (188 ligor, utan token) men
  match-datat svarar "check your subscription" — gratis-tiern täcker inte våra ligor. Skippa.

## Portar & processer

| Projekt | Backend | Frontend | Preview | launchd |
|---|---|---|---|---|
| svs (fryses på sikt) | 8000 | 5173 | 5180 | com.saman.svs.snapshot (kör kvar, matar svs) |
| vm (Boll boll kollen) | 8001 | 5174 | — | com.saman.vm.* (5 jobb) |
| **spelkompisen** | **8002** | **5175** | **5181** | inga ännu → com.saman.spelkompisen.* i Etapp 1 |
