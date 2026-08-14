# PH5 forward — riktigt Stryktipstest från omgång 4966

Datum: 2026-08-15. Skriven före första frysningen och före omgång 4966:s
spelstopp 2026-08-15 15:59 CEST.

**Status:** aktiv i drift från commit `587ed51`; ingen verklig forwardrad ännu
fryst eftersom T−3 h-fönstret öppnar 2026-08-15 12:59 CEST.

Driftkvittot före fönstret kördes mot en SQLite-kopia och den riktiga öppna
omgång 4966-payloaden:

- T−178 min skapade 16 system: 12 ordinarie + 4 PH5;
- T−18 min skapade ytterligare 16 system för den andra horisonten;
- ett identiskt återförsök skapade 0 dubbletter;
- samtliga åtta PH5-rader hade exakt 5 000 rader, kostnad 5 000 kr,
  `timely=1` och fyra unika radmängder per horisont;
- produktionsdatabasen ändrades inte av torrtestet;
- 712 backendtester och frontendens produktionsbygge var gröna;
- `/api/health` var `ok` efter driftsättning.

## Enkelt uttryckt

Det historiska PH5-testet spelade om gamla omgångar med information som i
praktiken låg nära slutläget. Det var ett snabbt sållningstest, inte ett äkta
framtidstest.

Detta test gör tvärtom: appen sparar exakt vilka rader varje metod hade valt
**innan** spelstopp. Efter att omgången avgjorts rättas samma sparade rader
automatiskt. Ingen information från framtiden kan läcka in och inget spel
lämnas in.

## Fyra jämförbara system

Alla spelar exakt 5 000 rader per omgång:

| Nyckel | Innebörd |
|---|---|
| `ph5-v3-b5000-medel` | vår riktiga värderadsbyggare |
| `ph5-v3-b5000-byggarslump` | slump ur samma kandidatuniversum som byggaren |
| `ph5-v3-b5000-favoritrad` | marknadens mest sannolika rader |
| `ph5-v3-b5000-folkrad` | de mest streckade raderna |

De fryses vid två redan använda horisonter:

- `h3`: omkring tre timmar före spelstopp;
- `m20`: omkring tjugo minuter före spelstopp.

Omgång 4966 ska därför få åtta forskningssystem: fyra vid vardera horisonten.
Raderna är deterministiska för samma input; om ett insamlingsvarv försöker
igen skapas inte ett nytt slumpresultat eller en dubblett.

## Varför 5 000 trots att historikgrinden inte passerade

På 216 gamla Stryktipsomgångar slog 5 000-radersbyggaren byggarslump tydligt,
men osäkerheten mot folk- och favoritraden gick fortfarande över noll. Den får
därför **inte** ersätta ordinarie champion eller beskrivas som bevisat bättre.

5 000 väljs här eftersom det är den faktiska budgetfrågan och den starkare av
de två historiska punkterna. Syftet är datainsamling, inte promotion.

## Låsta säkerhetsregler

- Nycklarna är `research-only` och `promotion_eligible=false`.
- De finns inte i `BENCHMARKS`, `benchmarks_for` eller championrapportens
  BH-FDR-familj.
- De ändrar inte ordinarie systemförslag, notiser eller Autopool.
- De kan aldrig lämna in ett spel automatiskt.
- Ingen historik bakfylls: kohorten börjar med Stryktipset 4966.
- Hälsokontrollen larmar separat om någon av de fyra researchraderna saknas,
  utan att de kan maskera ett saknat ordinarie benchmarksystem.

## Hur resultatet ska läsas

En enda lördag kan visa att hela kedjan fungerar och ge ett konkret facit:
vilka rader som valdes, bästa antal rätt, rättfördelning, beräknad utdelning
och ROI. Den kan inte bevisa att en metod är bättre — poolutfall är för
slumpiga.

Testet fortsätter därför på kommande Stryktipsomgångar. Först efter minst 40
parade, tidsriktiga omgångar får metoden utvärderas för eventuell promotion.
Beslutet ska då jämföra värderaderna med alla tre kontrollerna inom samma
horisont. En framtida promotion kräver en ny, uttrycklig beslutsgrind; dessa
researchnycklar promoveras aldrig av befintlig kod.

## Var det följs

Efter första frysningen syns raderna via Poolspel → Historik → Alla
konfigurationer och i systemdetaljen för omgång 4966. API:t
`/api/pool/systems` märker dem med:

- `research: true`;
- `promotion_eligible: false`;
- `method`: `varderader`, `byggarslump`, `favoritrad` eller `folkrad`.

Poolhälsan visar `research_freeze_incomplete` om frysningen saknas efter ett
tillåtet insamlingsvarv.
