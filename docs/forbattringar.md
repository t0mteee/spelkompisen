# Förbättringsbacklog — mot bättre +EV

Prioriterad lista från projektgenomgång + poolspels-research (juni 2026).
Teorin i korthet: i poolspel tas ~35 % (Stryk/Europa) av omsättningen — för +EV
krävs att folket felprisar tillräckligt, dvs **P_marknad/P_folk per RAD** måste
överstiga ~1/(1−takeout) ≈ 1,55 på toppnivån (lägre krav vid jackpot). Värdet
sitter i rader folket inte spelar, inte i enskilda tecken.

## Klart (implementerat)

- [x] **Power-metoden för fair_prob** — korrigerar favorit/longshot-bias vid
      overround-borttagning (empiriskt bäst tillsammans med Shin; proportionell
      normalisering överskattar longshots → falska "värdestreck" på skrällar).
- [x] **EV-topp-system** — ranka konkreta kandidatrader efter popularitetsjusterad
      EV (toppnivå-grov + full nivå-finrankning), ta budgetens bästa. Detta är den
      poolspels-optimala radvalsmetoden (rad-nivå, inte tecken-nivå).
- [x] Sharp-medveten teckenpoäng, markant-rörelse-flaggor, utdelningsspann
      (min/medel/max), Egna rader-export, strategi↔EV-koppling.

## Hög prioritet

1. ~~**Backtest & kalibrering mot facit**~~ → `cli.py backtest N produkt` (klar).
   **Första körningen (30+30 omgångar, juni 2026):**
   - Stryktipset: värdestreck (kvot ≥1.08) träffade **50 %** mot folkets 30.8 %
     streckade (n=20) — signalen ser äkta ut. Överspelade tecken (≤0.92) träffade
     bara **15.8 %** mot 30.1 % streckat — folket bränner pengar precis där
     modellen säger.
   - Europatipset: svagare/ingen edge i urvalet (värde 21.7 % träff, n=23) — mer
     data behövs innan slutsats.
   - **κ (vinnar-kalibrering)**: Stryk 1.08, Europa 0.78 — oberoende-antagandet
     är inom ±25 % och åt olika håll; ingen stor systematisk klumpning. Följ upp
     när n växer; ev. produkt-specifik κ i EV-modellen.
   - **Begränsning:** avgjorda omgångar behåller odds på bara ~1 match/omgång i
     API:t → kör om backtesten mot **våra egna snapshots** när databasen växt
     (några veckors data ger full odds-täckning). = backtest v2.

2. ~~**Spelvärdesindikator per omgång**~~ (klar): riktiga jackpotdata från
   `/draw/1/jackpots` (matcha productId + drawNumber; `fund` på draws är
   opålitligt — 6 Mkr-jackpotten fanns bara i jackpots-endpointen). /api/payouts
   ger `jackpot` + `spelvarde`; topinfo visar 💰-flagga och kupongens jackpotfält
   förifylls. Verifierad live: Stryk 6 Mkr, Europa/VM-tipset 5 Mkr.
   Kvar: spelvärdet räknas mot nuvarande omsättning — blir rättvisande först
   med projicerad slutomsättning (punkt 3).

3. ~~**Projicerad slutomsättning**~~ (klar): median av senaste avgjorda omgångars
   slutomsättning (cachas 6 h). Topinfo visar spelvärde nu + vid prognos
   (Stryk-jackpotomgången: "606 %" → ärliga 91 %); kupongen har "→ prognos"-knapp;
   systemvyn visar EV vid prognos; EV-/färgbyggarna räknar mot prognosen.
   Möjlig förfining: veckodags-/säsongsviktning i stället för rak median.

## Medel prioritet

4. ~~**Kelly-insats**~~ (klar): 📐-ruta i kupongen — kvarts-Kelly på toppvinsten
   (konservativt), bankrulle sparas lokalt, varnar när kupongkostnaden överstiger
   rekommendationen. Förfining: full multinivå-Kelly över alla vinstnivåer.
5. **X-bias-koll**: litteraturen antyder att kryss systematiskt understreckas i
   1X2-pooler. Verifieras gratis i backtesten (1) — i så fall litet X-tillägg i
   teckenpoängen.
6. ~~**Tätare snapshots nära spelstopp**~~ (klar): `cli.py snapshot-smart` —
   snapshotar alla produkter och förtätar själv till var 5:e min när någon
   omgång stänger inom 2 h (max 25 min/körning; launchd-intervallet orört).
7. **Diversifiering i EV-topp**: topplistan kan bli klungor av nästan identiska
   rader (delar öde). Greedy-val med straff för Hamming-närhet till redan valda
   rader ger bättre portfölj-varians till nästan samma EV.

## Portat/att porta från VM-kollen (/Users/saman/vm)

P1. ~~**CLV-facit**~~ (klar): value_log-tabell (first/best per flaggat tecken,
    grön kvot ≥1.08 eller sharp-edge ≥2 %), devigad Pinnacle-stängning från
    sista sharp-snapshot före avspark, facit från resultat-API:t. Loggas av
    snapshot-pollen; /api/clv + "Signal-facit"-panel i UI. Positiv snitt-CLV
    över många flaggor = signalerna äkta; negativ = vi lurar oss själva.
