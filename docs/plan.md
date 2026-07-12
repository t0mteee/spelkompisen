# Spelkompisen — färdplan

## STATUS (uppdatera löpande — läses först i varje ny session)

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

## Modellplan — vägen till en modell att lita på (efter backtest-domen)

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
- Modell: Dixon-Coles per liga (vm:s `model.py` som bas; rho refittas för klubbfotboll,
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
