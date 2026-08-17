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
