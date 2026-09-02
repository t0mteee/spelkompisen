# Överlämning — 2026-07-25 (Claude Fable 5 → nästa session)

Läs `CLAUDE.md` och STATUS-blocket i `docs/plan.md` först. Detta dokument
beskriver natten 24→25 juli: en bred granskning, fem verifierade buggfixar
och ett nytt sharp-ankare. Codex-uppföljningen omsätter därefter Samans två
förtydliganden — fler oberoende källor och live chansradar — i konkreta
leveranser och arbetspaket.

Claudes pass är committat (13 commits). Codex-uppföljningen nedan är nu
verifierad och ingår i repositoryt.

---

## Codex-uppföljning 2 — Samans saknade actions

### A. Fler oberoende bookmakerkällor

- **Altenar är levererat via Ninja Casino.** UI:t visar nu `N` och separat
  källhälsa. Fler Altenar-skins ska inte räknas som nya källor.
- **Smarkets är levererat som andra sharp-ankare.** UI:t visar nu `S`
  tillsammans med Pinnacle och separat källhälsa. Tvåankarkravet ska först
  shadow-loggas i minst 200 stängda observationer/28 dagar.
- **Betssons header är löst med Browser.** Exakt fält är `brandId`, med
  sportsbookens UUID från sidans publika bootstrap. `app/betsson.py` hämtar
  dessutom färska context-ID:n och bygger den publika utloggade
  webbklientskontexten; context-details verifierades med HTTP 200.
  Matchtabellen ligger däremot fortsatt bakom CloudFront-sessionen och får
  inte lösas genom cookie-/WAF-replay. Betsson är därför testad och
  header-klar men ännu inte inkopplad i `BOOKS`.
- **Coolbet är konkret blockerad av Imperva**, inte bortglömd. Anti-bot ska
  inte kringgås. Matchbook blir det omedelbart byggbara reservspåret för en
  tredje oberoende referens och likviditet nära avspark.

### B. Live matcher där chanserna överstiger utdelningen

**Levererat i shadow mode.** `app/live_radar.py` läser liveevent och
kumulativa Sofascore-mått, sparar femminutersobservationer i
`oddset_live_capture`, exponerar `/api/oddset/live-radar` och visas i en
mobilanpassad Live-radar i Oddset. Den använder xG när det finns och en
tydligt varnad chansproxy annars. Den påverkar inga tips, Kelly-tal, facit,
pushar eller systemförslag.

Migrationen är genomförd med backup och loggad i `docs/db-atgarder.md`.
Första scope-rättade liveprovet skrev två `sofa-live-v2`-captures.
Metod, signalgränser, settlementplan och gate före notiser finns i
`docs/live-radar-2026-07-25.md`.

Det historiska 220-matchersprovet under punkt 4 gäller en enkel
skottsignal. Det motiverar att radarn är informations-/shadowstöd, men är
inte längre ett skäl att avstå från att samla den rikare xG- och
chanshistorik Saman faktiskt beställde.

---

## Codex-uppföljning 1 — Claudes tre öppna punkter

1. **Pinnacle-CDN: löst och liveverifierat.** HTTP `Age` dras nu av från
   prisets observationstid i Oddset, altlinjer och pool-PIT. Transporthälsa
   använder fortfarande riktig hämtningstid. Ett cacheobjekt äldre än fem
   minuter får inte öppna notisgrinden. Live: hämtning 23:15:31, `Age=338`,
   observation 23:09:53; 63 DB-rader verifierade.
2. **m20-kadensen: löst utan att röra toleransen.** Poolinsamlingen har ett
   eget launchd-jobb på fasta femminutersslag, med 30-minuters basthrottle
   och varje tick inom två timmar från stopp. Oddset startar separat på
   fasta :00/:30; poolen har två minuters offset för att undvika käll- och
   DB-kollision.
   Båda jobben är installerade och laddade.
3. **Första settlementen: källan väntar fortfarande.** Ett nytt ordinarie
   Topptips-snapshot gav fortfarande ingen resultpayload för 4226/4227.
   Ledgern har korrekt lämnat 12 system osettlade; ingen manuell SQL eller
   fabricerat facit har använts.

Cachefixen ändrar datasemantik. Därför startar `pit-v3`/experiment
`pool-streckmove-v2` vid `2026-07-24T23:30:00Z` via det nya, frysta
`docs/pool-ph4-forward-manifest-v2.json`. Det gamla v1-manifestet ändrades
inte och hade noll forward-scorade omgångar. Full rapport:
`docs/pool-pit-v3-2026-07-25.md`.

Verifierat för hela den samlade ändringen: 212 gröna
backendtester, frontendbygge, shellsyntax, båda launchd-plists och
`git diff --check`.

---

## 1. Fem buggar som kostade pengar — alla uppmätta, inte antagna

Verifierade mot projektets EGEN settlementdata (150 omgångar/produkt):

