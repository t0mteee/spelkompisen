# Live-radarns källor — recon och FotMob-inkoppling (2026-07-25, Opus 5)

**Samans beställning:** fortsätt dra in live-data, gärna från fler källor
(Flashscore, LiveScore, spelsidor, Opta), och använd den för att UPPMÄRKSAMMA
matcher som sticker ut — inga blinda spelrekommendationer.

Utgångsläget var att radarn hade **ett** öga (Sofascore) och att detta öga är
blint där vi spelar mest: Sofascore saknar xG helt för Allsvenskan (0/31 i WP9b),
och radarns eget 220-matcherstest visade att en ren skottsignal inte förutsäger
mål (0,94–1,06× basraten över alla kvintiler). Radarn hade alltså ingen mätbar
signal i Sveriges högsta liga.

## Recon — ett artigt anrop per källa, inga challenges lösta

| källa | svar | live-xG | omdöme |
|---|---|---|---|
| **FotMob** `api/data/matches` + `matchDetails` | 200 JSON | **JA** (xG, xGOT, open/set play) | **inkopplad** |
| ESPN `site.api.espn.com/.../scoreboard` | 200 JSON | nej (skott, possession) | reserv, oberoende |
| LiveScore `prod-public-api` | 200 JSON | nej (resultat/klocka) | låg nytta |
| Flashscore `local-global.flashscore.ninja` | **401** | – | kräver privat `x-fsign`; skippas |
| Understat | 200 HTML | nej (ingen live) | skrapning, ingen live |
| Opta / Stats Perform | – | – | kommersiellt, ingen gratis väg |
| football-data.org v4 | 200 (tom) | nej | kräver nyckel |

Flashscore och Opta är alltså inte "svåra" — de är stängda. Gränsen står kvar:
publika JSON-endpoints, statiska publika tokens och artig rate limiting är fritt
fram; anti-bot-utmaningar löses inte.

## FotMob — vad som byggdes

`backend/app/fotmob.py` + tabellen `oddset_live_fotmob` + ett steg i
`cli.py live-tick`.

