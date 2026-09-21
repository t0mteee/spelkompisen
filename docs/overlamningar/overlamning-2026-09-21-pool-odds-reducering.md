# Överlämning 2026-09-21 — poolodds, riskvisning och reduceringsscreening

## Uppdrag och avgränsning

Saman bad att fortsätta rekommendationerna: utreda tio oddsluckor, pröva
en reducering som beaktar hela kupongens täckning, visa verklig koncentration
och behålla referensen. Arbetet görs i separat worktree från serverns
`9df2b54`. Inga gamla tjänster startas och inga gamla kuponger ändras.

## Oddsen: vad som faktiskt var fel

Stryktipset 4971 hade bara 3/13 giltiga sharpmatcher vid 20-minutershorisonten.
SQLite lästes read-only på servern. Nedan är belägg, inte antagande om utbud:

| Match | Belägg och slutsats |
|---|---|
| 1 Nottingham–Coventry | Diagnostiken har Nottingham Forest–Coventry City, exakt avspark 16:30Z, 215 observationer. Coventry-sidan fick 0. Belagt namnfel. |
| 3 Everton–Ipswich | `pin:1635909175`: Everton–Ipswich Town, exakt 14:00Z. Ipswich var ett avvisat delnamn. |
| 4 Newcastle–Hull | `pin:1635918924` och 24 diagnostiska observationer av Newcastle United–Hull City, exakt 14:00Z. Newcastle-sidan fick 0. |
| 6 Burnley–Derby | 22 diagnostiska observationer av Burnley–Derby County, 14:00Z. Derby fick 0. |
| 7 Lincoln–Swansea | Kandidaten Lincoln City–Swansea City finns i diagnostiken för match 4, 418 observationer, exakt 14:00Z. Båda poolkortnamnen saknade alias. Dessutom Pinnacle-id 1636463846 på svs:1028143005. |
| 8 Portsmouth–Blackburn | `svs:1028143014` bär Pinnacle-id 1636463907 och namnet Blackburn Rovers. Separata `pin:1636673667` är HÖRNOR och får aldrig användas som bevis för målmarknaden. Råa Pinnacle-namnet är inte bevarat på SvS-raden: namnfelet är en belagd inkompatibilitet med den lagrade namnformen, inte bevis för hela historiska capturekedjan. |
| 9 QPR–Preston | 481 observationer av Queens Park Rangers–Preston North End, exakt 14:00Z. Preston-sidan fick 0. |
| 11 Luton–Bradford | Ingen relevant sparad Pinnacle-kandidat hittades. Utanför ligorna med full Oddset-historik. Orsak fortfarande okänd. |
| 12 Oxford–Cambridge | Samma begränsning: inga säkra sparade kandidatbelägg. |
| 13 Sheffield W–Stockport | Samma begränsning. Sheffield United i närhetsloggen är INTE bevis för Sheffield Wednesday. |

**Levererad ändring `pool-name-v3`:** åtta poolspecifika alias
(Coventry, Ipswich, Newcastle, Derby, Lincoln, Swansea, Blackburn, Preston).
Globala Oddset-/modellalias orörda; V2.2 fortsätter oförändrat.
Entydighetsvakt, truppmarkörer, tidsfönster och trösklar sänks inte.
Hörn-/kortnamn spärras explicit i poolens matchning.

Två andra fel var viktiga:

- Diagnostiken sparade en enda kandidat efter den strikta matchpoängen.
  Ett korrekt delnamnspar fick 0 på ena sidan och trängdes undan av ett
  irrelevant par. Nu sparas upp till fem sökledtrådar. Sökrankningen kan
  visa delnamn; den kan ALDRIG godkänna dem eller leverera odds. Befintlig
  diagnostiktabell används, ingen schemamigration eller historisk ändring.
- Täckningsrapporten såg bara `pin:`-id och missade SvS-rader med
  Pinnacle-id. Den tog dessutom en hörnrad som möjligt målbevis och kallade
  fuzzy-par för ”korrekt par”. Nu läses alla Pinnacle-länkade rader,
  sidomarknader utesluts och okänd identitet/tid/tvetydighet redovisas.

Detta återställer INTE de missade historiska horisonterna. Nya observationer
krävs för att mäta förbättringen. `pit-v4`/`pit-total-v1` behålls inom Samans
tidigare insamlingsbeslut, med datumnot i båda manifestdokumenten.

## UI

