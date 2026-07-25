# Modell mot sharp-close — förregistrerat snabbfacit

Datum: 2026-07-25. Mått och grind är skrivna innan utfallet räknades.

## Frågan

Förutsäger den frysta modellen vart den sharpa marknaden rör sig bättre än den
Pinnacle-sannolikhet som redan fanns vid samma tidpunkt?

Detta är en snabb forskningsgrind, inte bevis på spelvinst. Closingmarknaden är
ett starkt men inte ofelbart proxyfacit. Matchresultat och riktig CLV för
faktiska spel förblir slutmåtten.

## Kohort

- källa: befintliga `oddset_prediction_log`;
- fasta horisonter: T−24 h, T−3 h och T−20 min;
- endast captures inom respektive förregistrerade tolerans;
- modell och direkt Pinnacle måste vara fångade högst fem minuter från varandra;
- samma match, horisont, marknad, tecken och exakt lina;
- alla tecken i marknaden måste finnas både vid capture och close;
- `derived` sharp, gamla/stale priser och flyttad lina utan färsk exakt-line-close
  räknas inte;
- alla prediktioner ingår, även kontroller som aldrig blev flaggor.

En observationsenhet är en komplett sannolikhetsvektor för
`match × horisont × marknad × modellversion`. Bootstrap blockas per match, så
tre horisonter eller flera marknader i samma match får inte skapa falsk
precision.

## Mått

Primärt mått är parad förbättring i log score mot den frysta sharpen:

`gain = CE(P_close, P_sharp_vid_horisont) − CE(P_close, P_modell)`

Positivt är bättre: modellen låg närmare close än marknaden redan gjorde.
`P_close` används som mjuk mål-fördelning; inga enskilda matchutfall behövs.

Diagnoser:

- modellens genomsnittliga absoluta avstånd till close i procentenheter;
- sharpens motsvarande avstånd;
- parad MAE-vinst i procentenheter (sharp minus modell);
- modellens signerade bias mot close;
- andel modellavvikelser på minst 0,5 pp som pekade åt samma håll som
  close-rörelsen.

## Grind för modellarbete

Bedömning görs separat per marknad och semantisk modellversion, med horisonter
och ligor som nedbrytningar.

- minst 50 kompletta cases;
- minst 30 unika matcher;
- minst 7 kalenderdagars bredd;
- 90-procentigt matchblock-bootstrap-KI.

Status:

- **slår sharp**: undre KI-gränsen för log-score-gain är över 0;
- **sämre än sharp**: övre KI-gränsen är under 0;
- **oklart**: mängdkraven är uppfyllda men KI korsar 0;
- **samlar**: mängd- eller tidskravet saknas.

En ny feature, kalibrering eller modellversion får inte promoveras därför att
ett urval ser bra ut i efterhand. Den fryses som egen semantisk version och
måste slå den befintliga championen på samma parade close-mått. Hörnmodellen
kopplas sist till exakt denna grind; inget separat hörnmått väljs efter att
hörnutfallet har setts.

## Första läsning efter förregistreringen

Ledgerskörningen gav 213 säkra par av 261 kompletta modellvektorer. 48 saknade
en direkt, samtidig Pinnacle-vektor på exakt samma lina; de exkluderades. Inget
par hade motstridigt close.

- Äldre `m-d82792f7`, 1X2: 103 cases, 48 matcher, 8 dagar. Modellens MAE till
  close var 4,246 pp mot sharpens 1,682 pp. Log-score-gain var −0,012935 med
  90 % KI [−0,019512..−0,007336]. Status: **sämre än sharp**.
- Nuvarande `m-3c7789ac`, 1X2: 10 cases, 5 matcher, 0 dagars bredd. MAE
  4,217 pp mot 0,657 pp; log-score-gain −0,014585 med KI
  [−0,027662..−0,001279]. Status: **samlar**, eftersom mängdgrinden inte är
  uppfylld; siffran är inte en slutlig dom.
- Äldre Ö/U: 60 cases, 31 matcher, 8 dagar och log-score-gain 0. Modell och
  sharp är i praktiken samma sannolikhet eftersom totalnivån är sharp-ankrad.
- Äldre AH: 32 cases/16 matcher och negativ tidig riktning, men fortfarande
  **samlar** på mängdgrinden.

Konsekvensen är att modellen fortsatt är amber. Nästa modellfeature ska först
frysas som egen version och sedan bedömas med denna grind; ett bättre historiskt
resultat eller en snyggare avvikelselista räcker inte.

## Hörnstart

Hörnmodellen hade före denna plan bara sparat/visat förväntat antal hörnor.
Det finns därför ingen historisk fryst hörnsannolikhet att utvärdera utan
läckage. Från och med nästa nya horisont fryses
`corner-poisson-total-v1` på Pinnacles aktuella totalhörnslina som modellens
första hörnbaslinje. Den går genom exakt samma kohort, log-score-gain,
matchblock-bootstrap och versionsgrind som övriga marknader. Gamla sharp-hörn
bakfylls inte med en modell beräknad i dag.

Hörnmetodens version ligger i hörnradens `fair_source`
(`corner-poisson-total-v1`) och fogas till just hörngruppens
utvärderingsversion. Den globala målmodellens fingerprint ändras inte:
1X2/AH/ÖU och V2.2 ska inte få ny identitet bara för att en ny marknad börjar
samla facit.
