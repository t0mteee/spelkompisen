# Förbättringsbacklog — ARKIV (svs-ärvda lärdomar + källkartläggning)

**Detta är inte längre projektets aktiva backlog — den ligger i
`docs/backlog.md` (sedan 2026-07-26).** Filen behålls som referens: research-
länkarna, metodlärdomarna från vm och bokkälls-kartläggningen (2026-07-24/25,
längst ned) är fortfarande giltiga. STATUS-blocket från svs-eran är borttaget;
öppna punkter härifrån är antingen avförda eller flyttade till backloggen
(t.ex. Bomben-filrubriken, diversifiering, multinivå-Kelly).

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
      **Uppdaterad till "Värderader"**: rankas nu på P^k × EV (k styrs av EV-
      reglaget) — ren EV var ospelbar för 100–500 kr; balansen är default.
- [x] Sharp-medveten teckenpoäng, markant-rörelse-flaggor, utdelningsspann
      (min/medel/max), Egna rader-export, strategi↔EV-koppling.

## Hög prioritet

1. ~~**Backtest & kalibrering mot facit**~~ → `cli.py backtest N produkt` (klar).
   **Första körningen (30+30 omgångar, juni 2026; ersatt av audit nedan):**
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
   **κ-audit 2026-07-16 (100 omgångar/produkt):** gamla geometriska
   `+1`-kvoten ersattes av Poisson-exponeringens naturliga skattare
   `Σ vinnare/Σ prognos`, med omgången som block i 90 %-bootstrap. Stryk:
   **0,98 [0,90..1,05]** (93 kompletta); Europa: **0,91 [0,81..0,97]**
   (98 kompletta). Runtime behålls konservativt på 1,00: Europa-resultatet
   skulle annars höja EV och kräver bekräftelse i ett nytt tidsfönster.
   Värde-/X-tabellerna ska inte användas som beslutsfacit från historiska API:t:
   odds-täckningen var bara 2–3 %, medan κ använder separata slutstreck.

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

## Nya signaler & källor (från v2-diskussionen, juni 2026)

S1. ~~**RLM — reverse line movement**~~ (klar): folket och devigad sharp åt olika
    håll. `rlm_go` ◆ (folk −3pp, sharp +2pp = smart pengar) / `rlm_fade` ⚠
    (folk +4pp, sharp −2pp = undvik). Taggar + märken + boost/straff i
    teckenpoängen. Gratis — bygger på egna serier. Trösklarna är gissningar:
    validera mot CLV/backtest när data växt.
S2. **Oddset som egen del**: SvS sportsbok (enskilda matcher, fotboll) som ny
    flik — leta utstick soft (Oddset) vs sharp (Pinnacle devigad) ≥ X %, dvs
    klassisk soft-book-värdejakt fast hos SvS. Kräver API-recon i Chrome
    (Oddset är Kambi-baserat, annan API-familj än tipsspelen). Störst nya yta.
S3. **Polymarket som andra sharp-källa** (vm har klient): prediction markets
    prissätter stora matcher/turneringar väl — bra korsreferens när Pinnacle
    tvekar/blockas. Tunn täckning för klubbfotboll i lägre serier.
S4. **Opening line-ankare**: spara första Pinnacle-priset per omgång explicit
    och visa total drift opening→nu (utöver våra fönster) — "vem hade rätt
    från början"-vy. Litet jobb, egna data.
S5. **ClubElo (P3)** kvarstår som marknads-oberoende sanity-check för
    Stryktipset/Europatipset (klubbar).

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
    folk-only när Pinnacle nere. Radbyggare + export klar: build_bomben_system
    rangordnar resultat-rader efter EV (pott = oms×0.65 + rullpott ur fund.rolloverIn),
    /api/bomben/system + BombenBuilder-UI, Egna rader-fil "Bomben"+"E,h-a,h-a,h-a"
    (filrubrik OVERIFIERAD — inloggningsskyddad sida; kopiera-fallback finns).
    KVAR: verifiera Bomben-filrubriken vid skarp uppladdning; modell-tier utanför CLV.
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