P2. ~~**Steam i devigade procentenheter**~~ (klar): app/steam.py — devigad
    Pinnacle-sannolikhet nu vs 6/24/72 h sedan, /api/steam + panel under
    Sharp-odds. 🔥-flaggan och ntfy-notisen triggar nu på devigat 24h-skift
    (≥3,5 pp markant, ≥6 pp stark) i stället för rå odds-diff; rå rörelse
    finns kvar som fallback när sharp-serie saknas.
P3. **ClubElo-korsreferens** (Stryktipset = klubbar): api.clubelo.com (gratis
    CSV, dagliga ratings). Elo→1X2 via supremacy = ratingdiff/skala → Poisson,
    kalibrera skalan mot marknadens snittsäkerhet (vm: ELO_GOAL_SCALE).
    EJ värdekälla (vet inget om skador) — bara "marknad/modell oense → kolla".
P4. ~~**Backtest mot football-data.co.uk**~~ → `cli.py fdbacktest` (klar).
    **Resultat (4 608 matcher, 23/24+24/25, E0/E1/D1/SP1/I1/F1), Pinnacle-close
    devigad = "marknaden", B365 = "folket", insats till B365-odds:**
    - Grön (kvot ≥1.08): träff 18.4 % (> sharp-P 16.8 > soft-P 15.2) · ROI **−2.6 %**
    - Neutral: träff 34.3 % = exakt kalibrerat · ROI −7.2 % (= bokens marginal, baslinjen)
    - Röd (≤0.92): träff 8.7 % (klart under soft-P 11.9) · ROI **−35.4 %**
    Beslutsregeln validerad: grön äter upp nästan hela bokmarginalen (+4.6 pp
    mot baslinjen), röd är gift (−28 pp under baslinjen). I poolspel finns ingen
    bokmarginal — att slå folket räcker, och folket är mjukare än B365.

**Metodlärdomar från vm (dyrt köpta):**
- Modellhärledda sannolikheter utan sharp-ankare driver alltid åt ett håll
  (+40–120 % "edges" × 3 ggr). Poisson-deriverat = modell-tier i UI, ALDRIG
  in i CLV-facitet.
- O/U-linje ≈ median (inte medel) för skev Poisson; kalibrera μ mot devigad
  sharp P(Över) via bisektion — härled aldrig μ direkt ur linjen.
- Aggregat-kalibrering ≠ per-match-edge: rätt i snitt bevisar inte att man
  slår stängningslinjen per match.
- Dixon-Coles rho: −0.13 (klubblitteratur) rimligt för klubbar; vm fittade
  −0.04 för landslag. Fitta mot egen data före användning.

## Låg prioritet / idéer

8. ~~Färgreducering~~ → `color=true` på /api/system (klar), inkl. **manuell
   överstyrning** (ColorLab: klicka tecken ofärgad→blå→gul, egna min/max-gränser,
   `colors=`/`bounds=`-params). Kvar: lås spik/uteslut tecken som separat villkor.
   Kupongen ärver numera systemets exakta rader ("radläge") i stället för att
   explodera till alla kombinationer vid "Fyll från förslag".
9. Andelsspels-läge: dela systemkostnad, visa per-andel-EV.
10. ~~Bomben~~ (klar, v1): exakt-resultat-spel utan SvS-odds. Poisson-målmodell
    (Pinnacle spread/total → home_xg/away_xg via derive.goal_expectations) mot
    folkets resultatfördelning (svenskaFolket-marginaler) → värdekvot per resultat.
    app/bomben.py + /api/bomben + BombenView (resultat-heatmap). Degraderar till
    folk-only när Pinnacle nere. KVAR: radbyggare/Egna rader-export för Bomben
    (kombinationer av resultat; annan filrubrik), och modell-tier-flagga utanför CLV.
11. Måltipset (pid 8) — samma API-familj som Bomben (mål-tips), kan återanvända motorn.
11. ~~Notifiering vid 🔥~~ (klar): app/notify.py pushar via ntfy.sh när en match
    får 🔥 (sen markant oddssänkning) och omgången stänger inom 8 h; dedup per
    match. Kräver NTFY_TOPIC i backend/.env + ntfy-appen.
12. Visa "din rad vs folkets rad"-överlapp som riskmått på kupongen.

## Research-källor

- Power/Shin-metoder & favorit/longshot-bias: [penaltyblog – From Biased Odds to Fair
  Probabilities](https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/),
  [Clarke – Adjusting Bookmaker's Odds](https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf),
  [mberk/shin (Python)](https://github.com/mberk/shin)
- Pari-mutuel-EV & takeout: [The Economics of Parimutuel Sports Betting](https://medium.com/@lloyddanzig/the-economics-of-parimutuel-sports-betting-367cb5ee1be1)
- Jackpotstrategi (svensk pooltips-praxis): [GamblingCabin – strategi vid extrema
  jackpottar](https://gamblingcabin.se/strategi-vid-extrema-jackpottar/),
  [topptipset.net – spelvärde](https://topptipset.net/stryktipset-lordag/)
