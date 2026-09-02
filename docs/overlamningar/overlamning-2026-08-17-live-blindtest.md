# Överlämning 2026-08-17 — liveblindtestets odds, facit och UI

Läs först statusdelen i `docs/plan.md` och metodkontraktet i
`docs/live-radar-2026-07-25.md`. Detta tillägg ändrar inte signaltrösklarna
eller radarversionen; det reparerar mätningen och gör vyn sann mot den redan
förregistrerade blindkohorten.

## Felet som användaren såg

Den 17 augusti visade de 100 senaste v9-raderna:

- 52 rader med observerat live-Ö/U-pris;
- 42 med `no_canonical_match`;
- 51 med slutresultat och 49 utan;
- 39 rader som både var prissatta och avgjorda;
- men bara 28 oddssatta och avgjorda i blindgaten.

Skillnaden är riktig men UI:t förklarade den inte. Journalen blandade:

1. första aktiva signalen per match — blindtestets enda beslut;
2. senare Stark-eskaleringar — diagnostik, aldrig ett andra blindspel;
3. signaler utan observerat livepris — observationer, aldrig spel;
4. prissatta testspel som ännu väntar på facit.

`Följer` är alltså inte passiv bevakning. Det är den första aktiva
signaltröskeln. När den nås och ett öppet Över-pris observeras skapas
blindtestets låtsasspel. Informationsläget före Följer är den verkliga
bevakningen och journalförs inte som signal. Om första observerade nivån redan
är Stark kan den vara blindbeslutet; en Stark-rad efter en tidigare Följer-rad
är däremot bara diagnostik.

## Backendens explicita testspelskontrakt

`live_signal_ledger.facit` märker nu varje journalrad med:

- `blind_entry`: första aktiva signalen för matchens låsta identitet;
- `test_bet`: `blind_entry` plus samtidigt observerad Ö/U-lina och Över-odds;
- `test_bet_exclusion`: `later_signal` eller `no_live_price` när raden inte
  ingår som spel.

Samma markering som blindgaten använder skickas därmed till UI:t. Klienten
ska aldrig själv försöka härleda första signalen ur den omvända listordningen.
Grupperna bär dessutom `n_priced_signals` och ROI-tröskeln i UI använder
`n_priced_settled`, inte alla avgjorda observationer.

## Varför odds saknades och vad som ändrats

Den gamla vägen krävde en kanonisk rad i `oddset_matches` för att få Kambis
event-id. Resultat-enbart-ligor och träningsmatcher kan sakna den raden även
när matchen finns i Svenska Spels pågående utbud.

När en NY signal saknar prematchkoppling eller den kanoniska raden saknar
SvS-id hämtas nu Kambis pågående eventlista högst en gång per radarvarv.
Matchen länkas endast om båda lagen matchar och exakt en kandidat återstår.
En svagare kortnamnslänk kräver att det andra laget matchar strikt.
Tvetydighet ger fortsatt inget odds. Därefter läses den ordinarie öppna
huvudlinan via samma `live_total`, inklusive alla befintliga suspensions- och
observationstidsregler.

Detta gäller bara framtida signalögonblick. Gamla liveodds får aldrig
bakfyllas från senare eller prematchdata.

## Varför facit saknades och vad som ändrats

Resultaten fanns redan för många gamla signaler, men den tidigare länken
krävde två strikt matchande lagnamn. Observerade exempel var:

- `Silkeborg – Odense` mot `silkeborg – odense boldklub`;
- `Alverca – Estrela` mot `alverca – estrela amadora`;
- `Sevilla – Rayo Vallecano` mot `sevilla – vallecano`;
- `KR Reykjavik – Breidablik` mot `kr reykjavik – breidablik kopavogur`.

Facitlänken får nu använda en kontextuell namnmatchning endast när:

1. resultatdatumet är exakt samma kalenderdag;
2. det andra laget matchar med den strikta regeln;
3. truppmarkörer och kända avvisade länkar är rena;
4. exakt en resultatkandidat återstår.

±1-dygnstoleransen finns kvar endast när båda lagen matchar strikt. Den nya
regeln är därför fail-closed vid dubbelmöten och tvetydighet. Ordinarie
settlement kan nu rätta äldre rader från redan observerat officiellt facit;
det är inte en rekonstruktion av signal eller odds.

## UI-kontrakt

Tabellen **Matchjournal** visar som standard enbart `test_bet=true`:

- grönt ✓ för vinst/halvvinst;
- rött ✕ för förlust/halvförlust;
- ↔ för återbetalning och ⏳ när facit väntar;
- slutresultat, mål efter signalen och enhetsresultat på samma rad;
- signalögonblick och ställning, beslut, låst liveodds och facit i fasta
  kolumner.

Övriga signaler är dolda bakom **Visa även signaler som inte blev spel**.
Där anges uttryckligen om orsaken var saknat pris eller att raden var en
senare eskalering. Signalregeltabellen anger tröskel, tidsfönster och exakt
när livepriset låses för Följer respektive Stark.

## Metod och version

