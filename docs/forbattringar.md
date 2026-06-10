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

2. ~~**Spelvärdesindikator per omgång**~~ (klar): `fund`/`extraInfo` parsas ur
   draw-svaret, /api/payouts ger `jackpot` + `spelvarde`; topinfo visar
   "spelvärde X %" + 💰-flagga, och kupongens jackpotfält förifylls.
   OBS: `fund`-fältets form är ännu overifierad (null utan jackpot) — dubbelkolla
   parsningen första riktiga jackpotomgången!

3. **EV-läget: osäkerhetsjustering tidigt i veckan**
   - Tidig låg omsättning → fält litet → "+EV" mot dagens pott är glädjesiffror.
     Projicera slutomsättning (historik per produkt/veckodag) och räkna EV mot
     den; visa båda. Streck stabiliseras sent — flagga att EV-ranking är färskvara.

## Medel prioritet

4. **Kelly-insats**: givet radernas p och utdelningsspann, föreslå total insats
   (fraktionell Kelly, t.ex. 0,25×) i stället för fast budget. Kräver (3).
5. **X-bias-koll**: litteraturen antyder att kryss systematiskt understreckas i
   1X2-pooler. Verifieras gratis i backtesten (1) — i så fall litet X-tillägg i
   teckenpoängen.
6. **Tätare snapshots nära spelstopp**: launchd var 30:e min missar sena rörelser
   (vår starkaste signal). Öka till var 5:e min sista 2 h (StartCalendarInterval-
   varianter eller en löpande agent som sover adaptivt).
7. **Diversifiering i EV-topp**: topplistan kan bli klungor av nästan identiska
   rader (delar öde). Greedy-val med straff för Hamming-närhet till redan valda
   rader ger bättre portfölj-varians till nästan samma EV.

## Låg prioritet / idéer

8. ~~Färgreducering~~ → `color=true` på /api/system (klar), inkl. **manuell
   överstyrning** (ColorLab: klicka tecken ofärgad→blå→gul, egna min/max-gränser,
   `colors=`/`bounds=`-params). Kvar: lås spik/uteslut tecken som separat villkor.
   Kupongen ärver numera systemets exakta rader ("radläge") i stället för att
   explodera till alla kombinationer vid "Fyll från förslag".
9. Andelsspels-läge: dela systemkostnad, visa per-andel-EV.
10. Måltipset (pid 6?) — samma API-familj, annan radstruktur.
11. Notifiering (ntfy/pushover) när 🔥-flagga (sen oddssänkning) dyker upp nära deadline.
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