## Bookmaker-strategin omvärderad (2026-07-24)

Full kartläggning i `docs/bookmakers-kartlaggning-2026-07-24.md` (allt live-testat).
**Premissen "fler mjuka böcker ⇒ fler edges" håller inte i den svenska marknaden:**

- **Svenska Spel ÄR den skarpaste mjuka boken.** Overround 2,59 % på Allsvenskan
  (uppmätt) — i praktiken Pinnacle-nivå. Att 231 av 241 värdeflaggor kom från
  SvS är därför en korrekt observation, inte ett insamlingsfel: ingen mjuk bok
  slår det priset.
- **Kambi är EN prisfeed.** svenskaspel / expektse / ubse (Unibet) / atg / paf
  ger identiska odds på decimalen (verifierat: 5.10/4.00/1.72, overround
  1,0259 för alla fyra). Att lägga till Unibet, ATG eller Paf ger noll ny
  information. Expekt bidrar bevisligen inget och kan tas bort.
- **Altenar är EN prisfeed** med olika marginalpåslag per skin. Betinia hade
  sämst av elva (1,095); bytt till ninjacasino (1,065) — samma event, samma
  linje, 3 pp bättre pris.
- **De flesta genuint mjuka böcker är botskyddade** (bet365, Coolbet, Betano,
  bwin, Winamax, ComeOn, 888 …). Betssons API är det viktiga undantaget:
  det svarar med JSON men kräver en okänd frontend-header. Kartläggningen
  stannade vid skyddet i stället för att kringgå det — den gränsen gäller.

**Det som faktiskt är värt att bygga: ett ANDRA SHARP-ANKARE, inte fler böcker.**
Smarkets (overround 2,15 %, öppet REST, 10/10 ligor, 810 event — verifierat) och
Matchbook (öppnar sent, men ger faktisk likviditet per pris) är BÖRSER: de är
skarpare än SvS och alltså inte ställen att hitta värde hos. Nyttan är metodisk
och stor:

1. Idag mäts varje edge bara mot vår egen power-devigning av Pinnacle — och
   metodvalet (power vs proportionell) rör ~3 pp medan flaggtröskeln är 2 pp.
   Ett börspris behöver nästan ingen devigning och validerar därför devigen.
2. Kräv att en edge överlever mot BÅDE Pinnacle och Smarkets innan den flaggas.
3. Fallback när Pinnacle Cloudflare-blockar (händer periodvis).

Smarkets-steget är nu levererat. Matchbook i snabbpollen är nästa byggbara
ankare (den öppnar sent och tillför mest i lineup-/steamfönstret). Betssons
frontend-header är löst, men eventtabellen kräver fortfarande en vanlig
CloudFront-browsersession och är därför inte ett stabilt launchd-spår. Exakt
ordning och acceptanskriterier:
`docs/bookmaker-kallplan-2026-07-25.md`.

### Plattformskarta (verifierad mot Spelinspektionens licensregister 2026-07-24)

Böcker på samma motor är **nära dubbletter, inte oberoende åsikter**. De
genuint skilda svenskvända motorerna är: Kambi, Betsson in-house, ComeOn
in-house, Altenar, Spectate, Coolbet, Playtech och bet365 — men bara **Kambi
och Altenar är rent åtkomliga**. Därav:

| Motor | Svenska varumärken | Åtkomst |
|---|---|---|
| **Kambi** | Svenska Spel, ATG, Unibet SE, Paf (+Speedybet, 1x2.se), LeoVegas, Expekt | ✅ öppet, men EN prisfeed — alla ger identiska odds |
| **Altenar** | Betinia, Ninja Casino | ✅ öppet, EN feed; skins skiljer bara i marginal |
| Betsson in-house | Betsson, Betsafe, NordicBet | `brandId` + publik context löst; eventtabell CloudFront-blockerad utanför browser |
| ComeOn in-house | ComeOn, Hajper, Snabbare | `lsbl.comeon.com`, ingen publik väg |
| Spectate (evoke) | Mr Green, 888sport | ingen publik väg |
| Coolbet (Sega Sammy, EJ Betsson) | Coolbet | Imperva-skyddad |
| bet365 (Hillside) | bet365.com (`bet365.se` är bara 301) | aggressivt botskydd |