Ingen tröskel, ligapopulation, signaltyp eller radarsignal ändras. Därför
behålls `chance-gap-shadow-v9`. Prisfallbacken reparerar ett mätbortfall i den
redan definierade populationen och dokumenteras med driftsättningstid; den
används aldrig för historisk bakfyllning. Om prisdefinitionen eller själva
signalpopulationen ändras senare krävs som tidigare en ny, förregistrerad
kohort.

Regressionerna täcker direkt Kambi-livekoppling, tvetydighetsstopp,
kontextuell men entydig resultatlänk, tvetydigt facitstopp och de explicita
`test_bet`-markeringarna för första signal kontra Stark-eskalering.

## Driftkvitto 2026-08-17

Commit `59c6e29` är pushad till `main` och driftsatt på servern. Backend,
frontend, snapshotinsamling och poolinsamling kör och `/api/health` svarar
`ok` utan pool- eller v2.2-anmärkningar.

En settlement-körning mot en separat databaskopia rättade 36 äldre
observationer innan produktionsjobbet fick köra. Efter ordinarie
produktionssettlement visar `chance-gap-shadow-v9`:

- 72 första aktiva signaler, varav 58 har facit;
- 39 riktiga blindtestspel med observerat liveodds;
- 38 av de 39 spelen har facit: 17 vinster och 21 förluster;
- 61 övriga journalrader i API-fönstret är inte spel och döljs som standard;
- ROI är tills vidare −24,1 %, men kohorten är fortsatt `collecting` eftersom
  beslutskravet är minst 200 prissatta facit över minst 60 dagar.

De historiska facitreparationerna ändrar inte vilka rader som räknas som
spel. De gör bara redan observerade resultat tillgängliga för rader som
tidigare fastnade på namnvarianter. Gamla saknade liveodds har inte
rekonstruerats eller bakfyllts.

## Uppföljning: snabbare facit och tydligare nivåer

Häcken–Halmstad 17/8 blottade en separat fördröjning. Flashscore och FotMob
följde matchen till 91–92:a minuten och 1–0, men en sista livebild är inte
bevis på slutresultat. Flashscores egen färdigfeed hade däremot samma event-id
`vRkjOT13` med status `AB=3`, ordinarie slutstadium `AC=3` och 1–0. På det
svenska dagsflödet låg kvällsmatchen redan i offset −1 trots samma UTC-dygn;
snabbkontrollen läser därför även angränsande Flashscore-dygn.

`settle_signals(..., refresh_recent=True)` identifierar nu bara öppna
signalrader vars matchstart ligger 100 minuter–36 timmar bakåt. Bara
Flashscores färdigfeed läses, högst en gång per tio minuter. För en
Flashscore-signal måste provider-id, liga, båda lagen och avsparken stämma.
En reservproviders signal kräver en unik lag- och tidsmatchning mot
Flashscore. Bara `AC=3` accepteras; förlängnings- och straffstadier lämnas
öppna tills ett säkert normaltidsfacit finns. Sofascore används inte i denna
snabbväg och sista liveraden används aldrig som facit. Häcken-spelet var Över
1,5 @ 1,38 vid 1–0 i minut 69 och ska därför rättas som förlust mot
Flashscores bekräftade 1–0.

Nivåsumman hade också en korrekt men lätt misstolkad nämnare. `Stark 13/13`
betydde 13 avgjorda av 13 Stark-ögonblick med pris, inte att bara 13 matcher
nådde Stark. I datat hade 28 matcher nått nivån; nästan alla var senare
eskaleringar efter Följer. Av de 28 var 27 senare signaler; den enda match där
Stark var första signal saknade livepris. Stark-gruppen hade därför noll spel
i huvudblindtestet trots 13 prissatta, diagnostiska Stark-ögonblick. Den första
UI-korrigeringen visade därför separat:

- antal matcher som nådde nivån;
- antal nivåögonblick med odds;
- hur många av dessa som är avgjorda.
- hur många som faktiskt blev spel i huvudblindtestet och fick facit där.

Förklaringen angav att nivåerna var separata diagnostiska nivåtester, medan
huvudtestet bara använder matchens första aktiva signal. Den
upprepade rubriken `Testspel` på varje spelrad är ersatt av den informativa
nivån och signaltypen, exempelvis `Följer · xG`.

### Driftkvitto för uppföljningen

Commit `dda866b` driftsattes 2026-08-17. Det ordinarie pool-/radarjobbet
rättade Häcken-raden 21:21:53Z med `result_source=flashscore` och
`result_key=allsvenskan|2026-08-17|hacken|halmstad`: slutresultat 1–0,
noll mål efter signalen och Över 1,5 @ 1,38 som `loss`, −1,00 enhet.

Produktions-API:t visar efter rättningen 39 av 39 prissatta blindtestspel med
facit. Stark-rutan visar samtidigt 28 matcher som nådde nivån, 13
diagnostiska nivåtest med odds och facit, men 0 spel i huvudblindtestet.
Backend, frontend och snapshot kör; pooljobbet är aktivt och väntar mellan
sina schemalagda körningar. `/api/health` svarar `ok` utan anmärkningar.