Historik → Tester → öppna kupong: andelen sparade rader står direkt under
1/X/2 för reducerade system, exempelvis 5,3 %. Det är INTE matchens
vinstchans. Matematiska kuponger behåller rena teckenrutor utan 33/33/33.
Befintlig text om saknade tecken respektive bortreducerade kombinationer
fanns redan och har inte dubblerats. Mobilrutorna behåller sin bredd.

## Ny reducering: skriven, körd, inte promoverad

`app/pool_portfolio.py` och `scripts/prova_pool_portfolio.py` är ett
fristående read-only-test. Ingen produktionsbyggare importerar prototypen.
Specifikation och körkommando: `docs/pool-portfolio-screen-v1-2026-09-21.md`.
Fasta parametrar skrevs före första resultatkörning och har inte optimerats
mot omgångens facit. Ordinarie builder, budget, frysning och X-riskgolv är
referens. Samma saknade-pott-kriterium för båda armarnas ROI.

Funktionstest på Stryk 4971, 20 min, EV50:

| Budget | Referens bästa rätt | Kandidat bästa rätt | Största teckenandel ref → kandidat | Bytta rader |
|---|---:|---:|---|---:|
| 512 | 7 | 9 | 99,0 % → 96,5 % | 470 |
| 20 000 | 9 | 10 | 93,3 % → 87,3 % | 11 686 |

20k-referensen reproducerar EXAKT den sparade kupongens radmängd.
512 är två ombyggda armar på samma frystidsunderlag, inte en historiskt spelad kupong.
Ingendera körningen utlöstes till fallback av EV-/teckengolven.

Separat simuleringssample (16 384 utfall, INTE optimeringssamplet):
20k-referens → kandidat, sannolikhet för minst 13/12/11/10 rätt:
12,23/39,64/70,78/90,28 % → 4,97/38,82/84,00/99,03 %.
**Kandidaten offrar för mycket toppträffchans. Inte generellt bättre.**
De analytiska rad-EV-värdena är inte uppmätt ROI och ingen lönsamhet påstås.
Pengafacit utelämnas här eftersom inte samtliga potter kan identifieras
med samma kriterium för båda armarna. Samplet är modellberoende och
historiken redan sedd: absolut inget promotionsbevis.

## Vad Claude/Codex ska göra härnäst

1. Efter nästa relevanta poolvarv: kör `pool_tackning_rapport.py --sedan 2026-09-21`.
   Läs femkandidatsloggen för kvarvarande avslag. Särskilt League One-matcherna
   behöver bevis för faktisk Pinnacle-listning; inget ”de erbjuds inte” utan observation.
2. Kör den frysta screeningen på ALLA tillgängliga tidsriktiga omgångar,
   samma budget per jämförelse (256/512/5000/20000), produktvis. Mät runtime,
   oberoende sample-variation, toppträffchans, övrig täckning, ROI-bortfall
   och hur ofta fallback inträffar. Ändra inte v1:s vikter under körningen.
3. Nästa kandidat behöver en explicit avvägning mellan toppträff och
   lägre vinstnivåer, exempelvis ett förregistrerat toppchansgolv. Ett
   rad-EV-golv skyddar inte toppträffchansen. Detta är särskilt viktigt på
   Topptipset där 7 rätt inte ger vinst. Ny specifikation, inte tyst v1-ändring.
4. Först efter den mekaniska kontrollen: separat forward-key/starttid/grind.
   Standard och gamla testserier ska fortsätta oförändrat. Ingen ny aktiv
   timer, ingen belastning i ordinarie poolvarv, ingen automatisk betting.

`cli.py gater` lästes: 62 grindar, 0 läsfel. Poolopt 42 parade omgångar har
nått skördestorlek; den preliminära parade granskningen ger inget säkert
stöd för promotion. V2.2 207/217/217 av 300 och fortsatt ligagap;
radar 231 prissatta/avgjorda men 17/30 dygn och 18/20 matchdygn.
Full formell poolopt-skörd enligt eget protokoll återstår; inte nya fria parameterprov.

## Verifiering och drift

27 riktade tester gröna: namn, entydighet, sidomarknader, diagnostik,
rapportens SvS-id, bitset-täckning mot brute force, determinism, budget,
EV-/teckengolv och frånvaro av facit/slutstreck i bygginput.
Full kontroll (backend, lint, frontendtester) grön och produktionsbygge klart.
Ingen DB-migration. Commit/push och driftefterkontroll antecknas nedan.