Korrigeringar av tidigare antaganden: Unibet har INTE lämnat Kambi i Sverige;
ComeOn är inte Kambi-turnkey (koden `comeon` ger 67 esport-event); Mr Green och
888sport har lämnat Kambi för Spectate; Coolbet ägs av Sega Sammy, inte Betsson;
Pinnacle ÄR svensklicensierat (`pinnacle.se`). Kambi rate-limitar (429 efter
~5 snabba anrop) — polla långsamt.

Ej implementerat men verifierat fungerande: Entain/bwin CDS-endpoint
(`x-bwin-accessid` är en statisk publik token i sidan, inte inloggning) — en
genuint annan motor, men bwin är inte svensklicensierat. Beslut krävs innan
det används.

### Smarkets inkopplat som andra sharp-ankare (2026-07-24)

`app/smarkets.py` + insamling i `oddset.collect`. Fyra batchade anrop räcker
för en hel liga; ett enda `/v3/events/`-anrop delas mellan alla tio ligor.
Första varvet: **258 oddsrader, alla 10 ligor OK**.

- **Overround ~1,00** (mid mellan bästa bid och bästa offer) mot Pinnacles
  2–2,5 % och Svenska Spels 2,6 %. Ett börs-mid behöver knappt devigas.
- **Ligger UTANFÖR `BOOKS`** — Smarkets är inte en bok vi letar värde hos utan
  ett fair-ankare. Den får aldrig skapa matchidentiteter.
- **Träningsmatcher: 53 event** mot Kambis 6 och Pinnacles 12. Det är vår
  liga med högst uppmätt edge (11,8 %) och sämst täckning — störst enskild
  vinst av bytet.
- **Oenigheten är materiell:** median |Δp| mot devigad Pinnacle 1,12 pp, och
  **11 % av selektionerna skiljer mer än 2 pp — hela flaggtröskeln.**

NÄSTA STEG (ej gjort): kräv att en edge överlever mot BÅDA ankarna innan den
flaggas, och använd Smarkets som fallback när Pinnacle Cloudflare-blockar.
Serien måste växa först — samma ordning som PIT-datat.

### bwin och Betsson — testade 2026-07-24/25, båda stoppade (av olika skäl)

**bwin (Entain CDS).** `www.bwin.com/cds-api/bettingoffer/fixtures` svarar
**403 från Cloudflare** för den här maskinen — det är en WAF-blockering, inte
ett saknat token. (Tidigare research fick 200, troligen från annan IP/geo.)
Att ta sig förbi en Cloudflare-challenge är kringgående av botskydd och görs
inte. Om endpointen svarar 200 från ditt eget nät är klienten trivial att
skriva — testa med curl därifrån först.

**Betsson/Betsafe/NordicBet.** Browsergranskningen 2026-07-25 hittade det
exakta felet: headern heter `brandId`, och värdet är sidans publika
`sportsbookBrandId`, inte Betssons content-brand-id. Inline-bootstrapen ger
även färska static/user-context-ID:n, och det publika user-context-anropet
ger alla återstående `x-sb-*`-fält utan cookie. Detta finns nu testat i
`app/betsson.py`; `context-details` svarade HTTP 200.

Bulkflödet med matcherna svarar däremot CloudFront 403 utanför den vanliga
webbläsarsessionen. Browsern visar samma Allsvenskan-data, men cookies eller
WAF-token ska inte exporteras/replayas och en DOM-skrapa är inte stabil nog
för launchd. Betsson är därför header-klar men inte en inkopplad källa.