## Labb-tabeller och låstidens semantik

Den tidigare sammanfattningen blandade tre olika populationer i samma
nivåbox: alla matcher som nått tröskeln, de som hade ett öppet livepris just
då och de som faktiskt blev förstbeslut i huvudblindtestet. Detta var
matematiskt korrekt men svårt att läsa; exempelvis såg `Stark 13/13` ut som
att bara 13 matcher hade facit trots att 28 matcher nått Stark.

Labb visar nu två tydligt åtskilda tabeller:

1. **Huvudblindtest** använder matchens första aktiva signal oavsett nivå och
   signaltyp. Högst ett spel per fysisk match kan räknas. Tabellen visar antal
   signalmatcher, hur många som hade ett öppet pris i beslutsögonblicket, hur
   många prissatta som har facit, ROI/KI och kvarvarande 200/60-krav.
2. **Nivåjämförelse** ställer separata väntestrategier mot varandra: spela när
   Följer först nås, eller ignorera Följer och vänta tills Stark först nås.
   Samma match kan därför finnas i både Följer- och Stark-raden. Raderna får
   inte summeras och Stark-raden är inte ett andra spel i huvudblindtestet.

`odds_observed_at` är låst append-only när respektive nivå först registreras.
Priset uppdateras inte senare. Om marknaden är stängd, saknas eller inte kan
kopplas säkert i det ögonblicket blir det ingen insats, och inget historiskt
pris bakfylls. Matchjournalens tabell visar signalögonblicket, om raden blev
huvudtestets beslut, exakt låst lina/pris och slutligt facit. Ej spelade
observationer är fortsatt dolda som standard men kan visas med toggle.

Hela Labb-ytan använder samtidigt en lodrät rapportstruktur. Sharp-facit,
modell mot close, aktiva valideringsgrupper, radarregler, nivåfacit,
matchjournal och övriga forskningsspår är tabeller med horisontell scroll på
smala skärmar. Små ROI-underlag kan visas för öppenhet men märks uttryckligen
`preliminärt`; endast den förregistrerade grinden kan ge stöd för blind
ryggning. Ändringen är ren presentation: kohort, signaltrösklar,
resultatsettlement och ROI-beräkningar är oförändrade.

### Driftkvitto för Labb-tabellerna

Commit `fee77c0` pushades till `main` och driftsattes 2026-08-17 på
MacBook-servern. Serverbygget gav bunten `index-DW7N7YBb.js`; samtliga 12
frontendtester passerade och `/api/health` svarade `ok` för både pool och
v2.2 efter omstart av enbart frontendtjänsten.

Browserkontrollen mot den driftsatta appen visade de riktiga nämnarna i de nya
tabellerna: huvudtest 72 signalmatcher, 39 låsta priser och 39 facit; Följer-xG
66/35/35; Stark-xG 28/13/13; Följer-skott 6/4/4. Matchjournalen visade 39
blindtestspel och 61 dolda observationer. Vid 390 px viewport var dokumentets
bredd mindre än viewporten och varje bred tabell scrollade i sin egen ram;
inga console-varningar eller fel registrerades.

## Uppföljning 2026-08-18: bästa livepris från tre oberoende flöden

ROI-ledgern använde tidigare enbart Svenska Spels Kambi-huvudlina. Det gav
två metodproblem: ett sämre SvS-pris kunde underskatta ett realistiskt
spelutfall, och ett Kambi-/identitetsfel gjorde raden helt oddslös trots att
en annan bok hade marknaden öppen.

Från `chance-gap-shadow-v10` frågas tre källor vid varje ny signalnivå:

- `svenskaspel`: Kambis live-lista + eventets live-total;
- `ninja`: Altenars separata `GetLiveEvents`, upptäckt via sportmenyns
  aktuella fotbollsligor med `hasLiveEvents`;
- `pinnacle`: Arcadias separata `/matchups/live` och
  `/markets/live/straight`, grupperade på fysisk parent-match så
  `live_delay`/`danger_zone` aldrig blir dubbletter.

Linan väljs först: färsk Pinnacle-huvudlina, annars Kambi, annars Ninja.
Därefter vinner högsta öppna Över-odds på **exakt samma lina**. Pinnacles
alternativlinor får jämföras med en mjuk boks huvudlina, men olika linor får
aldrig jämföras som om de vore samma spel. Vid lika odds är den fasta
källprioriteten deterministisk.

Serverprovet hittade 13 pågående Pinnacle-matchups och 30 live-totalrader.
Priserna var verkliga men bulk-CDN:n svarade med upp till cirka 15 minuters
`Age`; vanlig `Cache-Control: no-cache` ändrade inte åldern. Ett Pinnacle-pris
är därför ROI-spelbart endast vid `Age <= 90` sekunder. Äldre svar sparas som
`stale` och kan följas diagnostiskt men får varken definiera linan eller vinna
priset. Ninja/Altenar svarade från en separat liveväg med `max-age=3` och
markerar suspenderade utfall med `oddStatus=7`, som aldrig blir spelbara.