Verifierat live 2026-07-25 (Degerfors–Djurgården, Allsvenskan 65'):

| | Sofascore | FotMob |
|---|---|---|
| xG | **saknas** | 0,73 – 1,45 |
| xGOT | saknas | 0,00 – 0,98 |
| stora chanser | 1 – 3 | 1 – 3 |

Och den viktigaste kontrollen — Eliteserien, där BÅDA källorna har xG
(Kristiansund–Start 21'): **0,36 – 0,08 i båda**, identiskt. Källorna är alltså
konsistenta där de överlappar, vilket gör FotMob-värdena trovärdiga där
Sofascore är tyst.

Radarkortet i Oddset-vyn visar nu `xG 0.73–1.45 [FotMob] xGOT 0.00–0.98` och
matchen gick från "xG saknas · proxy / FÖLJER" till **GRANSKA LIVE** — dvs
precis "uppmärksamma matcher som sticker ut", utan någon rekommendation.

## Metodgränser som byggdes in

1. **xG blandas ALDRIG mellan providers** (WP9a-regeln). Egen tabell, egna id:n.
   Om Sofascore har xG används Sofascore; annars FotMob — och då räknas HELA
   signalen (inklusive 15-minutersdeltat) i FotMobs egen serie. Annars hade
   deltat mätt skillnaden mellan två xG-modeller i stället för mellan två
   minuter. `signal.xg_source` säger alltid vilken källa som talar.
2. **Observationstid per anrop** (🕐-regeln): varje `matchDetails`-svar
   tidsstämplas efter sitt eget anrop och `Age` dras av. Endpointen är
   `max-age=10`, men regeln läses ändå — inte antas.
3. **Egen HTTP-väg**: egen klient, 8 s timeout, tak 12 matcher, 60 s budget. En
   shadow-källa får aldrig strypa eller hänga den spelbara pipelinen (samma fix
   som radarn själv fick 2026-07-25).
4. **Explicit ligamappning** på (landskod, exakt liganamn) — aldrig fuzzy.
   Handbolls-läxan gäller även FotMob.
5. **Konservativ namnlänkning mellan källor**: prefixregel med minst fyra tecken
   ('Djurgården' ↔ 'Djurgårdens IF'), krav på samma liga. Ingen träff = ingen
   FotMob-data visas; vi gissar aldrig.
6. **Ingen statistik ⇒ ingen rad.** Nollor hade sett ut som 0,00 xG.
7. **Shadow.** Ingenting härifrån rör tips, Kelly, notiser, CLV eller
   modellinput. Nio regressionstester i `tests/test_fotmob.py`.

## Samans tre frågor — mätta svar (2026-07-25 kväll)

### 1. Är texten under statsen nödvändig?

Nej, den sa samma sak upp till tre gånger. Kortet hade `reason` + `warning` under
en statsrad som redan visade siffrorna:

* *Utan statistik:* "Källan saknar xG och användbara chansmått" **+** "Ingen
  chanssignal räknas från saknade värden" — två rader, samma innebörd, ovanpå
  statsraden som redan stod "xG saknas · stora chanser –––". Nu **en** rad:
  "Källan rapporterar inga skott- eller chansmått." Det enda som inte syns
  ovanför är att gränsen är källans, inte vår.
* *Med proxy:* radade upp exakt de siffror som stod ovanför. Nu: "X trycker på —
  men xG saknas, detta är en proxy".
* Varningen "proxyn har inte visat prediktiv mållyft" stod på **varje** kort och
  drunknade därför. Den hör i fotnoten, en gång — där ligger den nu.

### 2. Hur bestäms vilka träningsmatcher som visas? (två riktiga fel)

Uppmätt: Sofascore hade **463 livematcher**, varav **117 i `ut=853` Club Friendly
Games**, varav **43 fanns i vår Oddset-data**. Vi visade 11.

* **Fel 1 — bara EN träningsturnering var mappad.** Sofascore delar upp
  träningsmatcher på många turneringar, och de nationella låg helt utanför
  radarn: England 20 live, Bulgarien 11, Polen 8, Serbien 8, Kroatien 5,
  Tyskland 5. Nu mappade (853, 35960, 27113, 27120, 32053, 32366, 27118), alla
  bakom samma spärr — endast matcher som redan finns i Oddset.
* **Fel 2 — taket klippte blint.** `MAX_MATCHES = 14` delas av ALLA ligor och
  urvalet var *det Sofascore råkade returnera först*. En lördag med 43 behöriga
  träningsmatcher kunde alltså tränga ut Allsvenskan helt. Nu sorteras riktiga
  ligor först och därefter mest återstående speltid, och **vad som föll bort
  redovisas** — i källhälsan och i radarns fotnot ("Urval: friendlies 30 över
  taket"). Inga tysta tak.

### 3. Saknar verkligen SAMTLIGA träningsmatcher stats?

Nej — men nästan, och xG saknas helt. Ur vår egen insamling (56 träningsmatcher,
senaste capture per match):

| liga | matcher | med xG | med skott på mål | med stora chanser | med hörnor |
|---|--:|--:|--:|--:|--:|
| träningsmatcher | 56 | **0** | 4 | 4 | 50 |
| allsvenskan | 1 | 0 (FotMob fyller) | 1 | 1 | 1 |
| superettan | 1 | 0 | 0 | 0 | 0 |
| eliteserien | 1 | 1 | 1 | 1 | 1 |

* **xG: 0 av 56.** Och det är inte en Sofascore-brist — FotMob har `0`
  statistiknycklar även för *Hoffenheim*–Greuther Fürth och *Bologna*–Iraklis.
  Providerna prissätter inte försäsongsmatcher med händelsedata. Ingen ny källa
  löser det.
* **Skott/chanser: 4 av 56.** De fyra är matcher med en stor klubb inblandad
  (t.ex. Bromley–Crystal Palace: 2–7 skott på mål, 0–3 stora chanser). Djupet
  följer matchens profil, inte turneringen.
* **Hörnor: 50 av 56** — dem samlar vi, men proxyn använder dem inte. Att lägga
  in hörnor i en proxy som redan saknar prediktivt stöd vore att bygga vidare på
  ett negativt facit; lämnas.

Slutsats: fler träningsmatcher på skärmen ger fler kort utan chansinformation.
Taket är inte begränsningen — datan är.

### 4. Dölj matcher utan chansdata (Samans beslut 2026-07-25)

Matcher där källan inte rapporterar skott eller xG alls döljs nu ur radarvyn.
Nyansen Saman själv pekade ut är avgörande och är låst av test: **`no_stats`
sätts bara när ALLA chansfält är None**, dvs källan rapporterar dem inte. En
match i 4:e minuten med noll skott har värdet 0, inte None, och får en
proxysignal — den döljs alltså aldrig för att den är tidig.

Verifierat i drift direkt efter ändringen: 2 visade, **10 dolda**
(träningsmatcher 9, OBOS-ligaen 1). Kvar i vyn låg Kalmar FF 90' med
FotMob-xG och *Málaga CF i 12:e minuten* — den senare är beviset att tidiga
matcher med mätta värden stannar.

Filtret gäller VISNINGEN, inte insamlingen: captures fortsätter sparas, så
täckningsmätningar och framtida facit påverkas inte. Antalet dolda och vilka
ligor de kom ur redovisas i radarhuvudet (inga tysta filter).

### 5. Varför finns taket alls? (Samans följdfråga)

Det gamla taket 14 var satt efter en **gissning** om tidsbudgeten. Uppmätt
kostar ett statistik-anrop **0,06 s**, så 90-sekundersbudgeten räcker till över
tusen matcher — tiden var aldrig den bindande gränsen, och taket klippte i
onödan.

Men den verkliga kostnaden är inte tid utan **anrop mot en delad källa**: varje
matchplats kostar 12 anrop/timme mot Sofascore, samma källa som matar den
SPELBARA xG-pipelinen och frånvarodatan. Att fyrdubbla lasten för en
shadow-funktion är precis den risk radarn en gång fick egen klient för att
undvika.

Lösningen blev därför **sortering, inte ett högre tak**. Matcher vi redan vet
saknar chansmått läggs sist (`_known_empty_events`, tre nivåer: har haft data /
okänd / bevisat tom efter minut 25). Fördelningen över 73 livematcher på fyra
timmar:

| nivå | matcher |
|---|--:|
| tier 0 — har haft chansdata | **8** |
| tier 1 — okänd (ny eller tidig) | 4 |
| tier 2 — bevisat tom | **61** |

Med den sorteringen räcker 30 platser för **alla** matcher som har data, och de
som klipps är exakt de som ändå hade dolts i vyn. Ett tak på 60 hade gett
identisk SYNLIG lista till dubbla antalet anrop. En tidig match straffas aldrig:
tomt före minut 25 är okänt, inte tomt.

De bevisat tomma pollas fortfarande när det finns plats kvar, så vi märker om
statistik dyker upp sent — ett hårt skip hade gjort oss permanent blinda för
matchen. Testet som håller taket ≤ 30 är kvar med avsikt.

## Vad krävs för Betsson, Flashscore och Opta?

* **Betsson:** en cookie-fri eventväg. `/api/sb/v1/context-details` ger 200 med
  vår publika kontext, men `/api/sb/v1/widgets/events-table/v2` ger **CloudFront
  403** — och det gäller hela koncernen: betsson.com, betsafe.com och
  nordicbet.com svarar alla 403. (`betsson.se` ser ut att svara 200 men
  omdirigerar bara till `betsson.com/sv` och returnerar sidans HTML, inte API:t.)
  Ingenting Saman kan göra utan att exportera browsersession/WAF-token, vilket vi
  inte gör. Klienten ligger kvar färdig i `app/betsson.py` för dagen de öppnar en
  vanlig väg.
* **Flashscore:** feeden svarar **401** och kräver en `x-fsign`-header. Projektets
  gräns tillåter statiska publika tokens ur sidans kod, så det vore formellt
  görbart — men 401 är en avsiktlig auktoriseringsgrind (till skillnad från
  Pinnacles publicerade gäst-nyckel), och Flashscore ger oss inget FotMob inte
  redan ger: de har inte xG för Allsvenskan där vår lucka satt. **Rekommendation:
  skippa.** Låg vinst, tydlig gräns.
* **Opta:** deras gratisdel är renderade visualiseringar, inte data.
  `theanalyst.com` 403:ar mot oss, `dataviz.theanalyst.com` är ett tomt skal utan
  endpoints eller token i sidan och nämner ingen av våra ligor,
  `omo.akamai.opta.net` svarar "You are not allowed to receive this content" och
  `api.performfeeds.com` kräver betald outlet-nyckel (403, felkod 10300). Värt att
  notera: vi får sannolikt Opta-härledd data ändå — FotMobs xG för Eliteserien var
  **identisk** med Sofascores, vilket pekar på samma underliggande leverantör.

## Flashscore-testet — Saman hade rätt om xG, jag hade fel

Saman flyttade gränsen så långt den går (2026-07-25) och bad mig testa. Jag hade
avfärdat Flashscore med att de "inte har xG för Allsvenskan". **Det var ett
antagande och det var fel.** Uppmätt i deras egen vy:

* **Allsvenskan** (Degerfors–Djurgården, slutresultat): xG **0,92 – 1,53**,
  xGOT 0,00 – 1,52, plus skott, farliga chanser, hörnor, passningsprocent.
  Jämför FotMob vid 65': xG 0,73 – 1,45, xGOT 0,00 – 0,98 — konsistent
  utveckling, alltså samma storhet.

Men den avgörande frågan var inte om de har xG utan om de har den **där vi inte
redan har den**. Där tar svaret slut:

| liga | Sofascore | FotMob | Flashscore |
|---|---|---|---|
| Allsvenskan | ❌ | ✅ | ✅ |
| Eliteserien | ✅ | ✅ | ✅ |
| Superettan | ❌ | ❌ | ❌ (mätt: bara innehav/skott/hörnor) |
| OBOS-ligaen | ❌ | ❌ | ❌ (mätt: bara innehav/skott/hörnor) |
| Träningsmatcher | ❌ | ❌ | ❌ |

**Slutsats: Flashscore duplicerar exakt det FotMob redan ger och fyller ingen
kvarvarande lucka.** xG-tillgången följer ligans datanivå hos alla tre källorna,
vilket pekar på samma underliggande leverantör (Eliteserien: FotMob = Sofascore
exakt). Att bygga en tredje insamlare för Allsvenskan/Eliteserien vore ett rent
konsistenstest — och det har vi redan gratis genom FotMob mot Sofascore.

Rekommendationen blev alltså densamma som förut, men nu på **mätta** grunder i
stället för ett antagande: bygg inte Flashscore. Gränsfrågan blev därmed
irrelevant — vi behövde aldrig gå nära den.

**Praktisk anteckning för framtida pass:** feeden
`local-global.flashscore.ninja/2/x/feed/...` svarar 401 utan `x-fsign`.
Tokenvärdet är en statisk konstant i deras publika JS (tillåtet enligt gränsen
nedan), men **miljöns behörighetsklassare blockerar skript som söker efter
tokens i JS-buntar** — det läser som token-skörd. Behövs det i framtiden måste
Saman lägga in en Bash-behörighetsregel. Sidan i sig går att läsa i browsern
utan token, vilket räckte för mätningen ovan.

## Nästa steg för radarn

- **Låt serien växa och mät sedan.** Nu finns för första gången xG för
  Allsvenskan live. Innan en signal får bli mer än en färgmarkering krävs en
  förregistrerad gate — samma trappa som allt annat: definiera signalen,
  horisonten, tröskeln och n INNAN datan tittas på.
- **ESPN som andra öga** är billigt (ett anrop per liga, ingen xG men oberoende
  skott/possession) och skulle ge en korskontroll av FotMobs skottsiffror. Värt
  det först om FotMob-serien visar sig instabil.
- **Superettan/OBOS/träningsmatcher saknar xG i båda källorna.** Där är proxyn
  fortfarande allt som finns, och proxyn har ett negativt facit. Radarn ska
  därför fortsätta säga "följer" och inget mer för dem.
- **Live-odds** (Pinnacles per-matchup-endpoint är den enda som ger dem) ligger
  kvar utanför. Metodregeln "startade matcher hoppas över — live-odds ljuger"
  gäller värderingen; skulle live-odds någon gång användas som ren
  uppmärksamhetssignal är det ett eget beslut med eget facit, inte en utökning
  av den här.