| # | Fel | Uppmätt | Åtgärd |
|---|---|---|---|
| 1 | Europatipsets vinstplan var Stryktipsets kopia | 12-rätt får 0,22, inte 0,15 — potten underskattad 47 % | `PRIZE_PLANS` rättad |
| 2 | Spelvärdet visade bruttoandelen | splits summerar 0,92/0,98 ⇒ faktisk återbetalning 59,8 %/63,7 %, inte 65 % | `_payout_ratio()` + break-even-hurdle (+67 %) i statusraden |
| 3 | Ensamvinnargarantin osynlig | `guaranteedJackpots` = 10 Mkr på Stryk 4963, aldrig läst | `get_guarantees()`, visas i UI, medvetet UTANFÖR EV |
| 4 | Strukna matcher helgarderades | 52,8 % favoritträff i 593 strukna mot 52,1 % i 75 514 ostrukna; inga extra toppvinnare | tvingad gardering borttagen (kostade 3× rader) |
| 5 | CLV-facitet för optimistiskt | `LIMIT 300` + estimand-krock | hela historiken, samma estimand, censurdiagnostik, veckokadens |

**Den viktigaste siffran ändrades:** sharp-tiern är **+2,65 % [1,19..4,11]**
över 147 stängda flaggor — inte +6,6 % som det trunkerade fönstret visade.
Fortfarande positivt med KI över noll, men mindre än hälften.

Dessutom: κ per produkt/nivå ur PH4 inkopplad i radvalet (sänker EV), frontend
fick backendens streck-golv och räknar mot prognostiserad slutomsättning, och
amber-modellen (−4,2 % close-EV, KI utan noll) ger inte längre stödchip på
värdekorten — en signal som är mätbart sämre än marknaden får inte rösta upp
spel till "★ starkast stödd".

## 2. Smarkets inkopplat som ANDRA SHARP-ANKARE

`app/smarkets.py` — publikt v3-REST, ingen auth. Fyra batchade anrop per liga,
ett delat events-anrop för alla tio. Första varvet: 258 oddsrader, 10/10 ligor.

- **Overround ~1,00** mot Pinnacles 2–2,5 % och SvS 2,6 %.
- **Ligger UTANFÖR `BOOKS`** — det är ett ankare, inte en bok att slå, och får
  aldrig skapa matchidentiteter.
- **Träningsmatcher: 53 event** mot Kambis 6 — vår högsta-edge-liga (11,8 %)
  hade sämst täckning.
- **Oenigheten är materiell:** median |Δp| mot devigad Pinnacle 1,12 pp, och
  **11 % av selektionerna skiljer mer än 2 pp = hela flaggtröskeln.**

**Nästa steg (ej gjort):** kräv att en edge överlever mot BÅDA ankarna innan
den flaggas. Det angriper projektets djupaste metodproblem — att devigmetodens
val (power vs proportionell) rör ~3 pp medan flaggtröskeln är 2 pp, så vi inte
vet om edgen är marknadens eller devigens. Låt serien växa några veckor först.

## 3. Bookmaker-strategin omvärderad

Premissen "fler mjuka böcker ⇒ fler edges" håller inte i svensk marknad:

- **Svenska Spel ÄR den skarpaste mjuka boken** (overround 2,59 % uppmätt).
  Att 231/241 flaggor kom därifrån är en korrekt observation, inte ett fel.
- **Kambi är EN prisfeed** — svenskaspel/expektse/ubse/atg gav identiska odds
  på decimalen. Unibet, ATG, Paf, LeoVegas ger noll ny information.
- **Altenar är EN feed**; Betinia hade sämst marginal av elva skins. Bytt till
  `ninjacasinose`: overround 1,0949 → 1,0645.
- Plattformskartan finns i `docs/forbattringar.md` så ingen framtida session
  lägger till en "ny bok" som är samma feed.

## 4. Två utredningar som båda sa NEJ — och varför det är värdefullt

### Livebetting-screenern (Samans idé)

Saman förtydligade att Pinnacle är ointressant här: idén är en RADAR som
hittar matcher där det händer mer än ställningen visar, så att han själv
tittar på liveoddsen. Det är en annan (och bättre) fråga än den första
utredningen besvarade — och den går att avgöra HELT utan odds.

**Testat på 220 matcher i våra ligor** (`scripts/live_screener_validering.py`,
2 200 lag-observationer vid minut 15/30/45/60/75):

| kvintil av "tryck" | mål i nästa 15 min | mot basrate |
|---|---:|---:|
| Q1 lägst | 22,7 % | 0,97× |
| Q2 | 23,0 % | 0,97× |
| Q3 | 22,5 % | 0,96× |
| Q4 | 25,0 % | 1,06× |
| Q5 högst | 24,5 % | 1,04× |
| **topp 10 %** | **22,2 %** | **0,94×** |