Nya `oddset_live_signal_quote` sparar en rad per signal × tillfrågad källa:
provider-event-id, observerad/kontrollerad tid, status, lina, Ö/U-pris,
cacheålder och vilket pris som valdes. Signalen och de tre källraderna skrivs
i samma transaktion. Huvudraden bär fortsatt det valda priset så settlement
och Asian-Över-ROI använder bäst realistiskt pris utan en historisk
rekonstruktion. Gamla priser bakfylls aldrig.

Schemaändringen ägs av det idempotenta skriptet
`backend/scripts/migrera_live_signal_quotes.py`, som tar SQLite-onlinebackup
före mutation och validerar schema, PK, FK, integrity och foreign keys. Den
nya prisprocessen får inte blandas med v9:s Kambi-only-ROI, därför börjar v10
rent 2026-08-18 00:00Z. Trösklarna och själva signalpopulationen är oförändrade.

Labb visar vald källa, `✓ bäst`, alla tre källornas pris/status och källtäckning
per nivå. Pinnacle-stale, annan lina, suspension, saknad match och källfel
skiljs uttryckligen. Före drift passerade 742 backendtester, 12 frontendtester,
lint och produktionsbygge.

### Driftkvitto för tre-källorspriset

Commit `1836e33` pushades till `main` och driftsattes på MacBook-servern.
Spelkompisens skrivande jobb pausades under migrationen; backupen
`stryktips-2026-08-18-fore-live-signal-quotes.db` skapades innan tabellen.
Migrationen gav 11 kolumner, 0 startrader, `integrity_check=ok` och 0 FK-fel.
Efteråt passerade serverns 742 backendtester, 12 frontendtester, lint och
produktionsbygge (`index-Csmm-kZr.js`). Alla jobb startades igen och hälsan
var grön för pool och v2.2.

Ett skrivfritt produktionsprov efter start gav 26 SvS-liveevent, 4 öppna
Ninja-totaler och 6 Pinnacle-livematcher (5 öppna, 1 suspenderad). Pinnacles
prisobjekt var då 615 sekunder gammalt och blev därför korrekt `stale`; Ninja
hade `Age=0`. API:t visade den rena aktiva v10-kohorten med 0 rader och v9:s
72 matcher som orörd historik.

Browserkontrollen mot den driftsatta Labb-sidan visade v10, förklaringen
SvS + Ninja + Pinnacle, samma-linje-regeln och det ärliga tomläget för den nya
kohorten. Inga console-fel eller varningar registrerades. Vid 390 px viewport
var dokumentbredden 375 px mot 390 px viewport, alltså ingen horisontell
sidöverrinning.

Den första livekontrollen avslöjade också att radartabellerna hann rendera
fallbackvärdet `0/200` innan det verkliga API-svaret kom. Labb visar därför nu
`Hämtar radar-facit…` tills svaret finns och ett riktigt felmeddelande om
anropet misslyckas; noll kan inte längre blinka som ett falskt facit.

## Uppföljning 2026-08-18: Stark-filter och prisorsaker

Matchjournalens standardfilter är fortsatt **Blindtestspel**, enligt den
tidigare UI-regeln att ej spelade observationer ska vara dolda från start.
Det är därför standardlistan nästan bara visar Följer: 27 av 28 Stark-rader är
eskaleringar efter att matchen redan fått sitt enda blindbeslut, och den enda
Stark-raden som var förstbeslut saknade pris. Stark-raderna var alltså sparade
men låg bakom visningen av ej spelade observationer.

Journalen har nu fyra oberoende filter: visning (blindtest/alla/ej spelade),
nivå (alla/Följer/Stark), signaltyp (alla/xG/skott) och livepris (alla/låst/
saknas). Val av Stark växlar automatiskt från Blindtestspel till Alla signaler
så det aldrig ger en oförklarad tom lista. Både journalen och nivåjämförelsen
använder `SortableTable`: rubrikerna sorterar på desktop och mobil visar den
delade sortväljaren ovanför tabellen.

Backendens nivåsummering exponerar nu `odds_status_counts`, eftersom ”15 utan
pris” dolde flera helt olika orsaker. Produktionskohortens Stark-xG är:

- 13 `captured` — säkert kopplad match och öppet Ö/U-pris;
- 13 `no_canonical_match` — inget pris fick knytas till matchen utan att
  identiteten gissades;
- 1 `suspended` — rätt livemarknad fanns men var stängd i signalögonblicket;
- 1 `source_error:HTTPStatusError` — källan svarade med HTTP-fel.

De 13 identitetsluckorna observerades 9–17 augusti, samtliga före commit
`59c6e29` och den entydiga direkta Kambi-livekopplingen driftsattes 17/8 cirka
22:54 CEST. De är därför historiskt mätbortfall, inte belägg för att Svenska
Spel saknade odds. De får inte bakfyllas; förbättringen mäts på nya signaler.
UI:t använder därför formuleringen **utan säkert låst pris** och skriver ut
orsaksfördelningen direkt i respektive nivåtabellrad.

