# Maxtester — matematiskt 41 472 och reducerat 20 000

Datum: 2026-08-29  
Status: förregistrerade framåtriktade researchtest när committen som innehåller
detta dokument är driftsatt. Inga riktiga spel läggs.

## Verifierade gränser

Svenska Spels aktuella officiella sida för
[Externa Systemspel](https://spela.svenskaspel.se/stryktipset/externa-systemspel)
anger:

- en fil får innehålla antingen enkelrader (`E`) eller matematiska system
  (`M`), aldrig en blandning;
- högst 10 000 enkelrader eller 1 000 M-system per fil;
- maximal insats 20 000 kr.

Spelkompisens reducerade förslag levereras som explicit uppräknade E-rader.
Den tillämpliga officiella maxinsatsen är därför **20 000 kr/rader**, inte
cirka 25 000. Eftersom en fil bara får innehålla 10 000 E-rader kräver en
eventuell manuell leverans två separata 10 000-radersfiler. Spelkompisen
laddar inte upp eller betalar automatiskt.

För matematiska system är största 13-matchsformen **41 472 rader**:
`4` helgarderingar och `9` halvgarderingar ger `3^4 × 2^9 = 41 472`.
Formen finns i Svenska Spels officiella historiska
[spelregler](https://cdn1.svenskaspel.net/content/cms/documents/c91b3a83-2b4f-469d-9e2c-df4807905716/1.6/spelregler-stryktips-europatips-maltips-topptips-joker-180321.pdf),
och Svenska Spel publicerade 2026 ett aktuellt exempel på ett
[matematiskt system om 34 992 rader](https://om.svenskaspel.se/nyheter-sport-casino/daniel-jadden-soderberg-prickade-in-13-ratt-pa-tva-system-vann-33-miljoner-pa-stryktipset/).
Den nya matematiska serien sparar själva M-systemets fulla kartesiska
radmängd för facit, men UI säger uttryckligen att 41 472 inte ska laddas upp
som en enda extern E-fil.

## Varför 40 000-piloten avslutas

`max40-v1-b40000-ev50` och `max40-v1-b40000-ev80` valde de 40 000 högst
rankade enskilda raderna ur samtliga `3^13 = 1 594 323` utfall. Det är ett
reducerat radurval, även om beloppet låg nära det matematiska maxet.

Nycklarna får aldrig byta betydelse. Piloten ligger därför kvar oförändrad i
ledgern och i Max-tester-vyn som **40 000-pilot · avslutad**, men
`research_families_for()` schemalägger den inte längre och poolhälsan kräver
inga nya max40-frysningar.

## Nya frysta kontrakt

Gemensamt:

- Produkter: Stryktipset och Europatipset. Topptipsets hela utfallsrum är
  bara `3^8 = 6 561` och ingår inte.
- Start utan bakfyllning: Stryktipset 4968 och Europatipset 2603. Serverns
  öppna omgångar och framtida h3-fönster verifierades 2026-08-29 kl. 12:18
  CEST.
- Horisonter: T−3 timmar och T−20 minuter med ledgerns vanliga toleranser.
- Armar: EV medel (`medel`, värdevikt 0,50) och EV högt (`tuff`, 0,80),
  parade på samma produkt, omgång, horisont och marknadsobservation.
- Research-only: ingen automatisk promotion, ingen påverkan på standardmodell,
  kupongbyggare eller riktiga spel.
- En frysning som inte får exakt föreskrivet radantal sparas inte som giltig.

### Matematiskt max

Nycklar: `mathmax-v1-b41472-ev50`, `mathmax-v1-b41472-ev80`.

Byggaren låser först formen till nio halv- och fyra helgarderingar. Profilen
avgör vilka fyra matcher som får tredje tecknet och vilka två tecken som tas
i övriga matcher. Därefter materialiseras **alla** kombinationer. Tester
kräver exakt 41 472 unika rader, fyra helgarderingar, nio halvgarderingar och
noll spikar. Detta är ett M-system, inte en topplista av fristående rader.

### Reducerat max

Nycklar: `reducedmax-v1-b20000-ev50`, `reducedmax-v1-b20000-ev80`.

Byggaren grovrankar hela `3^13` och behåller exakt 20 000 explicita
E-rader per arm. Detta följer samma full-universe-metod som den avslutade
40 000-piloten, men med en ny familj, nya nycklar och verifierad leveransgräns.

## Mätning och UI

API:er:

- `GET /api/pool/mathmax`
- `GET /api/pool/reducedmax`
- `GET /api/pool/max40` (historisk pilot)
- `GET /api/pool/systems/detail` och `/api/pool/systems/live` för exakt kupong,
  slutligt facit respektive preliminär liverättning.

Huvudfliken **Max-tester** har tre underflikar. De aktiva serierna visar
paröverlapp, exakt fryst kupong, odds/streck, X-vikt, liverättning, slutligt
facit och kontrafaktisk ROI. 40 000-piloten markeras avslutad. Poolhälsan
larmar `mathmax_freeze_incomplete` och `reducedmax_freeze_incomplete`
separat; den gamla piloten kan inte göra driftstatus röd.

Resultat ska brytas ned per produkt och horisont. Efter 10 kompletta par får
de beskrivas som preliminära. Minst 40 kompletta parade omgångar per
jämförelse krävs före bootstrap-intervallbaserad slutsats. Ingen promotion
sker utan en ny, explicit förregistrering.

## Drift och nästa AI-session

1. Ändra aldrig parametrar eller startomgång under befintliga config_key:er.
2. Bakfyll aldrig missad h3/m20 efter att horisonten passerat.
3. Kontrollera `/api/health`, `/api/pool/mathmax`,
   `/api/pool/reducedmax` och Max-tester-vyn efter deployment.
4. Tolka simulerad kostnad/utdelning som kontrafaktisk, aldrig spelade pengar.
5. En hög överlappning mellan armarna är ett resultat. Ändra inte urvalet
   under v1 för att skapa artificiell skillnad.
6. Officiellt facit kommer bara från settlementlagret; livebilden är ett
   rent läsande ögonblicksläge.
