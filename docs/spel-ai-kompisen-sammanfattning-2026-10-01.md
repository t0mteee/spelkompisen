# spel-ai-kompisen — sammanfattning för godkännande

**Datum:** 2026-10-01 · **Skriven av:** Claude · **Bygger på:**
`docs/spel-ai-kompisen-plan-2026-10-01.md` inklusive Codex ändringar (commit 3e288d6).
Inget byggs innan Saman har godkänt avsnitt 7.

## 1. Kort

- Agenten arbetar i ett eget, privat sidoprojekt på servern och får ändra allt där.
- Spelkompisen, dess databas och facitmotorn rörs inte av agenten.
- Klockan sköts av vanliga schemalagda jobb. Agenten tänker, bygger och förklarar.
- Du får en notis när något är klart, går fel eller behöver ditt svar, samt poolförslag
  6 h och 30 min före spelstopp.

## 2. Stegen för att komma igång

| # | Steg | Vem | Läge |
|---|---|---|---|
| 1 | Claude inloggad på servern | du | ✅ klart 1/10 |
| 2 | Vakten i Spelkompisen | Claude | ✅ i drift 1/10 |
| 3 | Godkänn beslutslistan i avsnitt 7 | du | väntar |
| 4 | Privat repo, egen port (8003/5176) och egen databas | Claude | efter 3 |
| 5 | Facitmotorn på skyddad plats. Frysning av förslagen vid 6 h och 30 min, även Spelkompisens standardförslag vid samma tidpunkt som jämförelse | Claude | efter 3 |
| 6 | Sandbox och behörighetslista. Prov som visar att agenten inte kan skriva i Spelkompisen eller facitmotorn | Claude | efter 3 |
| 7 | Agentsessionen: tmux, launchd och Remote Control, plus minnesfiler | Claude | efter 6 |
| 8 | Notiskanal och 🤖-vy, med en provnotis till dig | Claude, du installerar appen | efter 7 |
| 9 | Provvecka med reducerat schema | automatiskt | efter 8 |
| 10 | Utvärdering efter en vecka: kvot, kvalitet och antal notiser | du och Claude | dag 8 |

Steg 4–8 tar ungefär 1–2 dagar.

## 3. Det som sker automatiskt

### Utan AI (vanliga schemalagda jobb)

| Jobb | När | Notis till dig |
|---|---|---|
| Insamling i Spelkompisen | som i dag | nej |
| Vakten | var 30:e min, tester varje natt | nej, larm på Idag |
| Poolförslag 1, fryses | 6 h före spelstopp, för valda spel | ja |
| Poolförslag 2 och jämförelse mot förslag 1 | 30 min före spelstopp | ja |
| Facit för förslag och modeller | efter avgjorda matcher och omgångar | i dagsrapporten |
| Kontroll att agentsessionen lever | var 30:e min | ja, om den legat nere i mer än 30 min |

### Med AI (agenten)

| Arbete | När | Notis till dig |
|---|---|---|
| Morgonrunda: larm, felsökning, rättningar, prov av appen, dagsrapport | 07:00 | ja, när den är klar |
| Forskningspass, ett mål i taget enligt kön | 10:00, och 15:00 från vecka 2 | ja, när det är klart |
| Motivering till poolförslagen | direkt efter 6 h och 30 min | ingår i förslagsnotisen |
| Utredning vid nytt rött larm | vid behov, högst 3 per dygn | ja |
| Driftsättning eller återställning av den egna appen | när agenten beslutar, efter gröna tester | ja, alltid |
| Genomgång av gränssnittet | söndagar | ja |

Exempel: Stryktipset 4973 stänger lördag 3/10 kl 15:59. Förslagen kommer 09:59 och 15:29.

## 4. Det som alltid kräver ditt beslut

- Ändringar i facitmotorn, poängreglerna eller historiska rader.
- Allt i Spelkompisen: kod, tjänster och databas. Agenten läser bara.
- Att flytta en idé från sidoprojektet till Spelkompisen. Det sker som ⚖ efter facit.
- Högre budget: fler körningar, mer disk eller mer CPU.
- Varje spel. Du laddar upp och betalar själv; agenten lägger aldrig spel.

Detta får aldrig göras, oavsett beslut: lösa antibot-utmaningar, logga in hos källor,
röra `svs` eller `vm`.

## 5. Hur du meddelas

| Kanal | Vad |
|---|---|
| Notis på mobilen | klart, misslyckat, behöver ditt svar, poolförslag, driftsättning eller återställning, missat förslag |
| Chatten i Claude-appen (Remote Control) | du frågar, svarar eller skriver "paus" |
| 🤖-vyn i sidoprojektet | fulla loggar, förslag med motivering, facit per modell, öppna ⚖ |
| Idag i Spelkompisen | vaktens driftlarm, som nu |