### Drift- och browserkvitto 2026-08-18

Commit `7c09d76` pushades till `main` och driftsattes på MacBook-servern.
Serverns backendtester för området (42), samtliga frontendtester (12), lint
och produktionsbygge passerade. `/api/health` svarade `ok` efter omstart och
servern var ren mot `origin/main`.

Den driftsatta sidan verifierades dessutom i browsern mot riktig
produktionsdata. Val av Stark växlade visningen till Alla signaler och gav 28
journalrader. Prisfiltret Saknas gav 15 rader. Klick på rubriken
Signalögonblick ändrade både ordning och sortpil, den exakta fördelningen
13 utan säker matchkoppling + 1 suspenderad marknad + 1 källfel visades, och
inga console-varningar eller fel registrerades.

## Tillägg 2026-08-18 — ROI per oddskälla, och Labbtabellerna på mobil

### `source_roi`: vad varje källa hade gett på samma lina

`_summary()` returnerar nu `source_roi` bredvid `quote_source_counts`. Räkningen
är kontrafaktisk och helt lokal: alla källor prissätter exakt den lina signalen
bokförde, så `_over_profit(slutmål, quote.line, quote.over_odds)` per källa är en
ren prisjämförelse och inte tre olika spel. Per källa redovisas `n_asked`,
`n_priced`, `n_best`, `avg_over_odds`, `roi_over` och `roi_ci90`.

**Det är diagnostik och grindar ingenting.** Blindgaten läser oförändrat
`roi_over`/`roi_ci90` på det valda bästa priset. Ett nytt fält i
summeringsdicten ändrar ingen selektion och kräver därför ingen ny
signalversion.

**Pinnacle är ankare, inte bok — även live.** `PLAYABLE_LIVE_SOURCES` är
`{svenskaspel, ninja}` och raden märks `playable: false` för Pinnacle. Skälet är
inte principiellt utan mekaniskt: Pinnacle har klart lägst marginal på live-Ö/U
och vinner därför nästan varje "högsta Över-odds"-jämförelse. En ROI mätt på
dess pris är "vad fair value gav mig", inte vad en bok gav. `n_best` finns just
för att göra den snedvridningen synlig i stället för att argumentera om den.

Läs alltid ROI och `n_priced` ihop. Bortfallet är inte slumpmässigt — en bok som
stänger marknaden när den är osäker lämnar just de matcherna ur sin egen serie,
så en tunn källa kan visa bäst ROI utan att vara ett bättre val.

### Labbtabellerna fick plats på mobil

Elva tabeller hade handskrivna `min-width` på 680–980 px i behållare på
320–340 px. Mätt på 390 px betydde det 2–3 gångers sidoscroll, och radetiketten
föll ur bild så fort man scrollade till värdet — man kunde aldrig se BÅDE vilken
rad och vilket tal.

Två regler i `@media (max-width: 760px)`, desktop helt orört (verifierat vid
1280 px: `min-width` 680–900 px kvar, `position: static`, `white-space: nowrap`):

1. `min-width: 0` och radbrytande text — tabellerna gick från 680–980 px till
   338–551 px, och signalregeltabellen får nu plats helt utan scroll;
2. `position: sticky` på första kolumnen för de som ändå är för breda — 6–7
   kolumner får aldrig plats på 340 px, men etiketten står kvar medan värdena
   scrollas förbi. Radfärgningen i signalloggen flyttades till den låsta cellen,
   annars hade den hamnat bakom cellens egen bakgrund.

Lägg inte tillbaka `min-width` på mobil. Vill man ha mer plats är nästa steg att
faktiskt korta kolumnerna, inte att scrolla längre.

### Pinnacles livepris kom ur fel cache

`soccer_live_totals()` läste `/sports/29/matchups/live` och
`/sports/29/markets/live/straight`. **Båda bär samma `max-age=905` som
prematch-bulken** (uppmätt 2026-08-18: age 791 s respektive 47 s i ett och
samma anropsblock). Vid en slumpmässig tidpunkt i cachecykeln är åldern ungefär
likformig över 0–905 s, i snitt ~450 s, medan `PINNACLE_LIVE_MAX_AGE_S` är 90.
Pinnacle diskvalificerades alltså som `stale` i ungefär nio fall av tio och var
i praktiken en tom kolumn.

`Pinnacle.refresh_live_total(matchup_ids)` hämtar därför priset per matchup
(`/matchups/{id}/markets/straight`, `max-age=419`) för de matcher som faktiskt
bär en signal. Identiteten kommer fortfarande ur bulken — lagnamn ändras inte —
men priset gör det inte.

Uppmätt i drift, fyra samtidiga livematcher: bulken 340 s för alla fyra,
per-matchup 82, 181, 233 och 391 s. På Vélez Sarsfield–Defensa y Justicia
skilde sig inte bara åldern utan **linan**: bulk Ö2,5 @ 1,89 mot färsk
Ö2,25 @ 1,78. Bulkpriset var alltså inte ett gammalt pris på rätt lina utan ett
pris på en lina marknaden lämnat.

