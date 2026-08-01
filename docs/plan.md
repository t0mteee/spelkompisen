# Spelkompisen — färdplan

## STATUS-SAMMANFATTNING (2026-08-01 — läs detta först i ny session)

> **Aktiv backlog och prioritering: `docs/backlog.md`** (2026-07-26).
> WP-listan längre ned är historik över avslutat arbete.

**FLASHSCORE ÄR RADARNS PRIMÄRA STATISTIKKÄLLA (2026-08-01, Samans beslut).**
Saman såg att Chelsea–Tottenham saknade chansdata hos oss. Utredningen visade
att varken FotMob (tomt stats-block, tom shotmap) eller Sofascore (bara
innehav/hörnor/kort) hade siffror — men Flashscore hade full xG, xGOT, skott
och stora chanser. Mätning över alla samtidiga livematcher: Flashscore hade
xG där FotMob bara hade skott eller ingenting, aldrig sämre. Ny `app/
flashscore.py` + egen tabell `oddset_live_flashscore`; källvalet rankar
DATAKVALITET först och låter Flashscore vinna vid lika, så en match där
FotMob har xG aldrig nedgraderas. Signalversionen bumpad till
`chance-gap-shadow-v3` (trösklarna oförändrade — men kohortens
datagenererande process ändras av en ny källa). Provider-id är nu
ogenomskinlig sträng överallt (Flashscores är alfanumeriskt); `provider_
event_id` byggd om till TEXT med bevarade rader. 412 tester gröna, migration
med backup + reparerad FK-incident (se `docs/db-atgarder.md`), verifierat i
browser: Flashscore bär två av tre livekort och Östersund–Öster gick från
dold till synlig. Metod: `docs/live-radar-2026-07-25.md`.

**SIGNALJOURNALEN GRANSKAD OCH HÄRDAD (2026-08-01, Fable 5).**
Multi-agent-granskning av 38a45ff gav 17 verifierade fynd — alla åtgärdade
samma dag, innan serien hunnit växa (1 rad fanns, intakt). Kritiskt: Kambis
betOffer-nivå-`suspended` spärras nu (utfallen kan stå OPEN under den —
livereproducerat; suspenderat pris kunde bokföras som spelbart och förorena
blindgatens ROI). Allvarligt: `match_key` är nu LÅST per fysisk match
(`_locked_key` — sen kanonisk länkning/källflip kunde dubblera blindkohorten)
och officiellt FT-resultat bevisar numera BÅDA utfallen för fler-mål-före-FT
(bara sanna ettor censurerades → nedåtbias). Dessutom: `suspended` som eget
statusvärde (kräver OBSERVERAD stängning, ≠ `not_offered`), per-rad-
tidsstämplar, klockproveniens `clock_source`/`clock_observed_at` — journalen
speglar exakt signalens per-fält-beräkningsbas (migration + backup + DB-
logg), capture-fel syns i launchd-loggen, `ag=NULL`-krasch vaktad, svensk
facit-enum i Labb, migration validerar FÖRE mutation inkl. UNIQUE-vakten.
Fixarna verifierades adversariellt av tre oberoende skeptiker som fällde och
skärpte tre av dem (lås-spärrar mot U23-falskmerge/dubbelmöten/spegling,
per-fält-klocka, migrationsatomicitet). 390 tester gröna (27 nya), API + UI
verifierade. Full rapport: `docs/granskning-codex-38a45ff-2026-08-01.md`.

**LIVE-RADARNS SIGNALJOURNAL OCH BLINDFACIT BYGGT (2026-07-31, Codex).**
Råcapture-/kontrollgruppsfacitet fanns redan; nu sparas dessutom exakt den
första synliga Följer- respektive Stark-signalen per match × typ, med minut,
ställning, provider/version, xG-/skottmått, samtidigt observerad öppen
SvS/Kambi-huvudlina för live Ö/U samt separat oddsobservationstid. Suspenderat
eller saknat pris loggas som saknat, aldrig som spelbart, och livepriser kan
inte förorena prematchtabellen. Efter matchen sparas normaltidsresultat, mål
efter signalen, mål inom nästa 15 matchminuter, fler mål före full tid och
korrekt Asian-Över-resultat inklusive kvartslinjer. Labb visar alla trösklar,
nivåfacit och detaljerad journal. Blindkohorten är fryst till första aktiva
signalen per match och får först ge stöd vid ≥200 oddssatta+avgjorda matcher,
≥60 dagar och undre KI90 > 0. Allt är shadow; inga tips/notiser/system ändras.
Additiv migration + backup + DB-logg klara; inga historiska liveodds
bakfyllda. 363 backendtester och frontend-build gröna. Metod:
`docs/live-radar-2026-07-25.md`.

**ODDSET-UI REFRESH KLAR (2026-07-30, Claude E1 + Codex E2–E7).**
Oddset är nu fyra persisterade sub-tabbar: Matcher, Live, Värdespel och
Rörelser, med en alltid synlig räknarrad. Desktop visar sorterbara
jämförelsetabeller; vid ≤760 px används samma sortering över mobilkort.
Huvudtabellen och marknadsradarn är också sorterbara. Prognosledger,
modell-mot-close, gruppgrindar och hela signalloggen har flyttats till Labb;
loggen laddas 200 rader i taget. Vald flik och sortering överlever omladdning.
Matcher-fliken har dessutom ett persisterat val för att dölja redan startade
matcher; Live och signalflikarna påverkas inte.
Verifierat i browser på 1280/390 px, frontend-build grön och 351 backendtester
gröna. Arbetsplan och verifiering: `docs/ui-oddset-tabbar-2026-07-29.md`.