Basrate: 23,5 %. **Signalen har ingen prediktiv kraft** — laget som skjutit
mycket utan utdelning gör inte mål oftare, och de allra mest "trycksatta"
ligger till och med under basraten. Det är klassisk regression mot medelvärdet:
skott är brus, och otur blir inte tur.

Viktig förutsättning som också verifierades: **Sofascores shotmap saknar xG
helt för Allsvenskan** (29–31 skott per match, 0 med xG). Skott med minut och
typ finns däremot — det är det testet ovan använder, alltså "20 skott"-halvan
av Samans exempel.

**Historisk Claude-slutsats:** bygg inte en enkel skottbaserad spelsignal.
**Samans senare produktbeslut:** bygg en informationsradar och samla ett
eget framåtriktat facit med xG/stora chanser där källan erbjuder det. Detta är
nu levererat i shadow mode; se Codex-uppföljning 2 ovan.

### Den första livebetting-utredningen (bonus: en produktionsbugg)

Den fann att **Pinnacles bulk-endpoints är CDN-cachade `max-age=905`** och att
objektet ofta redan är minuter gammalt (verifierat: `age` 469 och 539 s).
**Hämtningstid ≠ pristid** — samma klass av fel som pit-v1:s förändringstid ≠
observationstid. Klienten bokför nu `last_age_s`.

**LÖST I CODEX-UPPFÖLJNINGEN OVAN:** åldern dras nu av i
färskhetsreglerna och PIT-capturen; notisvakten godtar inte cacheobjekt äldre
än fem minuter. Prisets semantik är separat versionerad.

Två bonusfynd: `/markets/related/straight` returnerar tyst FRYSTA
prematch-marknader (lätt fälla), och per-matchup-endpointen är 8 kB mot
bulkens 32 MB.

## 5. Kvällsauditen av PH2/PH3 (utlovad i överlämningen 07-24)

**Allt som går att granska före settlement är korrekt.** 7 pit-v2-horisontrader,
8 128 captures, 12 frysta system med **12 unika `rows_hash`**. Devigade
sannolikheter summerar till 1,00 i 48/48 rader, streck till 100 i 48/48, inga
orimliga rörelser eller gap. `timely` flaggade rätt de två frysningar som låg
10,5 min efter cutoff. `jackpot_source=missing` är KORREKT för Topptipset
(finns inte i jackpots-feeden alls — verifierat).

**Ett fynd:** m20-horisonten tappas systematiskt. Tätlägets 25-minutersbudget
mot launchds 30-minutersintervall lämnar ett ~31-minutershål (uppmätt
16:18 → 16:49); faller cutoffen där blir horisonten tom. Gaten använder h3
(frisk), så det frysta experimentet påverkas inte. **Toleransen rördes inte.**
Kadensen är nu löst med ett eget, förskjutet femminutersjobb enligt
Codex-uppföljningen ovan.

**Settlement-delen återstår:** SvS hade 23:15 inte publicerat facit för
topptipset 4226/4227 (`drawState=Closed`, ingen `result`). Att ledgern då gör
ingenting är rätt beteende. Auditera egen vinstutspädning, `payout_complete`
och `n_evaluable` när facit finns.

---

## Vad nästa session bör göra

1. **Auditera första settlementen** när SvS publicerat facit (punkt 5 ovan).
2. **Följ första `pit-v3`-dygnet**, särskilt faktisk m20-täckning med det nya
   femminutersjobbet; ändra inte toleranser eller förregistrerad gate.
3. **Settla Live-radarns snapshots framåt** enligt
   `docs/live-radar-2026-07-25.md`; inga notiser före gaten.
4. **Bygg tvåankar-shadowfacitet** för Pinnacle + Smarkets; koppla inte in
   gaten innan 200 stängda observationer/28 dagar.
5. **Bygg Matchbook-spåret** enligt `docs/bookmaker-kallplan-2026-07-25.md`.
   Betssons header är löst, men dess eventtabell kräver fortfarande en
   vanlig browser-/CloudFront-session.

## Väntar på Saman (kan inte göras utan honom)

- Inget för Betsson. Codex använde Browser och löste headern utan att läsa
  eller exportera cookies. Det kvarvarande CloudFront-hindret är tekniskt och
  ska inte kringgås manuellt.
- **bwin** ger 403 från Cloudflare här; svarar den 200 från Samans nät är
  klienten trivial.

## Gränsen som gäller

Publika JSON-API:er, statiska publika tokens i sidans kod, läsa publik
JavaScript och artig rate limiting är fritt fram. Att lösa eller förfalska
anti-bot-utmaningar — Cloudflare-challenges, Impervas `reese84`, CAPTCHA — görs
inte. bet365, Coolbet och Betano ligger bakom det senare. Betssons publika
bootstrap/context är åtkomlig, men bulk-eventflödet får ändå inte lösas genom
CloudFront-sessionreplay. Altenar är rent åtkomlig.