Det är en förbättring, inte en lösning — medianåldern ligger fortfarande över
tröskeln. **Sänk inte `PINNACLE_LIVE_MAX_AGE_S` för att få mer data att
kvalificera sig**; det vore att flytta bevisribban i stället för att förbättra
mätningen.

`Cache-Control: no-cache` prövades och gör ingenting: samma matchup gav
49/49/49 s och 224/224/224 s med och utan headern. De enda nollorna kom när vår
egen miss populerade cachen. Lägg inte tillbaka den.

v10:s deklaration utökades med detta samma dygn i stället för att bumpa till
v11. Det är försvarbart bara därför att v10 hade **exakt noll rader** när
ändringen gjordes — ingen observation kom ur den gamla koden inne i v10:s
fönster. Hade en enda funnits hade det krävt en ny version.

### Kohorten hinner aldrig fylla grinden

Blindgaten kräver 200 prissatta och avgjorda matcher samt 60 dagar. Så här
stora har kohorterna faktiskt blivit:

| version | prissatta + avgjorda |
|---|---:|
| v2 | 1 |
| v3 | 2 |
| v4 | 10 |
| v5 | 3 |
| v6 | 4 |
| v7 | 8 |
| v8 | 1 |
| v9 | 39 |
| v10 | 0 (startad i dag) |

Tio versioner på sjutton dagar. Den största kohorten någonsin är 39 av 200, och
v9 — den bästa — samlade 39 på cirka åtta dygn, alltså ~5 per dygn. 200 skulle
ta ungefär 40 dygn utan avbrott, men versionen har i snitt bytts varannan dag.

**Kohortregeln är rätt och ska inte mjukas upp.** Problemet är att den tillämpas
på ett system som fortfarande byggs om varje vecka. Vill man ha ett facit måste
radarn frysas: inga ändringar i trösklar, providers, identitet, källurval eller
prisväg under mätperioden. Annars kommer räknaren fortsätta nollställas strax
innan den betyder något.

### Två mobilfel till i Oddset-listan

Hittade vid en systematisk svepning av alla fem vyer på 390 px (mät mot
`documentElement.clientWidth`, inte `innerWidth` — den senare räknar in
scrollbredden och döljer precis det man letar efter):

1. **Hela sidan gick att dra i sidled, 36 px.** `.teams` ärvde
   `white-space: nowrap`, så lagnamn + badges + 🏋️-rankchip blev en obrytbar
   rad; chipet slutade på x=426 med en sida som är 390. Ligachipsen och
   navigeringen såg likadant ut i mätningen men är inneslutna i egna
   `overflow-x: auto`-behållare och är alltså avsiktliga. Fixat med
   `white-space: normal` på just `.teams`; de tre 1X2-rutorna ligger kvar på
   samma rad (verifierat: identisk `offsetTop`).
2. **`.epill` bröts mitt itu.** `+3%` delades mellan `+3` och `%`, alltså en
   grön pill i två stycken, och gjorde den 1X2-rutan 84 px hög mot grannarnas
   63. `white-space: nowrap` på pillen; alla rader mäter nu 63/63/63.

Metodnot för nästa gång: leta efter element som spiller över OCH saknar en
ancestor med `overflow-x: auto|scroll|hidden`. Utan det villkoret drunknar de
verkliga felen i avsiktligt svepbara listor.

## Tillägg 2026-08-18 (kväll) — identiteten var buggen, inte oddsen

Samans iakttagelse: det är fel beteende att vi signalerar matcher utan
liveodds, eftersom odds finns i 99 % av fallen. Och: prematch-kopplingen borde
gå att återanvända när matchen väl är live.

Båda stämde. **Uppmätt: 66 av 187 signaler (35 %) föll på
`no_canonical_match`. I 64 av dem FANNS Oddset-matchen, hade `kambi_id` och
började inom några minuter.** Det som fällde dem var att ETT lagnamn stavades
annorlunda hos livekällan:

| livekort | Oddset |
|---|---|
| `Dep. A Coruna` | `Dep. La Coruña` |
| `Charleroi` | `Sporting de Charleroi` |
| `Nordsjaelland` | `FC Nordsjälland` |
| `Genk` | `KRC Genk` |
| `Club Brugge KV` | `Club Brugge` |
| `LA Galaxy` | `Los Angeles Galaxy` |
| `IBV Vestmannaeyjar` | `ÍB Vestmennaeyjar` |

Motståndaren matchade exakt i varje fall. **Noll av de 64 var tvetydiga.**

`_canonical_match` har därför samma trestegsstege som provider↔provider-länken
redan använder, och lånar `live_radar`s hjälpfunktioner i stället för att
skriva en parallell:

1. båda lagen strikt (oförändrat, går alltid först);
2. båda lagen i kontext;
3. **ETT lag räcker** — men bara inom `LINK_START_TOLERANCE_MIN` och med
   samma truppmarkör på båda sidor. Beviset är att ett lag spelar en match i
   taget: delar två rader liga och avspark, och är ett lag samma, kan de
   omöjligen vara olika matcher.

Steg 3 tar **inte** den närmaste av flera kandidater. `_pick` får välja på
avspark när båda lagen är bevisade, men med bara ett lag är "närmast i tid" en
gissning. Två kandidater ⇒ inget pris. Låst av
`CanonicalMatchTests` (ett lag räcker, strikt går före, tvetydighet avslås,
truppmarkör avslås, fel liga avslås, för stor avsparksskillnad avslås,
spegelvänd orientering länkas).

Ommätt efter ändringen: **64 av 66 länkas nu, alla 64 med `kambi_id`.** De två
kvarvarande hade ingen Oddset-match alls i fönstret.

Notera vad detta INTE är: signalerna slutar inte sparas när priset saknas. Att
utesluta oprissatta signaler ur journalen vore selektionsbias — en bok som
stänger marknaden när den är osäker skulle då tysta just de matcherna ur sin
egen serie. De räknas fortsatt i täckningen och bara de prissatta ingår i ROI.
Journalen har redan ett prisfilter i UI:t för den som bara vill se de spelbara.

## Tillägg 2026-08-18 (kväll) — tidskravet i grinden

Samans beslut: antalet matcher ska väga tyngre än antalet dagar. Fattat när
v10 hade **noll rader**, alltså utan att kunna se vad ändringen gör med ett
pågående resultat — vilket är enda tillfället en grind får röras.

Gamla kravet var 60 dygns SPANN. Två problem:

1. med den takt kohorten faktiskt fylls binder det långt efter matchkravet och
   skjuter beslutet månader framåt utan att tillföra bevis;
2. **spann mäter avståndet mellan första och sista observationen, inte
   spridningen.** 200 signaler på tre dygn med 60 dygn emellan hade passerat.
   Kravet gjorde alltså inte det man trodde att det gjorde.

Kravet är därför delat i två som tillsammans mäter det spannet försökte proxa
för: `BLIND_MIN_DAYS = 30` (grovt säsongsskydd — en Över-signal mätt enbart i
augusti behöver inte hålla i november) och nya
`BLIND_MIN_MATCHDAYS = 20` distinkta dygn (det direkta måttet på klustring).
`n_match_days` och `required_match_days` ligger i summeringen.

Matchkravet 200 är OFÖRÄNDRAT. Det är den statistiska styrkan; dagarna är bara
ett skydd mot att de 200 kommer från ett enda tillfälle.

## Tillägg 2026-08-19: liverättningen visar VILKA rader som lever

Nivåtabellen sa "2 rader kvar till 8 rätt" utan att peka ut någon av dem. På en
256-raderskupong är det inte handlingsbart — Saman kunde se antalet sjunka men
inte vilka rader det gällde, alltså inte heller vad han skulle heja på utöver
`cheer`s per-match-svar.

### Nytt i `pool_played.live_status`

`_alive_rows` returnerar tre fält:

- `alive_rows` — per överlevande rad: `n` (radnummer i kupongen, samma ordning
  som filen som lämnades in), `row`, `secure`, `possible` och `open` (tecknet
  raden behöver i varje kolumn som ännu inte är avgjord);
- `alive_rows_total` — hur många som lever mot LÄGSTA redovisade nivå;
- `alive_rows_open_cols` — de kvarvarande kolumnerna, i kupongordning.

Listan är sorterad på säkrade rätt fallande och kapad vid `ALIVE_ROWS_MAX`
(40). Kapningen är säker för det som betyder något: alla rader har lika många
öppna kolumner, så `possible = secure + n_öppna` och sortering på `secure` är
identisk med sortering på `possible` — de rader som kan nå TOPPNIVÅN ligger
alltid först och faller aldrig utanför kapet.

Öppna kolumner är exakt `_decided()`s komplement, så en struken match och ett
obelagt förlängningstecken räknas som kvarvarande. Raden visas därmed med det
tecken den BEHÖVER, aldrig med ett tecken vi gissat åt Svenska Spel.

### UI: listan hänger på en VALD nivå, inte på "kan nå något"

`AliveRowsTable` i `App.jsx` har nivåknappar som bär `alive_per_level`. Det är
nödvändigt, inte kosmetiskt: Topptipset har åtta matcher men bara 8 rätt delar
potten, medan nivåtabellen börjar på `width − 3` = 5. "Lever mot golvnivån" var
därför 184 av 256 rader och sa ingenting. Med nivåval visar knappen `8 rätt 2`
exakt de två rader som fortfarande jagar potten.

Räknaren på knappen kommer från `alive_per_level`, som är räknad på HELA
kupongen och alltså sann även när radlistan är kapad. Är den kapad står det
"Visar 40 av 184" — tabellhöjden får aldrig läsas som totalen.

