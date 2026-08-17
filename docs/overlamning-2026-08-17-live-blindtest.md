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

Signaljournalen heter nu **Blindtestspel** och visar som standard enbart
`test_bet=true`:

- grönt ✓ för vinst/halvvinst;
- rött ✕ för förlust/halvförlust;
- ↔ för återbetalning och ⏳ när facit väntar;
- slutresultat, mål efter signalen och enhetsresultat på samma rad;
- `Odds vid beslutet` i stället för en lös Live Ö/U-kolumn.

Övriga signaler är dolda bakom **Visa även signaler som inte blev spel**.
Där anges uttryckligen om orsaken var saknat pris eller att raden var en
senare eskalering. Reglerna ovanför journalen använder ordet Testsignal och
förklarar Följer/Stark-flödet i vanlig svenska.

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