En notis innehåller aldrig kuponger, insatser eller loggar — bara vad som hänt och en
länk till 🤖-vyn.

## 6. Claudes synpunkter på Codex version

**Bra och bör stå kvar:**

1. Vanliga jobb äger klockan; agenten är aldrig den enda klockan. Ett missat förslag
   markeras som missat och bakfylls aldrig.
2. Teknisk isolering i stället för regler i en prompt.
3. Båda förslagen sparas med fullständigt underlag och får facit, även när slutsatsen
   är att avstå.
4. 6 h och 30 min hör till sidoprojektet och ändrar inte Spelkompisens h3 och m20.

**Bör ändras eller läggas till:**

1. **Färre notiser.** En notis vid både start och slut ger 8–12 notiser per dygn.
   Förslag: notis när något är klart, misslyckat eller behöver svar; startnotis bara vid
   driftsättning. Att tystnad aldrig får betyda klart löses av att vakten larmar när ett
   schemalagt jobb inte har rapporterat i tid.
2. **Jämförelse vid samma tidpunkt.** Facitmotorn bör även frysa Spelkompisens
   standardförslag (256 kr medel) vid 6 h och 30 min. Annars finns inget att jämföra
   agentens förslag med parat.
3. **Facitmotorns kod utanför agentens repo.** En skyddad datakatalog räcker inte om
   koden som räknar facit ligger i repot som agenten får ändra.
4. **30-minutersförslaget börjar byggas 35 min före stopp,** så att det når dig senast
   30 min före och du hinner ladda upp.
5. **Sandboxen måste vara påtvingad.** Claude Code kan köra enskilda kommandon utanför
   sandboxen; den möjligheten ska vara avstängd för agenten. Provet i steg 6 ska visa att
   en skrivning i Spelkompisen nekas.
6. **SQLite i WAL-läge.** Även en skrivskyddad läsare kan behöva skriva i databasens
   `-shm`-fil. Sandboxen behöver tillåta just den filen, annars kan läsningen fallera.
   Provas i steg 6.
7. **Notiskanalen.** Ett ntfy.sh-ämne kan läsas av alla som känner till namnet. Ett långt
   slumpat namn utan personlig data räcker. För agentens egna notiser kan Claude-appens
   notiser vara privatare; det provas i steg 8.
8. **Paus.** Det behövs ett sätt att pausa allt från mobilen: "paus" i chatten eller en
   knapp i 🤖-vyn. Alla jobb läser samma flagga.
9. **Avsnitt 10 i planen är obesvarat.** Codex har inte svarat på frågorna om
   databasläsning och delad kod kontra gaffel. Punkt 6 ovan täcker den första frågan.
10. **Topptipset-omgångar med stopp efter midnatt** ger notiser mitt i natten. Förslag:
    tysta timmar 23–07, utom "behöver ditt svar", och nattomgångar utanför urvalet.

## 7. Beslut att godkänna

Svara "ja till allt" eller ange numren du vill ändra.

| # | Beslut | Rekommendation |
|---|---|---|
| 1 | De tre villkoren: fast facitmotor, ingen dubbel insamling, fasta gränser | ja |
| 2 | Agentens mandat i sidoprojektet: brett och utan rutingodkännanden (Codex 4.1) | ja |
| 3 | Kvot: din Max-prenumeration delas. Tak vecka 1 | högst 6 AI-körningar per dygn |
| 4 | Repo | privat `t0mteee/spel-ai-kompisen` |
| 5 | Spel med förslag vecka 1 | Stryktipset och Europatipset |
| 6 | Var förslagen syns | bara i sidoprojektet, tills facit finns |
| 7 | Din spelbudget | agenten föreslår veckobudget och insats; du beslutar |
| 8 | Tillbaka till Spelkompisen | bara du, via ⚖, efter facit |
| 9 | Codex roll | Codex i Spelkompisen, agenten ensam i sidoprojektet |
| 10 | Gränser i facitmotorn | ärv Spelkompisens: pool ≥ 40 omgångar och FDR, odds CLV-grönt v2, live ≥ 200 matcher och 60 dagar |
| 11 | Resurser | låg prioritet, högst 20 GB disk |
| 12 | Notiser | slutnotis per jobb, startnotis bara vid driftsättning, tysta timmar 23–07 |
| 13 | Notiskanal | ntfy med slumpat ämne; prova Claude-appens notiser |
| 14 | 30-minutersförslaget | byggs från 35 min före stopp |
| 15 | Sofascore (separat beslut, backlog 21) | Flashscore som resultatkälla i Spelkompisen |