Mobil (uppmätt vid 375 px): tabellen var 330 px i en 297 px behållare, så den
TREDJE kvarvarande matchen hamnade utanför — exakt den man behöver.
`max`-kolumnen (45 px) döljs därför på mobil; den är `rätt nu` plus antalet
kvarvarande matcher och alltså helt härledbar. Rubriken bär matchnumret, som
binder kolumnen till liverättningen strax ovanför, och lagnamnet visas bara på
desktop. Efter ändringen: 297 px i 297 px, ingen klippning och ingen
sidoscroll på sidan.

### Buggfix som ändringen avslöjade: kortet unmountades var 60:e sekund

`PlayedPanel.load` hämtar i två steg — först `?live=false` för lokal data,
sedan `?live=true`. Steg ett satte `live_pending: true` UTAN att bära med sig
föregående `live`, så `live` var odefinierad i ~en halv sekund var 60:e sekund.
Hela kortkroppen ligger bakom `{live && (...)}` och unmountades alltså
regelbundet, vilket nollställer allt tillstånd i den: radlistan man just slagit
upp slog igen av sig själv en gång i minuten.

`load` behåller nu föregående `live` per kupong-id medan den nya hämtas. Den
visade statusen är en verklig observation som är högst en minut gammal, och
`live_pending` säger redan att en ny är på väg — att blanka den var varken
färskare eller ärligare. Verifierat i drift: radlistan stod öppen med samma
valda nivå 102 sekunder efter öppning, alltså över minst en hel uppdatering.

### Driftkvitto

Mätt på de två riktiga Topptipset 4278-kupongerna med tre matcher kvar:

```
alive_per_level: {'8': 2, '7': 21, '6': 86, '5': 184}
öppna kolumner:  [6, 7, 8]
  rad  70: 5 säkra, max 8, behöver [1 2 1]
  rad 192: 5 säkra, max 8, behöver [1 2 2]
```

762 backendtester gröna (`AliveRowsTests`: sortering och innehåll, död rad
utesluts, kapning med sann total, struken match och obelagd förlängning som
öppna kolumner). Frontend lintad och byggd.
## Tillägg 2026-08-19 — poolens liverättning fick samma källtålighet

Det här är **inte** en ändring av liveblindtestet. Det gäller Historiks kort för
redan spelade poolkuponger, där chansen på kvarvarande vinstnivåer behöver
live-1X2 och tidigare bara frågade Kambi.

Topptipset 4278 gav ett konkret femmatchersprov. Bara Atlético Madrid–Málaga
hade öppet Kambi-1X2. Nijmegen–Bodø/Glimt och Slovan–Celje fanns i listan men
Kambi returnerade inget öppet 1X2; Celtic–LASK saknades och Hapoel–Sabah hade
namndrift. Ninjas råa livepayload bar samtidigt komplett, öppet 1X2 på alla
fem enligt den dåvarande tolkningen. **Korrigering 2026-08-25:** typ-id 7
visade sig vara `Ingen` i en syntetisk nästa-mål-marknad, inte kryss. Bara den
kanoniska `sportMarketId=70472` och kryss-id 2 får nu användas. Den ursprungliga
täckningsslutsatsen var därför för optimistisk; fallbackkedjan är fortfarande
rätt, men hellre modell/Pinnacle än en felmärkt Ninja-marknad.

Ny ordning i `pool_played.attach_live_odds`:

1. Kambi-live-1X2, precis som förut;
2. Ninja/Altenar `GetLiveEvents`, öppna trevägsutfall och separat
   suspensionsstatus;
3. Pinnacle: livebulken identifierar matchen, men moneyline hämtas om via varje
   matchup-barns detaljväg. Färskaste öppna barn väljs och HTTP Age måste vara
   högst 90 sekunder;
4. först därefter den gamla, tydligt märkta modellen ur ställning, spelad tid
   och spelbolagets prematchpris.

Provideridentiteten är fail-closed. Båda lagen i samma orientering går först;
spegelvända event avslås eftersom 1 och 2 då byter betydelse. En kontextlänk
kräver en strikt sida. Bara ett lag får räcka först när båda avsparkarna kan
läsas, skiljer högst 30 minuter och kandidaten är unik. Kambi-liveevent
exponerar därför även `start` nu.

`probs_source` följer varje pågående match och summeras i
`chance_live_source_counts`. Historiktexten kan därför säga exempelvis
`5 prissatta live (SvS 1, Ninja 4)` i stället för att bara påstå att ett pris
fanns. Ingen observation skrivs till DB: detta är en read-only aktuell
kupongchans, inte ett nytt facit. Systembyggare, tips, CLV, signal-ROI och
settlement läser inget av fälten.

Regressioner finns för Ninjas kanoniska kryss-id och för att typ 7/`Ingen`
avslås, suspension, Pinnacles
moneyline/färskaste barn/cacheålder, Kambi→Ninja→Pinnacle-ordningen,
Pinnacles 90-sekundersstopp och entydig ensidig identitet. Efter sammanfogning
med liverättningens radlista: 767 backendtester, 12 frontendtester, ESLint och
produktionsbygge gröna.