**MODELLPLANEN P1–P6 KÖRD (2026-07-28 kväll, Fable 5, Samans "kör
samtliga i ordning"; detaljer + avvikelser i backlog.md:s MODELLPLAN).**
Kärnpunkter för nästa session: (1) **κ nu i ALLA tre värderingsvägar**
(builder + evalRows + pool_mc `kappa_by_tier`) — PH4 äger mätningen, dess
gate (≥40 OOT-omgångar efter 24/7) styr nästa steg. (2) **Utfalls-facit**:
`oddset_value_log.outcome` settlas via `resolve_outcomes` (1X2,
modellspårets join); `RESULT_ONLY_UT` ger cuper/bestadeild/friendlies
resultat via Sofascore (normaltid, inga statistik-anrop, SOFA_UT ORÖRD).
Skarpt: 370 resultat, 176 settlade, resultat-ROI −1,6 % (träff 34 %) mot
close-EV +2,5 % — close-EV äger grindarna, 🎯-raden är display.
(3) **Omsättningsprognosen** veckodagsviktad ur lokala settlementlagret
(`projection_basis` i /api/payouts; Europatipset to 7,36 M mot blandade
4,33 M; 0 nätverk). (4) `TEAM_ALIASES` i norm_team (IBV); SPEGELPAR i
odds-flödet upptäckta = egen designpunkt (teckenspegling krävs — bygg
inte utan förregistrering). (5) PH5:s Hamming-fråga förregistrerad
(`docs/ph5-hamming-forregistrering-2026-07-28.md`), arm i scriptet,
fullkörning 256/512 KLAR 29/7: grinden passeras INTE (endast Stryk-256
signifikant, gränsfall; slump ej klart sämst) — ingen byggaråtgärd,
dom i förregistreringsdokumentet. (6) UI: 🎯 resultat-ROI + 🌡 kalibrering i Signal-loggen,
prognosgrund-tooltip; 🧬 MODELLHÄLSA-kort i Labb (utfalls-facit,
prognosfel per produkt/metod, PH4-OOT-räknare) via /api/pool/
turnover-prognos. Prognos-METODVALET är datadrivet per produkt —
backtesten fångade att veckodag förlorar stort för dagliga produkter
(topptipset 173 % mot 43 %); blandad median väljs då automatiskt. 351 tester gröna. OBS: test_book_cdn_age är
nätverksflaky (Smarkets-anrop i collect — fix-chip skapad).

**EUROPACUPERNA INLAGDA (LIGA 8–10) + FOTMOB PRIMÄR LIVEKÄLLA (2026-07-28,
Fable 5, Samans beställningar).** (1) **FotMob är radarns primära källa**
(Sofascore reserv — bär signalen bara med strikt bättre statistik; körs
efter FotMob i `_live_pass`, båda med eget skyddsnät). FotMob täcker nu
även Oddset-spärrade friendlies via DELADE `live_radar.known_friendly`
(spegling 1↔2 — odds- och statskällor är oense om hemmalag på turnématcher,
Chelsea–WSW-fallet — plus `_same_team` i stället för exakt likhet: FotMob
kortar namnen). (2) **CL/EL/Conference INKL. kval**: cuperna är TVÅ
Pinnacle-ligor (2627/205451, 2630/2632, 214101/271382) och TVÅ Kambi-vägar
per nyckel — `pin_ids`/`kambi_paths` i oddset.py, batcharna stämplas med
sin EGEN observationstid (🕐 p.3). Smarkets: kvalslugs + Conference-huvudslug
OBSERVERADE, CL/EL-huvudslug mönsterhärledda tills ligafasen (september).
Sofascore lägger kvalet under huvudturneringens UT (verifierat) — 7/679/17015
direkt i radarns TARGET_UT, medvetet INTE i SOFA_UT (wp9c-fingeravtrycket,
samma som Besta deild). FotMobs SEPARATA kvalligor (10611/10613/10615)
mappade till samma nycklar. Sharp-ankrad väg utan modell; actionable.
(3) `_NOISE` utökad med föreningsformer (nk/gnk/hnk/kf/ks/pfc) — löste
dubbelkort i radarn (Sofascore "GNK Dinamo Zagreb" ↔ FotMob "Dinamo
Zagreb"). Liveverifierat 28/7 kväll under pågående CL-/ECL-kval: insamling
10+9+45 Pinnacle / 10+9+42 Kambi / Smarkets matchad, ~1024 oddsrader, 0 fel;
radarn visade kvalmatcher live med FotMob-xG; kommande cupmatcher får
SvS-odds + sharp + värde. Startade matcher får korrekt INGA odds
(live-odds-regeln). 342 tester gröna. Radartaken HÖJDA samma kväll
(Samans beslut): Sofascore 30→60, FotMob 20→60 — kvaltorsdagen 30/7 spelar
53 cupmatcher samtidigt och kvalen HAR chansdata (15/23 uppmätt), så gamla
"det som klipps döljs ändå"-argumentet höll inte längre. Sortering +
skipped-loggning kvar som skydd; isolationstestets gräns flyttad till 60.

**BESTA DEILD INLAGD SOM SJUNDE LIGA (2026-07-27 kväll, Fable 5, Samans
beställning).** Recon 30 min: Pinnacle 2102 ("Iceland - Premier League",
22 matchups), Kambi kör GAMLA vägen `football/iceland/urvalsdeild`
(besta_deildin = 404), Ninja/Altenar saknar ligan, Sofascore ut 188
VERIFIERAD fotboll men medvetet INTE i SOFA_UT (hade fraktuerat V2.2-
manifestet via wp9c-fingeravtrycket — kopplas vid nästa naturliga
omfrysning ⇒ ingen xG/frånvaro/WP9c för Island än). Smarkets visade sig
köra TVÅ aktiva slugs för ligan — LEAGUE_SLUGS är nu flervärdig (tupel).
Ingen modell (ingen football-data); ren sharp-ankrad väg och NY utforskande
facitgrupp (BH-FDR) — primärgrupperna orörda. Liveverifierad insamling:
2 Pinnacle- + 2 Kambi-matcher, Smarkets matchad, 31 oddsrader, 0 fel; ligan
syns i UI med Rek-kolumn. Känd skönhetsfläck: Kambis "ÍB Vestmennaeyjar"
mot Pinnacles "IBV" mergar inte (fuzzy vågar rätteligen inte efter
identitetssaneringen) — en dubblettrad för matchen 1/8; alias-mekanism för
förkortningar är en backlog-småpunkt, INTE en tröskelsänkning.
331 tester gröna.

**BACKLOGGEN KÖRD (2026-07-27, Fable 5 + två agenter, Samans order "kör
backloggen förutom ntfy").** (1) **Matchbook byggd i skugga**: öppen publik
väg bekräftad utan konton (källgränsen), 1X2-pris + likviditet i samma
observationstid, insamling enbart i 3h-snabbfönstret mot befintliga
identiteter (kollision ⇒ hoppa), ny tabell `oddset_matchbook_liquidity`
(migration + backup), sex ligor mappade. Aldrig i BOOKS/ankare — ny
`SHADOW_SOURCES`-spärr i attach_value + payload-strip. Liveprov: Häcken–AIK
1,90/4,30/4,00 (41/30/9 EUR — tunn likviditet dagar före avspark bekräftar
snabbfönster-designen). ≥ 28 dagars ren skugga före all användning.
(2) **Rek per match** (Samans beställning): "Rek"-kolumn i Oddset-vyn för
följda ligor (ej träningsmatcher/research — de visar inget), bästa
värdeselektion med nivå/OMTVISTAD eller nedtonad "avstå"; delade
`oddsetBestValue`/`oddsetValueTier` gör att 💰-korten, Idag-panelen och Rek
läser exakt samma urval. (3) **Rek-historik i matchdetaljen**: 📒-sektion ur
nya `/api/oddset/match-flags` med close-EV-pills och ⚓-markering — första
exemplet bekräftade OMTVISTAD-vakten skarpt (Karlsruher: close-EV −0,8 %
precis som Smarkets varnade). (4) **Bomben-spelläge**: rullpott-styrd pill.
(5) **STATUS-loggen komprimerad** (249 rader 07-13→24 till GAMMAL STATUS).
331 tester gröna, build grönt, browser-verifierat. NTFY fortsatt av på
Samans besked.

**CLOSE-DRIFT v2 — Ö/U-LINJEFLYTTAR REVERSERAR (2026-07-26 sen kväll,
Fable 5, godkänd insats).** Förregistrerad i
`docs/close-drift-facit-v2-2026-07-26.md` FÖRE körning. Tvåsidigt test av
linjeflytt h24→h3 på befintlig data (v1 exkluderade dessa — utfallen aldrig
granskade): **Ö/U-fortsättningsandel 23,6 % [15,3..31,9]** (72 vidareflyttade,
139 stilla) — tidiga totallineflyttar dras TILLBAKA; AH neutral 46,8 %.
Konsistent med v1:s prisreversering: Pinnacles tidiga Ö/U-rörelser
överreagerar. Reverseringshypotesen (a) samlar forward-kohort från
2026-07-26T21Z (veckokadens, ≥100 aktiva före tolkning); frånvaro (c)
utforskande utan signal. Före tips: forward-replikering, pris-EV-storlek och
vanliga trappan. Ingen runtime-ändring.

**ETT GRÄNSSNITT + BESLUTSSTÖD (2026-07-26 natt, Fable 5, Samans order).**
Klassiska v2-vyn är RIVEN (−412 rader; App.jsx är nu komponentbiblioteket,
AppV3 enda skalet — build/browser/311 tester gröna). Nya beslutsstöd, allt
ur befintliga tal: spelläge-pillret (jackpot—spela / tunt—spela smått /
avstå ur prognostiserat spelvärde + PH5-domen) i Poolspel-rubriken OCH på
Idag per spelform; 🎟 Dina kuponger-kort på Idag med livestatus
(avgjorda/bäst/vid liv); personligt kupongfacit (PlayedPanel) överst i
Historik. Direkt utfall: nästa Europatipset (omg 2594) flaggar GRÖNT —
spelvärde 110 % med 2 Mkr rullpott — medan dagens Topptipset säger avstå
(70 %). NTFY förblir avstängt på Samans besked. Rek-historik i
matchdetaljen kvar som småpunkt (kräver flags i detail-payloaden).

**PH5 256/512 KLAR — 13-MATCHSDOMEN: TÄTHETSBEROENDE MEN ALDRIG EN FÖRDEL
(2026-07-26 kväll, Fable 5, godkänd insats).** Förregistrerad uppföljning
körd (`docs/ph5-radvalsablation-256-512-2026-07-26.md`): underskottet mot
slump krymper monotont med budgeten (Stryk −8,2 → −5,0 → −2,3 pp; Europa
neutral) — gleshetshypotesen stämmer — men ingen spelbar budget (≤512 rader
= 0,03 % av utfallsrymden) vänder det till en fördel, och toppnivåträffarna
hamnar systematiskt hos favorit-/folkraden (2 mot 7/7 vid 512). Kontrast:
8-matchsprodukterna +7,7..+15,5 pp med KI > 0 vid 100 rader. Konsekvens
enligt förregistreringen: ärlig text i byggaren för Stryktipset/Europatipset
(ingen logikändring, levereras i v3-konsolideringen); gles-täckningsmetod är
en egen framtida förregistrering.

**LIVE-TÄCKNING + ODDSIDENTITET HÄRDADE (2026-07-26 em, Codex).**
Superettan-matchen GIF Sundsvall–Falkenberg doldes trots FotMob-skott eftersom
fallbacken krävde xG; nu väljs en hel providerserie enligt xG > skott/chansdata
> saknad statistik. Verifierat live vid 85': FotMob 10–7 skott, 5–3 på mål,
matchen synlig utan xG. En färsk FotMob-serie visas dessutom som ett eget
namespacat kort om Sofascore helt saknar matchen; stats får inte vara beroende
av att två providers först råkar länka. FotMobs xG vinner också i halvtid när
dess egen minut tillfälligt är tom; en länkad matchklocka får komplettera
metadata men aldrig blanda providers chansmått. Karlsruhe–Inter-kortets
+187–206 % var en bevisad
eventkrock med Novara–Internazionale U23: per-lagströskel, write-once/globalt
unika provider-id:n, per-varv-claims och `data_conflict`-karantän skyddar nu
alla signal-/modell-/facitvägar. DB-backup + skript körda; 34 bevisat
kolliderade matcher fick 30 value-loggar, 598 prediction-loggar/84 captures,
frånvarocaptures och 80 falska lokala notiser borttagna. Karlsruhe reparerad,
Novara egen rad, hela gamla Pinnacle-serien borttagen, DB-integritet ok.
`DATA_VERSION 2→3`; detaljer:
`docs/oddset-identitetsaudit-2026-07-26.md` och `docs/db-atgarder.md`.
Efter första nya korrekta Pinnacle-varvet separerades priserna bevisligen
(Karlsruhe 3,74/5,69/1,49; Novara 1,80/3,33/3,70). Karlsruhe har nu en riktig
Pinnacle-edge +25,6 %, men Smarkets säger −6,9 %; UI:t märker därför kortet
`OMTVISTAD EDGE`/⚓ utan att tyst promovera tvåankargaten.
Versionsutfall efter saneringen: aktiv sharp `s-95e14fca`, aktiv modell
`m-c4ee7c5d`; båda börjar samla i nästa capturefönster. Historiska rader finns
kvar under sina äldre versioner men räknas aldrig ihop med post-fix-facitet.
Tvåankarbeslutspaketet är nu ärligt nedjusterat till 13 mätta/9 stängda
(3/9 överlever båda ankare, ~7 dygn till volymkravet vid nuvarande takt).

**CLOSE-DRIFT-FACIT v1 KÖRT — MOMENTUM FALSIFIERAD, TIDIGA SKIFT REVERSERAR
(2026-07-26 kväll, Fable 5, godkänd insats).** Förregistrerat i
`docs/close-drift-facit-2026-07-26.md` FÖRE körning; 3 303 aktiva selektioner
ur prediction-ledgern. Ingen cell passerar gaten till en 🔮-driftradar.
Huvudfynd: h24→h3-momentum träffar UNDER 50 % med hela KI:t under för AH
(39,8 % [32,2..47,5]) och Ö/U (36,5 % [28,8..44,2]) — sharpens tidiga skift
tenderar att reversera mot close. Att vända hypotesen i efterhand är
forking-paths; en reverseringshypotes kräver EGEN förregistrering på ny
kohort. Driftmagnituderna på samma lina är små (±0,1–0,2 pp); för
parmarknaderna är LINJEBYTENA driften (~500 exkluderade selektioner) — v2
bör studera ⇄ ur alt-linjelagret. Frånvaro-cellen samlar (28 selektioner).
Ingen runtime-ändring.

**RADAR-SETTLEMENT LEVERERAD (2026-07-26 em, Codex-agent under Fable 5-granskning,
godkänd insats).** Alla capture-ögonblick settlas nu mot de två förregistrerade
utfallen (mål inom 15 min / fler mål före FT) med kontrollgrupp = icke-signal-
ögonblick och villkorad basrate liga × minutband × ställning; DELAD
signalfunktion `live_radar.radar_signal` (chance-gap-shadow-v2) — ingen andra
implementation. `cli.py radar-settle`/`radar-facit`, settling i `_live_pass`
(try/except, DB-only), append-once — settlade rader skrivs aldrig om.
302 tester gröna (10 nya). En incident redovisad + åtgärdad i
`docs/db-atgarder.md`: testsviten hann skriva 2 335 deterministiska
settlementrader i prod-DB före backup (raderna identiska med riktig körning,
lämnas; anropet flyttat så det inte kan upprepas; backup tagen i efterhand).
Första facitläsning (shadow, INGEN slutsats): xg-signalens 15-minutersutfall
32,7 % mot basrate 48,2 % — pekar hittills åt fel håll, i linje med
220-matchersprovet; utfall B degenererat tills slutstatus-captures finns.

**REKOMMENDATIONSPASSET (2026-07-26 em, Fable 5, godkänt av Saman).**
(1) **PH3-gaten förregistrerad** (`docs/ph3-gate-2026-07-26.md`): n ≥ 40
settlade timely omgångar, ≥ 60 dagars spann, winsoriserad KI > 0,
veckokadens; armarna frysta, rollover-fallet manuellt första gången.
(2) **Beslutspaketet för konsensus-gaten** (`backend/scripts/
tva_ankare_beslut.py`): kör förregistrerade tvåankarregeln + devigkonsensus +
coverage-kostnad i en läsning. Läge: SAMLAR — 8/50 mätta+stängda i
primärgruppen, ~8 dygn till beslutsvolym; tidig varning: ankarkravet hade
bara behållit 25 % av kohortens flaggor. (3) **startOdds-semantiken
VERIFIERAD OCH UPPLÅST** (`docs/startodds-semantik-2026-07-26.md`):
öppningsodds med tidiga engångsrevisioner (23 % av selektioner, median 4 %
in i observationsfönstret), inte stängning, trackar inte aktuellt odds;
result-API:ts version kanonisk. Användbar som omgångs-kovariat i
final_only-analyser över 8 278 omgångar — aldrig som PIT-observation (ingen
tidsstämpel). PH0-spärren hävd. (4) Radar-settlement byggs (separat post
när klar). (5) **Nytt föreslaget spår efter Samans closing-fråga:
close-drift-facit v1** — se backlogens 3b: förutspå sharpens drift till
close med befintliga signaler (steam-momentum, XI/frånvaro, vila,
ankar-lead-lag, ⇄, RLM) mätt offline i prediction-ledgern; 🔮-driftradar i
UI som shadow om prediktorerna håller.

**DEVIG-ABLATIONEN KLAR — FACITET ÄR INTE EN DEVIG-ARTEFAKT, MEN 24
POWER-FLAGGOR BÄR INGET VÄRDE (2026-07-26, Fable 5, godkänd insats).**
Förregistrerat i `docs/devig-ablation-2026-07-26.md` FÖRE körning; 172 stängda
sharp-1X2-flaggor/89 matcher, Pinnacle-trion rekonstruerad ur oddsserien
(sanity: median |Δ| mot lagrad first_fair 0,002 pp). Under proportionell
devigning överlever bara 125/172 (73 %), Shin 148/172. Huvudmåttet
(power-estimand för båda grupperna): **konsensusflaggor (alla tre metoder)
+4,40 % close-EV [+2,54..+6,14] mot bara-power-flaggornas −0,49 %
[−3,50..+2,45]**. Devig-tvetydighet är alltså en äkta filtersignal — samma
mönster som två ankare-mätningens första flagga. Ingen runtime-ändring:
eventuellt konsensusfilter tas som del av SAMMA signal_version-bump som två
ankare-gaten om den promoteras (en bump, inte två).

**PH3-SETTLEMENTAUDIT KLAR — MASKINERIET HÅLLER, SIFFRORNA FÅR INTE TOLKAS
(2026-07-26, Fable 5, godkänd insats).** 30 settlade system (24 topptipset/
6 topptipsetstryk, 5 omgångar) auditerade i `docs/ph3-settlementaudit-
2026-07-26.md`: correct_dist re-zippad mot settlement-kanonen och
utspädningen omräknad oberoende — **30/30 identiska**, alla timely, alla
payout_complete. ⚠ Rollover-vägen (0 vinnare på träffad nivå ⇒ okänd ROI) är
ännu oprövad av skarp data — verifiera manuellt första gången. ROI:erna
(−100 % på 50-kronorsarmarna, −68,5 % på ev256 över 4–5 omgångar) är brus vid
n=5 och citeras inte; ingen PH3-gate är förregistrerad än — skriv den innan
någon vill läsa ledgern som bevis.

**FIXPASSET F1–F5 GENOMFÖRT + DRIFTBUGG F5c HITTAD I TID (2026-07-26, Fable 5,
godkänt av Saman).** Alla granskningsfynd åtgärdade; 292 tester gröna (14 nya
regressionsfall), backend omstartad. F1: saknad Ö/U i Altenars lyckade
listsvar markerar nu priset unavailable (spökpriset borta). F2: SvS-deep
sparas med per-anropstid − Age. F3: Kambi-/Altenar-klienterna läser HTTP Age
defensivt (uppmätt: Kambi skickar inget Age-huvud, Altenar `max-age=3`) och
alla bokstämplar Age-justeras — "kvar"-bevisets cachefönster är nu ≤3 s.
F4: spelade kuponger settlar mot settlement-kanonen (`played-v2`: officiellt
outcome per eventNumber, events_order-join, hård breddvakt, struken match =
fastställt tecken; livevyn räknar struken/okänd som oavgjord). F5:
avsparkstider PIT-serialiseras i nya `oddset_sofa_team_event_start`
(migration + backup, 6 728 seedade rader), forward-självguard 6 h, och
wp9c-POLICY schema 3→4 fingeravtrycker statusomfång + forwardvikter — det
bumpar f22 och V2.2-manifestets egen change_policy gav då nytt manifest
`docs/model-v2.2-multileague-forward-manifest-v2.json`
(`v2.2-wp9c-multileague-v2`, start 2026-07-26T11:00Z; v1-raderna 07-23→26
kvar som historik under gammal shadow-version — de var redan fracturerade av
den tysta payloadändringen). **F5c, allvarligast, hittad under fixarbetet:**
capture-valideringen krävde `finished` medan insamlaren sedan 2026-07-25
skickar även scheduled/inprogress — varje lagcapture med kommande fixtur hade
kraschat tyst från ~16:26 i dag när 20h-TTL:n släppte, och rotationsriskdatat
hade ALDRIG flödat (0 scheduled-event sparade). Fångad innan driftsmällen;
efter fix gav force-refresh Allsvenskan 16/16 captures, 757 event varav 150
scheduled, 0 fel. Detaljer + backup: `docs/db-atgarder.md` (2026-07-26).

**GRANSKNING AV KVÄLLS-/NATTPASSET + NY BACKLOG (2026-07-26, Fable 5).**
Codex Altenar-/modell-mot-close-pass granskat: metodiken HÖLL — ANKARE ≠ BOK
intakt, ingen signalversions-drift (hörnversionen korrekt isolerad via
`fair_source`), modell-mot-close-implementationen matchar förregistreringen
punkt för punkt, Altenar-deep följer observationstidsregeln per event.
Fem bekräftade fel lades i backloggen (F1–F5, fil:rad där): (F1) bok-ÖU utan
else-gren markerar aldrig plockat ÖU-pris unavailable — draget pris kan
flaggas i upp till 45 min; (F2, förelåg före passet) SvS-deep sparas med
varvstart i stället för anropstid; (F3) "kvar"-etiketten läser inga
Age-huvuden på bokssidan — CDN-cachat svar kan "återbekräfta" (villkoret i
`oddset_value` är rätt, etiketten display-only); (F4) spelade kuponger settlar
mot draw-payloadens Current-score positionsvis (events_order oanvänd, tyst
trunkering, struken match = rätt för alla rader) i stället för
settlement-kanon — 0 kuponger bokförda, inget skadat, fixa före första
användning; (F5) rotationsrisk-upserten skriver över `start_at` (as-of-läsaren
tappar PIT vid ombokning) och v22-POLICY bumpades inte trots ändrad
wp9c-payload (whitelist skyddar modellfeatures — inget spelbart ändrat).
Kvällens tre commits (spelade kuponger, rotationsrisk, radar-förtätning)
saknade STATUS-poster — radar-förtätningen verifierad ren (ingen extra
Pinnacle-trafik, budgetmatten håller). Verifierat i övrigt: 278 tester gröna,
frontendbygge grönt, frysta manifest orörda, launchd + API friska, PH3 har nu
30/42 settlade system (auditens blockerare släppt). Dokumentstädning:
`docs/backlog.md` är enda aktiva backloggen (UTKAST tills Saman godkänt),
`forbattringar.md` arkiv, källtabellen/portar rättade (FotMob i drift,
Flashscore avförd), kallplanens tvåankarkrav pekar på den förregistrerade
regeln i `tva-ankare-2026-07-25.md`.

**ALTENAR SYNLIG + SPELBAR VÄRDEKÄLLA (2026-07-26, Codex).** `+ Fler odds`
visar nu Ninja/Altenar som `N` även för Ö/U och totalhörnor, inte bara 1X2.
Ninja döljs inte längre när 1X2 råkar vara identiskt med SvS eftersom Altenar
är en oberoende prismotor. Värdemotorn valde redan bästa färska bokpris mot
devigad Pinnacle; regressionstester låser nu att färska Ninja-hörn/ÖU kan
vinna bokvalet och att gamla priser exkluderas. En ny `kvar`-etikett är
striktare än vanlig färskhet: bokens oförändrade pris måste ha återbekräftats
**efter** Pinnacles senaste prisändring. Därmed betyder “Ninja bekräftat kvar”
ett observerat lagg, aldrig en gammal cache. Ö/U/hörnor kräver fortfarande
exakt samma lina (huvud- eller färsk Pinnacle-altlina). Ingen signalversion
ändrad: urval och edge-formel är oförändrade; detta synliggör källa och
observationsbevis.

**ALTENAR-HÖRNOR HITTAD OCH INKOPPLAD (2026-07-25, Codex).** Claude hade
korrekt konstaterat att `GetEvents` saknar hörnor, men eventdetaljen var inte
kartlagd. Den publika vägen `Widget/GetEventDetails?eventId=…` innehåller
marknadsgrupp `Hörnor` och `typeId=166` för totalt antal hörnor, med `isMB`
som markering av huvudlinan. Verifierat live på Brommapojkarna–Hammarby:
alternativa linor 7,5–11,5 och huvudlina 9,5 till 1,70/2,05. Ninja/Altenar
hämtar nu huvudlinan inom samma 7-dygns-/3-timmarsfönster som Kambi-deep;
varje event får egen observationstid, avstängda eller ofullständiga par
ignoreras och ett eventfel fäller inte ligan. Alternativlinorna sparas ännu
inte: nuvarande book-lager representerar ett par per marknad, och tecken från
olika linor får aldrig blandas. 278 backendtester gröna. Ingen signal-, modell-
eller dataversion ändrad — detta är en ny oberoende mjuk prisobservation, inte
en algoritmändring.

**NÄSTA MODELLORDNING KORRIGERAD AV SAMAN (2026-07-25).** Efter de nya
prispunkterna: (1) modell-mot-close-facit från hela prediction-ledgern, inte
bara sällsynta flaggor; (2) modelltransparens i matchvyn — modell mot sharp mot
SvS per marknad och pp-differenser; (3) hörnkalibrering sist med samma
close-mått. Förregistrerat mått och grind:
`docs/modell-mot-close-2026-07-25.md`. PH3/Smarkets/manifest var punkter ur en
äldre överlämning och är inte denna arbetsordning.

**MODELLORDNINGEN GENOMFÖRD (2026-07-25, Codex).** Måttet ovan är nu byggt
direkt på prediction-ledgern och visas i Oddset-vyn. Av 261 kompletta
modellvektorer kunde 213 paras säkert med direkt Pinnacle vid samma horisont,
marknad och exakta lina. Den äldre modellversionens 1X2 är redan fälld som
**sämre än sharp**: 103 cases, 48 matcher och 8 dagar; modellen låg i snitt
4,25 pp från close mot sharpens 1,68 pp och parad log-score-förbättring var
−0,0129 med 90 % KI [−0,0195..−0,0073]. Nuvarande version samlar ännu
(10 cases/5 matcher/0 dagar) och får inte tolkas trots negativt tidigt KI.
Ö/U är som väntat i princip identisk med sharp eftersom totalnivån är ankrad
dit. Matchtabellen visar nu marginalrensad modell/Pinnacle/SvS och differenser
i pp för 1X2, AH, Ö/U och hörnor; parmarknader jämförs bara på exakt samma
lina. Hörnens `corner-poisson-total-v1` fryses framåt i samma ledger/grind —
ingen bakfyllning med dagens modell. Full svit: 278 backendtester och
frontendbygge gröna; API och desktopvyn verifierade i drift.

**TVÅ ANKARE I SKUGGA + TRANSPORTFIX (2026-07-25 eftermiddag, Opus 5).**
Sharp-facitets `+2,4 % [1,0..3,8]` över 166 stängda (uppdaterat från +2,65 %/147
när fler flaggor stängt) kan i dag inte skiljas från ett devig-/ankarval: median
oenighet Pinnacle vs Smarkets är 1,12 pp och 11 % av selektionerna skiljer mer än
hela 2 %-tröskeln. Därför mäts nu ANDRA ANKARET i skugga —
`anchor2_source/_fair/_edge/_closing_fair/_note` på `oddset_value_log`, rapport i
`/api/oddset/clv` (`anchor2`) och en ⚓-rad i Signal-loggen. **Runtime är
oförändrat**: `SHARP_PARAMS` och `signal_version` orörda, så de stängda flaggorna
behåller sin facitgrupp. En riktig gate promoteras bara enligt den förregistrerade
regeln i `docs/tva-ankare-2026-07-25.md` (n ≥ 50 mätta+stängda i primärgruppen,
veckokadens, ≥ 1,0 pp bättre close-EV med undre KI > 0). Första mätta flaggan
visade caset direkt: Pinnacle-edge +2,6 % mot Smarkets −0,4 %. Takt 14–32 nya
1X2-flaggor/dygn ⇒ beslutsläge inom ~1 vecka.
Dessutom: **ANKARE ≠ BOK har nu ett test** (spärren fanns i kod men i inget av de
219 testfallen), och **brotli** ligger i `requirements.txt` — CloudFront svarar `br`
även på `Accept-Encoding: gzip`, så Betsson-bootstrapen dog i drift på en hel sida
medan fixturtesterna var gröna. Se 📦 TRANSPORTREGELN i CLAUDE.md. Betsson
omverifierad: context-details 200, events-table **403** — fortsatt parkerad.
Sviten är 226 tester grön.

**PH5 v2 KLAR — RADVALET SLÅR BASLINJERNA PÅ TOPPTIPSET, FALLER PÅ 13-MATCHS
(2026-07-25, Opus 5).** 3 976 omgångar. Sanity-kravet (slump ska ligga klart sämst)
**passerar på de tre 8-matchsprodukterna och faller på de två 13-matchs**:
* **Topptipset +7,7 pp mot favoritraden [+5,2..+10,2] och +8,5 pp mot folkrad
  [+6,1..+10,9]** (n=2 496) · **Extra +15,5/+14,7 pp** (n=523) · **Stryk +10,4/+9,5 pp**
  (n=229). Alla sex undre KI-gränser > 0, och vår metod har flest toppnivåträffar
  i alla tre (386 mot 273/263 i Topptipset). Regel 1 uppfylld: **radvalet gör
  verklig skillnad här.**
* **Stryktipset och Europatipset får INTE tolkas** (regel 3): vi förlorar mot slumpen
  (−8,2 pp [−15,4..−1,7]) och har **0 toppnivåträffar på 223 omgångar**. Orsaken är
  sannolikt täthet — 13 matcher = 1,6 M utfall, och 100 rader är 0,006 % av rymden
  mot ~1,5 % på Topptipsets 8 matcher. **Nästa körning: samma ablation vid 256 och
  512 rader.** Återvänder kravet med tätheten är slutsatsen budgetberoende och hör
  in i UI:t som varning; gör den inte det är värderad-metoden fel verktyg för
  13-matchsprodukter och det ska stå i byggaren.
Talen är PARADE DIFFERENSER mellan armar, inte förväntad ROI: alla armar ser
slutstrecket (ej PIT), medianen är +0,0 pp och vi "vinner" bara 10–17 % av
omgångarna — snitten drivs av minoriteten omgångar där något faller ut.
Per-omgångs-ROI ligger i `docs/ph5-radvalsablation-v2-2026-07-25.json` så
omkörningar aldrig behöver räkna om Topptipset-delen.

**PH5 v1 UNDERKÄNDES AV SITT EGET SANITY-KRAV (2026-07-25, Opus 5).**
Nytt spår som svarar på frågan PH3-ledgern inte kan besvara i tid (6 settlade system
i dag): slår vårt radval baslinjerna, mätt på 4 000 kompletta omgångar med faktiska
vinnarantal och utdelningar? `scripts/ph5_radvalsablation.py` anropar den RIKTIGA
`build_ev_system` på omgångar rekonstruerade ur settlementlagret — ingen tredje
EV-implementation — mot folkets rad, favoritraden och slumpen, alla med samma
information. Kohort `final_only`, hålls utanför pit-manifesten.
**v1:s förregistrerade sanity-krav ("slump ska ligga klart sämst") FÖLL i fyra av fem
produkter** — slump låg som mest +45,5 % med KI [−69,7..+197,7]. Slumpen var inte
bättre, den var tyngre i svansen: ROI per omgång är golvad vid −100 % och obegränsad
uppåt, så en enda toppvinst bär medelvärdet. Samma estimand-fälla som gav "+6,6 %"
när sanningen var +2,65 %. **Ingen ROI-slutsats får dras ur v1.**
v2 (specificerad före körning, motiverad av validitetsbrottet): PARAD differens per
omgång — omgångens tur delas av alla armar — winsoriserad ±200 pp, plus andel
omgångar vi vinner, plus per-omgångs-ROI sparad i JSON så omräkning aldrig kräver ny
1,5-timmarskörning. Provkörning: `vs slump +16,6 pp [+1,8..+32,1]`, KI utan noll i
rätt riktning. Läs `docs/ph5-radvalsablation-2026-07-25.md` INNAN någon läser
v1-siffrorna i `ph5-radvalsablation-2026-07-25.json`.

**PIT-v4 + RADARURVALET LAGAT (2026-07-25 kväll, Opus 5).** Samans beslut:
`pit-v4` med nytt manifest `docs/pool-ph4-forward-manifest-v3.json`
(`pool-streckmove-v3`) i stället för att skriva om pit-v3 — dess 71 featurerader
lämnas orörda som historik och hann aldrig forward-scoras. Toleranser,
featureuppsättningar, mått, seed och promotionsgrind är OFÖRÄNDRADE; enda tillägget
är `skipped_fetch_is_not_an_observation`. `ph4_ablationer` läser v3-manifestet och
testet som binder runtime till manifestet är uppdaterat.
Live-radarns urval hade två riktiga fel: (1) bara EN träningsturnering var mappad,
så England 20 / Bulgarien 11 / Polen 8 / Serbien 8 / Kroatien 5 / Tyskland 5 live
låg helt utanför radarn — nu mappade bakom samma Oddset-spärr; (2) `MAX_MATCHES=14`
delas av alla ligor och urvalet var *det Sofascore råkade lista först*, så 43
behöriga träningsmatcher kunde tränga ut Allsvenskan — nu riktiga ligor först,
därefter mest återstående speltid, och **vad som föll bort redovisas** i källhälsan
och radarns fotnot. Kortens dubbeltext bort (`reason` + `warning` sa samma sak
ovanpå en statsrad som redan visade siffrorna); proxyvarningen står nu en gång i
fotnoten. **Mätt om träningsmatcher: 0 av 56 har xG** (FotMob har 0 nycklar även
för Hoffenheim och Bologna — providerna täcker inte försäsong), 4 av 56 har skott,
50 av 56 har hörnor. Fler träningsmatcher på skärmen = fler kort utan
chansinformation; taket är inte begränsningen, datan är.
Källsvar: Betsson 403 på events-table i HELA koncernen (betsson.com/betsafe/
nordicbet; `.se` omdirigerar bara till `.com/sv`) — inget Saman kan göra utan att
exportera WAF-session. Flashscore 401 = avsiktlig grind och ger inget FotMob inte
redan ger ⇒ skippas. Opta gratis = renderade visualiseringar, feeds kräver betald
outlet-nyckel. Detaljer: `docs/live-kallor-2026-07-25.md`.

**FOTMOB SOM ANDRA LIVE-ÖGA (2026-07-25 eftermiddag, Opus 5).** Radarn var blind
just där vi spelar mest — Sofascore saknar xG helt för Allsvenskan, och den rena
skottproxyn har ett negativt facit. Recon av sju källor: FotMob ger live-xG, xGOT
och open/set-play för Allsvenskan OCH Eliteserien; ESPN ger skott/possession utan xG
(reserv); Flashscore svarar 401 utan privat `x-fsign` och Opta har ingen gratisväg —
båda skippas, gränsen mot anti-bot står kvar. `app/fotmob.py` + tabellen
`oddset_live_fotmob` + steg i `cli.py live-tick`. Verifierat live: Degerfors–Djurgården
65' fick xG 0,73–1,45 (Sofascore: tomt) och gick från "xG saknas · proxy" till
GRANSKA LIVE; på Eliteserien där båda källorna har xG är de **identiska** (0,36–0,08).
**xG blandas aldrig mellan providers**: egen tabell, och när FotMob används räknas
hela signalen inkl. 15-minutersdeltat i FotMobs egen serie (`signal.xg_source` säger
vilken källa som talar). Fortsatt shadow — inga tips, Kelly, notiser eller CLV.
Nio tester. Detaljer: `docs/live-kallor-2026-07-25.md`.

**m20-FRÅGAN AVGJORD — FALSK FRÅNVARO HITTAD (2026-07-25 eftermiddag, Opus 5).**
m20 skrivs INTE bort som scope: mätvärdet bakom "sharp kan strukturellt inte nå
10-minuterstoleransen" var en artefakt av vår egen dubbeltrafikspärr. Captures var i
tid överallt — det var PRISET som fattades, för `record_sharp_capture` bokförde
spärrens tomma svar (`skipped`, inget fel) som `not_listed`. **Före spärren: 0 tomma
sharp-ticks av 591. Efter: 228 av 435 (52 %).** Åtgärdat: överhoppad hämtning ger
ingen capture; `collect_pinnacle(force=…)` förbigår spärren enbart i ett öppet
horisontfönster (`pool_dataset.horizon_window_open`, max ett anrop per horisont och
omgång, toleranser oförändrade); `/api/external-odds` svarar `ej ompollad` i stället
för att påstå att Pinnacle inte listar matchen. Fyra regressionstester.
**ÖPPET FÖR SAMAN:** 2 240 falska `not_listed`-rader (2026-07-25) + 474 (07-24) ligger
kvar och `pit-v3`-features är beräknade på dem — där betyder `sharp_eligible=0` "vi
frågade inte". Välj A) rensa + räkna om pit-v3, eller B) bumpa till `pit-v4` med nytt
manifest (rekommenderat, kostar ~1 dygn, samma mönster som v2→v3).
Full analys: `docs/m20-och-falsk-franvaro-2026-07-25.md`.

**GRANSKNING AV CODEX-PASSET + FEM FIXAR (2026-07-25, Fable 5).** Codex arbete
(live-radar, CDN-fix, pit-v3, m20-kadens, Betsson) granskades kritiskt. Det
metodiska höll: pit-v3 startades som NYTT experiment i stället för att smyga in
ändrad datasemantik, gamla manifestet är verifierat orört, och Betsson håller
gränsen (ingen cookie-/WAF-replay, ej i BOOKS). Fem fel hittades och lagades:
1. **Ankarkontaminering (allvarligast).** Smarkets blev en bok i värdemotorn
   trots att den låg utanför BOOKS — `attach_value` använde "allt utom
   pinnacle". 192 felaktiga flaggor rensade med backup; ANCHOR_SOURCES-spärr
   införd. Facitet tillbaka på +2,65 % [1,19..4,11].
2. **Överkorrigering av CDN-Age** — drogs från varvets STARTTID, så sena ligor
   i en 25-minutersloop bakåtdaterades med Age plus hela insamlingstiden. Nu
   mot det egna anropets tid; gäller även Kambi, sidoböcker och Smarkets.
3. **Ingen monotonispärr** — olika CDN-noder kunde flytta färskhetsklockan
   bakåt och skapa falska rörelsepunkter. `MAX(last_seen_at, ?)`, och
   cacheobjekt äldre än senaste bekräftelse hoppas över helt.
4. **Radarn delade HTTP-klient med den spelbara xG-pipelinen** — egen klient,
   matchtak, tidsbudget, tidsstämpel per event, och proxy skild från xG i
   fältnamn och sortering.
5. **Dubbeltrafik mot Pinnacle** från två launchd-jobb — spärr på 10 min.
Ett agentfynd verifierades bort: radarfel kan INTE släcka Oddset-vyn.
Observationstidsregeln och ANKARE ≠ BOK står nu i CLAUDE.md — samma bugg hade
uppstått tre gånger på tre dygn.

**GRANSKNINGSFIXAR 2026-07-24 (Fable 5) — läs innan poolspels- eller
facitarbete.** En bred genomgång (kod + mätning mot settlementlagret) hittade
fyra fel som påverkade pengar och ett som påverkade slutsatser:
1. **Europatipset hade fel vinstplan** — 12-rätt kopierad från Stryktipset
   (0,15 mot uppmätta 0,22), potten underskattad 47 %. Rättad i PRIZE_PLANS.
2. **Spelvärdet var 5 pp för snällt** — splits summerar till 0,92/0,98, så
   faktisk återbetalning är 59,8 %/63,7 %, inte 65 %. `_payout_ratio` +
   break-even-hurdle (+67 %) visas nu i statusraden.
3. **Ensamvinnargarantin var osynlig** — `guaranteedJackpots` (10 Mkr på
   Stryk 4963) lästes aldrig. Parsas nu och visas, men går INTE in i EV
   förrän villkoren verifierats mot SvS regler.
4. **Strukna matcher helgarderades i onödan** — antagandet om återbetalning
   är empiriskt falskt (52,8 % favorittäffar mot 52,1 % i ostrukna; inga
   extra toppvinnare). Kostade 3× rader per struken match.
5. **CLV-facitet var för optimistiskt** — `LIMIT 300` gav ett rullande
   fönster, och det owinsoriserade snittet redovisades mot ett winsoriserat
   KI. Ärlig siffra över hela historiken: sharp **+2,65 % [1,19..4,11]**
   (147 stängda), inte +6,6 %. Statusbeslut är nu veckokadens i stället för
   varje varv (sekventiell testning), och censurerade linjeflyttar blockerar
   grönt när de dominerar.
Dessutom: κ per produkt/nivå ur PH4 är inkopplad i radvalet (sänker EV),
frontend fick backendens streck-golv och räknar mot prognostiserad
slutomsättning, och amber-modellen (−4,2 % close-EV) ger inte längre stöd
på värdekorten. Detaljer i commit 15c1d7c/bb9a412.
**Codex-uppföljning 2026-07-25:** Claude hade korrekt hittat att Pinnacles
HTTP `Age` bokfördes men inte användes. Nu gäller `observationstid =
hämtningstid − Age` i Oddset, altlinjer och pool-PIT; cacheobjekt äldre än
5 min öppnar inte notisgrinden. Liveprov: 23:15:31 − 338 s = 23:09:53,
63 DB-rader verifierade. Datasemantiken bumpades därför till `pit-v3` och
nytt orört manifest `docs/pool-ph4-forward-manifest-v2.json`;
`pool-streckmove-v1` hann aldrig forward-scoras. m20-hålet löses utan ändrad
tolerans genom separat pool-launchd var 5:e min, medan Oddset ligger på fasta
:00/:30. Full rapport: `docs/pool-pit-v3-2026-07-25.md`. Efter live-radarn
och käll-UI:t är hela sviten 212 tester grön.
**Codex-uppföljning 2 — källor + live-radar:** Altenar/Ninja och Smarkets
visas nu explicit i Odds-tabellen och källhälsan. Betssons `brandId` och
publika context-bootstrap är lösta och testade i `app/betsson.py`; dess
eventtabell kräver däremot fortfarande en CloudFront-browsersession, så
källan är inte inkopplad och skyddet ska inte kringgås. Coolbet är
Imperva-blockerad. Matchbook är nästa byggbara reservspår.
Genomförande och accepter finns i
`docs/bookmaker-kallplan-2026-07-25.md`.
Live-radarn är levererad i shadow mode: Sofascore live-xG/chansmått sparas
var femte minut, visas i Oddset och påverkar inga tips/notiser.
`docs/live-radar-2026-07-25.md` är metod- och settlementplanen.
**Appen är komplett och i drift** (backend 8002, frontend 5175; separata
launchd-jobb för Oddset och poolspel)
— och sedan 2026-07-20 **enda driften**: SvS kompisen (svs, 8000/5173) är pausad som
fryst arkiv efter verifierad total paritet (delad git-historik, svs sista commit
2026-07-02; poolspelsmotorn här är bättre via WP6). Halverar även Pinnacle-trafiken.
- **6 ligor**: Allsvenskan, Superettan, Eliteserien, OBOS-ligaen, MLS (nytt 2026-07-13),
  Träningsmatcher. Källor per match: SvS (Kambi), Pinnacle (sharp, AH/ÖU/hörnor),
  Expekt (Kambi expektse — ≈identisk med SvS, visas bara vid diff),
  Ninja Casino (Altenar; Betinia var sämre skin i jämförelsen).
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
- **Insamling (A1 ✅ 2026-07-13; kadensdelning 2026-07-25)**: launchd kör
  Oddsets `cli.py smart` på :00/:30 — fullt varv (alla källor + deep +
  modelldata), och därefter SNABBVARV
  var 4:e min så länge någon match startar inom 3 h (Pinnacle + böckernas 1X2
  för ligorna i fönstret samt SvS deep-marknader för just 3h-matcherna).
  Separat pooljobb går var 5:e min; `pool-tick` gör basvarv var 30:e min och
  varje tick när omgång stänger inom 2 h, varefter `live-tick` samlar
  shadowdata för pågående matcher.
- **EJ GJORT ÄNNU**: NTFY/notifieringsspåret **PAUSAT på Samans begäran
  2026-07-16** — notera: med notisvakt + källhälsa på plats är det säkert att
  återaktivera, och utan pushar tävlar systemet inte i latens mot manuell
  odds-inspektion; beslut om mobil-default för `Bara signaler` återstår;
  P1/P2-backloggen finns nedan. Europaligorna är inlagda som isolerade
  forskningsligor och är sedan 2026-07-24 synliga i vanliga Oddset-vyn
  (🔬, icke-actionable — se produktbeslutet ovan).

## Backlog (WP-struktur efter granskningen 2026-07-13 — HISTORIK; aktiv backlog i `docs/backlog.md`)

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
  (pytest-kompatibel, ingen dependency). 107 fall täcker bland annat
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
- **WP9c ✅ 2026-07-17**: Sofascore team-events (alla tävlingar per lag) ger
  PIT-säker vila, 7/14/30-dagars belastning och tydligt märkt basarena-reseproxy
  utan cup-blindhet. 94/94 arenor; 48/48 kommande matcher komplett. Samlas
  forward men är inte modellinput.

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
12. ✅ Facit per signalgrupp + candidate-ETA: aktuella primärgrupper har egna
    statuskort på desktop/mobil; tier-raden är endast aggregat utan grönt-✓.

**D. Stora ligorna — V2.2-research inlagt; UI-synlighet klar 2026-07-24.**
PL, Bundesliga, La Liga och Serie A samlas nu med Pinnacle/Kambi-1X2,
historiska topplige-/andradivisionsresultat, Elo och WP9c, och visas i vanliga
Oddset-vyn som 🔬-märkta forskningsligor. Synligheten är implementerad separat
från V2.2-actionability, notiser och CLV. Ligue 1 är inte inlagd.
| Liga | football-data | Sofascore ut | Kambi-väg | Pinnacle |
|---|---|---|---|---|
| MLS ✅ (inlagd, i säsong) | new/USA.csv | 242 | football/usa/mls | 2663 |
| Premier League ✅ research | mmz4281/{säsong}/E0.csv | 17 | football/england/premier_league | 1980 |
| Bundesliga ✅ research | .../D1.csv | 35 | football/germany/bundesliga | 1842 |
| La Liga ✅ research | .../SP1.csv | 8 | football/spain/la_liga | 2196 |
| Serie A ✅ research | .../I1.csv | 23 | football/italy/serie_a | 2436 |
| Ligue 1 | .../F1.csv | 34 | football/france/ligue_1 | proba |
OBS: huvudligornas filer ligger under mmz4281/-strukturen (inte new/) och
Div/FTHG/FTAG-formatet stöds nu av parsern. FÖRVÄNTNING: dessa
marknader är extremt effektiva — SvS/Pinnacle-gap blir mindre och stängs fortare;
värdet sitter i tidiga linjer + mindre marknader. Kärnvärdet förblir Norden/MLS.
Verifiera alltid Sofascore-id:ns SPORT (handbolls-läxan).

**E. Infra/övrigt**
12. NTFY/notifieringar — pausat 2026-07-16; återuppta först när Saman ber om det.
13. Betsson (egen oddsmotor) — `brandId`/OBG-kontext löst; eventtabellen
    CloudFront-blockerad utanför browser, ingen cookie-/WAF-replay.
14. Servermigrering (Pi 5/N100, launchd→systemd) — beslut öppet sedan tidigare.
15. Altenar-champ för träningsmatcher/MLS hos Betinia (GetSportMenu-sväng).

## GAMMAL STATUS (historik — nyaste överst)

### Avslutade milstolpar 2026-07-13 → 2026-07-24 (flyttade ur STATUS 2026-07-27 — backlogpunkt C6)

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
- **Kvalitetspaket + Backtest v4 klart (2026-07-16; 107 tester efter WP9c):** tester täcker nu även
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
  **Separat V2.2-flerligeförsök startat 2026-07-23:** V2.1 förblir stoppad.
  Allsvenskan-only-manifestet hann få 0 rader och ersattes före första
  observationen. Nytt scope: Allsvenskan + research-only Premier League,
  Serie A, La Liga och Bundesliga, fortsatt bara 1X2 och kompletta styrke-/Elo-/
  WP9c-rader. Championship, Serie B, Segunda och 2. Bundesliga är fit-only så
  nyuppflyttade lag inte blir historiklösa. 6 292 fria resultatrader, 78 lag/
  arenor och 3 441 lag-event är inlästa; 38/39 aktuella premiärmatcher är
  kompletta (Bayern–Stuttgart saknar giltigt ClubElo-intervall och behålls öppet
  som missing). De fyra ligorna syns inte i UI och kan inte skapa signaler,
  notiser eller CLV. Träningsgate: 300 avgjorda kompletta matcher per horisont,
  ≥50 per liga, ≥42 dagar; forwardgaten upprepar volymen och kräver positiv
  undre 90 %-KI utan att någon liga försämras >0,005 logloss. Shadow
  `v22-7450a9ff`, features `f22-9c205e9c`, modellkälla `m22-957459bc`.
  Manifest: `docs/model-v2.2-multileague-forward-manifest.json`; rapport:
  `docs/v2.2-multileague-start-2026-07-23.md`.
- **Produktbeslut 2026-07-24, del 1 LEVERERAD samma dag:** Premier League,
  Serie A, La Liga och Bundesliga syns nu i vanliga Oddset-vyn som egna
  ligafilter och matchrader (🔬-märkta, dotted filterknapp) med SvS-/Pinnacle-
  odds, prisålder och rörelseserier. Synlighet och actionability är separerade
  i `oddset.py`: `visible_in_ui`-flaggan ger `VISIBLE_LEAGUE_KEYS`,
  `ACTIONABLE_LEAGUE_KEYS` (= ej research) styr värde/Kelly/notis/CLV.
  UI-payloaden strippar värde-/modellfält för research (`research=True`-
  markerade), `Bara signaler` räknar aldrig research som signal, spelkort/
  amber-listan exkluderar dem, och `_research_next_round` visar nästa omgång
  när 10-dagarsfönstret är tomt (premiärerna 16/8+ syns direkt). Insamlings-
  payloaden (`include_research=True`), V2.2-identiteter, ledger och v22audit
  är oförändrade (`actionable nej · notiser nej`). 135 backendtester + bygge
  gröna; verifierat i browser på desktop + 390 px utan sidscroll.
  Del (2), immutable PIT-facit för poolspelen, är påbörjad: **PH0-auditen är
  klar** (`docs/ph0-kallaudit-2026-07-24.md` + JSON; skript
  `backend/scripts/ph0_kallaudit.py`). Nyckelfynd: result/streck/omsättning
  finns i API:t hela vägen till 2013 (Stryktipset #4267, exakt gräns), inga
  429 vid 0,35 s takt; aktuella odds är flyktiga → rörelser finns BARA i de
  86 lokalt observerade omgångarna (`observed_pit`); `startOdds` når ~2022
  och är osemantiserad; API:ts drawState är korrekt även när lokala
  `draws.state` fryst. **PH1 är GENOMFÖRD 2026-07-24** (grönt ljus via "kör
  vidare med backloggen"): `app/pool_settlement.py` + fyra append-once-tabeller
  (kanon-hash, ingen tyst overwrite, journal med retrybara statusar),
  migration + backup + backfillskript (se `docs/db-atgarder.md`), 10 nya
  tester, framåtriktad settlement i snapshotvarvet och läs-API
  `/api/pool/history`. Full backfill körd: **8 278 omgångar, alla fem
  produkter tillbaka till januari 2013** (API:ts arkivhorisont), 76 554
  matchfacit, 14 476 utdelningsnivåer, 0 fel/divergenser — detaljer i
  `docs/db-atgarder.md`. `startOdds` sparas rått men är SPÄRRAT för analys
  tills semantiken verifierats. Äldre API-bakfill får bara ge finalvärden,
  facit och utdelning, aldrig fabricerad rörelse. **PH2 + PH3 är också
  GENOMFÖRDA 2026-07-24** (`docs/db-atgarder.md`): PIT-dataset `pit-v1`
  (256 horisontrader över 98 observerade omgångar, enbart observed_pit,
  no-backfill-regeln kodad), framåtriktad omsättnings-/jackpottserie
  (`pool_draw_snapshot`), och systemledgern med FÖRREGISTRERAD
  benchmarkmatris (primär `ev50-medel-vw50` + två sekundära) som fryser
  byggarens konkreta rader vid T−3h/T−20min i varvet och settlar mot
  riktig utdelning — champion = dagens byggare, `/api/pool/systems`.
  **PH4-analyspasset är KÖRT 2026-07-24** (`docs/ph4-analys-2026-07-24.md`,
  läsande, ingen runtime-ändring): folket överstreckar favoriter i alla fem
  produkter (65–70 %-streck träffar 56–60 %); **κ>1 överallt** (2013–2026:
  1,04–1,29; 2024+: 1,02–1,11 — medvinnarna är FLER än oberoende-antagandet,
  dagens EV är optimistisk i medvinnartermen); folkkorrelationen är U-formad
  (fetare svansar — systemspel täcker skräll- och folkfacit bättre än
  mitten); ablationerna (34 topptipsomgångar walk-forward) slår INTE rå
  devigad marknad — endast streckrörelse har negativt punktestimat (KI över
  noll, hypotes). FÖRREGISTRERAD GATE: ≥40 out-of-time-omgångar efter
  2026-07-24 med hela KI90<0 per produkt; challengers (nivå-κ under toppen,
  svansjusterad P_folk) ska slå champion i PH3-ledgern före runtime.
  **Codex-eftergranskning åtgärdad 2026-07-24:** PH0/`pit-v1` hade blandat
  senaste värdeförändring med senaste lyckade observation. Ny
  `pool_market_capture` skriver därför varje lyckad SvS-/Pinnacle-läsning
  även när värdet står still; `pit-v2` kräver presence + timingtolerans och
  bakfyller aldrig v1. PH3 räknar nu kontrafaktisk egen-vinnarutspädning,
  rollover med noll officiella vinnare blir okänd ROI, och rapportering/gate
  sker per produkt × config × horisont enbart på timely+lösbara rader.
  Jackpot har explicit endpointproveniens utan `draw.fund`-fallback.
  Forwardmanifestet `docs/pool-ph4-forward-manifest.json` fryser kandidat d
  och börjar scoring 2026-07-25; development kan inte räknas mot de 40
  omgångarna. Första livevarvet gav 212 presence-rader men korrekt 0
  `pit-v2`-horisonter (cutoffs får inte bakfyllas). Full rapport:
  `docs/pool-pit-v2-2026-07-24.md`. **Ingen runtime-modell ändrad.**
  Slutverifiering: 163 backendtester, frontend production build och
  produktions-DB:s integritetskontroll är gröna.
  Kvar: låt v2/PH3 växa, kontrollera första horisont/frysning/settlement,
  `startOdds`-semantikverifiering och gate-omprövning först vid volym.
  Överlämning och arbetsordning:
  `docs/overlamning-till-claude-2026-07-24.md`.
- **UI v3-experiment levererat 2026-07-24 (Samans beställning):** ny
  gränssnittsversion i `frontend/src/AppV3.jsx` + `AppV3.css` med växel —
  klassiska v2-vyn är orörd och default; ✨-knappen i v2-headern öppnar v3,
  "Klassisk vy" går tillbaka (val i localStorage `svs_ui_version`, växling
  laddar om sidan; kupong/omgång/inställningar delas via `svs_state` åt båda
  håll — verifierat med 128-raderskupong genom hela rundresan). v3 = fyra
  vyer: **Idag** (nästa spelstopp med spelvärde/jackpot per spel, topp-
  värdespel, rörelseradar, forskningsligornas status, signal-facit per
  primärgrupp, historikfacit-ingång), **Poolspel** (v2:s analystabell/
  byggare/kupong/sharp/steam/CLV återanvända i stegflöde 1-2-3),
  **Oddset** (samma OddsetView) och **Historik** (settlementlagret: KPI:er,
  omsättnings-sparkline, expanderbara omgångar med nivåer + matchfacit +
  slutstreck). Desktop + 390 px utan sidscroll, teal-accent skiljer
  versionerna åt.
- **WP9c team-events klar (2026-07-17):** Sofascore-lagflödet samlar nu alla
  tävlingar per aktivt lag med provider-ID, tournament, första/senaste
  observation och basarena. 94 lag/94 arenor, 94 lyckade captures och 3 329
  unika matcher i 24 tävlingar backfillades. Alla 48 kommande källligamatcher
  hade komplett exakt/aliasverifierad vila, 7/14/30-dagars belastning och
  basarena-reseproxy. Backfillens `first_seen_at` är 2026-07-17 och kan därför
  aldrig bli historiskt promotionsbevis. **Ej inkopplat i dagens tipsmodell;**
  endast nya tidsenliga captures ingår i V2.2:s isolerade forskningslager. Rapport:
  `docs/wp9c-team-events-2026-07-17.md`.
- **Alt-linjelagret (steg-upp 2026-07-20, Samans beställning):** sharpens ALLA
  Ö/U-/AH-/hörnlinjer sparas nu (`oddset_sharp_alt`, samma två API-anrop som
  förut) och värdemotorn jämför på BOKENS exakta lina via alt-linjen när
  huvudlinorna skiljer — samma-linje-regeln dödade tidigare 67 % av AH- och
  ~40 % av Ö/U-jämförelserna. Stängningen läser alt-lagret när huvudlinan
  flyttat (exakt-line-close i stället för censur). Rent marknadspris (grön väg,
  ingen modell); ny sharp-version `s-776ca0e0`. Första varvet: 1 238 alt-rader/
  38 matcher; Ö/U-jämförelser 66 (28 via alt), AH 38 (12), hörnor 6 (2).
  Facit-läge samma dag: sharp 1X2 +3,8 % close-EV på 50 stängda (Allsvenskan
  +3,7 %/16 matcher, MLS +6,8 %/12) — långt kvar till candidate (30 matcher/
  liga) men riktningen är rätt; modell-tiern fortsatt negativ = amber gör sitt
  jobb. Detaljer i `docs/db-atgarder.md`.
- **Facit-UI + alt-linje-efterkontroll (2026-07-23):** prognosledgern visar
  nu status som aktuella liga × marknad × tier × versionskort; tier-summan i
  signal-loggen är uttryckligen bara översikt och kan inte längre få ett
  missvisande ✓. Primärgrupper visar 50 flaggor/30 matcher/28 dagar samt en
  försiktig tidigaste candidate-prognos när stickprovet räcker; positiv undre
  KI-gräns måste fortfarande bevisas. Äldre signalversioner ligger kvar i
  detaljtabellen men räknas inte som aktuell insamling. Oddset-listorna visar
  en bästa värdeselektion/rörelse per match och kan sorteras på datum eller
  kvalitet/storlek. Efter tre drift­dygn hade `s-776ca0e0` 98 sharp-flaggor och
  52 jämförbara stängningar; 8 stängdes exakt på flagglinan trots flyttad
  huvudlina (5 Ö/U, 2 hörnor, 1 AH). DB 47 MB, integritet `ok`; 114 tester och
  frontendbygge gröna, desktop + 390 px verifierade utan konsolfel.
- **Drift-audit 2026-07-23:** v2-modulerna är kodmässigt märkta vilande och får
  inte återupptas utan ny hypotes + nytt fryst outer-manifest. 45-minutersvaktens
  flimmerrisk är mätt: 120/236 fullvarvsintervall på sju dygn var längre än
  45 minuter (median 51, max 63), främst för djuppriser utanför snabbfönstret.
  Gränsen ändras inte — gamla priser ska inte göras spelbara. Om UX-problemet
  märks blir nästa lösning en separat nedtonad ”senast sedd signal” utan
  Kelly/notis/logg/facit. Se `docs/flimmer-audit-2026-07-23.md`.

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
| **Sofascore (browser-TLS)** | **xG (!), hörnor, 43 statfält/match** för Allsvenskan & Eliteserien + live-radarns chansdata | ✅ i drift — `curl_cffi impersonate` ersatte Playwright-planen (Etapp 3). OBS: xG saknas helt för Allsvenskan i live-läge. |
| **FotMob** | live-xG/xGOT/open-set-play — ANDRA live-ögat där Sofascore saknar xG | ✅ i drift 2026-07-25 (`app/fotmob.py`, egen tabell — xG blandas aldrig mellan providers). Gamla "skippa"-domen från 2026-07-12 upphävd. |
| Flashscore | live/odds/lineups (inofficiellt) | ⛔ omtestad 2026-07-25: 401 utan privat `x-fsign` = avsiktlig grind, och ger inget FotMob inte redan ger — skippas (källgränsen) |
| allsvenskan.se / eliteserien.no | officiell statistik | 🟡 WordPress med wp-json — undersök vid behov, låg prio |
| FBref (browser-kontext) | tabeller/grundstats | 🟡 browser passerar Cloudflare (verifierat) men INGEN xG för Allsvenskan (22 tabeller kollade) — lågt värde, skippa |
| Blockerade (omtestade 2026-07-12; FotMob senare LÖST, se egen rad) | football-data.org (Allsvenskan i katalogen men datat kräver betald tier), Opta-webben (Akamai; gratisvägen = renderade bilder, feeds kräver betald outlet-nyckel — omkollat 2026-07-25) | ⛔ |
| ASA (American Soccer Analysis) | MLS: xG/xPass/Goals Added/löner/domare/arenor — oberoende MLS-kvalitetskontroll | 🔴 certfel 2026-07-13 (hostname mismatch, både httpx & Chrome-TLS) — verifiera åtkomst innan planering (WP9a). Blanda aldrig providers' xG i samma fält. |
| Sofascore shotmap | shot-xG + xGOT per skott | ✅ probat 2026-07-13: Eliteserien 30/30 skott med xG — Allsvenskan 0/31 (fältet saknas för SWE). Coverage-matrix (WP9b) innan features byggs. |
| Sofascore team-events | lagets ALLA tävlingar (cup/Europa) | ✅ WP9c i drift 2026-07-17: 94 lag, 3 329 unika event, PIT-first-seen, vila/belastning + basarena-reseproxy; ännu inte modellinput |
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
| svs (FRYST ARKIV 2026-07-20) | 8000 | 5173 | 5180 | urlastat (servrar stoppade, DB kvar) |
| vm (Boll boll kollen) | 8001 | 5174 | — | com.saman.vm.* (5 jobb) |
| **spelkompisen** | **8002** | **5175** | **5181** | com.saman.spelkompisen.{snapshot,pool,backend} |
