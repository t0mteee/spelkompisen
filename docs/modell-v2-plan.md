# Modell v2 — förregistrerad plan

Beslutad 2026-07-16 efter Backtest v4. Målet är en faktisk modellförbättring,
men utan att optimera trösklar eller funktioner på samma matcher som används
som bevis.

## Mål och avgränsning

V2 ska inte försöka ersätta en effektiv marknad med en fristående målmodell.
Pinnacles devigade sannolikhet vid samma fasta horisont är baslinjen. V2 får
bara lära en liten, regulariserad korrigering när tidsäker laginformation
motiverar det:

`p_v2 = softmax(log(p_sharp) + delta(features))`

Första versionen omfattar bara 1X2 i Allsvenskan och Eliteserien. Den körs i
skuggläge/amber, notifierar aldrig och påverkar inte sharp-signaler. AH, Ö/U,
hörnor, MLS, frånvaroeffekt och nya datakällor ligger utanför första experimentet.

## Förregistrerade hypoteser

1. Den fristående xG-/Elo-modellen innehåller en liten mängd information som
   inte redan finns i sharp-priset, men dess stora avvikelser är överkonfidenta.
2. En ridge-krympt residual mot marknaden kan därför förbättra logloss utan att
   skapa stora fristående modell-edgear.
3. Effekten får vara olika per liga, men tunna ligaparametrar måste krympas mot
   en gemensam nordisk effekt i stället för att fittas fritt.
4. Nyttan ska synas i sannolikhetsmått före ROI. Positiv historisk ROI ensam är
   aldrig promotionsgrund.

Hypoteserna och kriterierna nedan fryses innan v2-backtesten körs.

## Datakontrakt

Varje tränings-/prediktionsrad måste bära:

- provider-event-ID/canonical match-ID, liga och avspark;
- exakt `as_of` och horisont: T−24 h, T−3 h eller T−20 min;
- power-devigad Pinnacle 1X2 från samma eller tidigare tillåten capture;
- modellversion och featureversion;
- endast resultat, xG och Elo som var kända vid `as_of`;
- availability/last-seen för marknadspriset;
- featurevärde, saknas-flagga och källtid — aldrig tyst imputation.

Resultat efter avspark, closingpris och framtida xG/Elo får endast användas som
facit, aldrig som input. Frånvaro läggs inte till förrän historiken har mätbar
täckning vid respektive horisont och en förregistrerad spelarvärdering.

## V2.0 — dataset och identitetskontroll

1. Bygg en reproducerbar walk-forward-tabell för de två ligorna.
2. Rapportera coverage per liga, säsong, horisont och feature innan någon modell
   tränas. Saknade värden får inte filtrera bort svåra matcher tyst.
3. Lägg in en identitetsmodell där `delta=0`. Den måste återskapa Pinnacles
   sannolikhet och logloss exakt; annars är datasetet eller devigen fel.
4. Frys ett slutligt outer-testfönster som inte används för featureval,
   regularisering eller stoppbeslut.

Acceptans: inga post-kickoff-rader, ingen match i både träning och test vid samma
walk-forward-steg, och marknadsidentiteten avviker mindre än `1e-10`.

## V2.1 — minsta residualmodell

Första modellen är multinomial ridge-logistik på marknadslogits med högst dessa
förregistrerade residualfunktioner:

- fristående modell minus sharp i logitrymd för 1/X/2;
- xG-viktad anfalls- och försvarsskillnad;
- PIT-Elo-skillnad;
- hemmafördel;
- effektivt historikantal och datans ålder;
- ligaindikator med krympning mot gemensam effekt.

Alla kontinuerliga features standardiseras enbart på respektive träningsfönster.
Saknade Elo/xG får egna indikatorer och neutral imputation beräknad från
träningsfönstret. Ingen trädmodell, automatisk feature search eller interaktion
läggs till i v2.1.

Regulariseringsstyrkan väljs i en inre tidsordnad validering inom varje outer-
träningsfönster. Det yttre testutfallet får aldrig påverka valet.

## V2.2 — offline-dom

Primärt mått är parad skillnad per match:

`delta_logloss = logloss(Pinnacle) - logloss(v2)`

Positivt är bättre för v2. Osäkerheten tas med matchblock-bootstrap, 90 % KI.
Brier och kalibrering per tecken/liga är skyddsmått. ROI och träffprocent
redovisas men styr inte beslutet.

Offline-v2 får gå vidare till skuggläge endast om:

- minst 300 outer-testmatcher totalt och minst 100 per liga finns;
- genomsnittlig `delta_logloss > 0` och undre 90 %-KI-gräns är över 0;
- ingen liga försämras mer än 0,005 logloss;
- Brier försämras inte mer än 0,002 totalt;
- kalibreringsrapporten saknar en ny systematisk 1/X/2-bias över 3 pp;
- resultatet håller när matcher utan full xG/Elo-täckning inkluderas.

Om kriterierna missas stannar v2.1. Vi lägger inte till fler features en efter
en tills samma testfönster råkar bli positivt.

## V2.3 — forward-skugga

Godkänd offline-version får en ny fryst `signal_version` och loggas vid ledgerns
T−24 h/T−3 h/T−20 min. UI får visa:

- sharp-sannolikheten;
- v2:s justering i procentenheter;
- de högst bidragande featuregrupperna;
- amber-status och antal forwardmatcher.

V2 blir standardmodell i UI, fortfarande amber, först efter minst 100 tidsenliga
forwardmatcher, minst 40 per liga, minst åtta veckors span och positiv undre
90 %-KI-gräns för parad `delta_logloss` mot sharp. Actionable/grön signalstatus
kräver dessutom den befintliga prediction-ledgerns candidate→out-of-time-green-
regel för exakt liga × marknad × horisont × version. Ingen notis aktiveras av
modellens sannolikhet ensam.

## Senare features — nya, separata experiment

Efter v2.1-domen kan varje följande grupp få en egen version och samma offline-
plus-forward-process:

1. vilodagar, cupmatcher och resor från WP9c;
2. viktad frånvaro när WP8-historiken är mogen;
3. bekräftade elvor nära T−20 min;
4. väder/underlag endast om coverage och effekt motiverar kostnaden;
5. MLS som separat kalibreringsprojekt.

Shot-xG/xGOT från olika providers blandas aldrig i samma feature. En ny feature
måste först få coverage-matris, PIT-definition, saknas-policy och test.

## Leveransordning

1. **V2-A dataset/audit ✅ 2026-07-17:** featuretabell, läckagetester,
   coverage-rapport, identitetsbaslinje och fryst outer-manifest. Första
   produktionsaudit i `v2-a-audit-2026-07-17.md`; live-underlaget växer nu
   automatiskt och retrospektiv rekonstruktion är spärrad från promotion.
2. **V2-B modell/backtest:** ridge-residual, nested walk-forward och fryst dom.
3. **V2-C skuggläge:** versionerad ledgercapture och förklarande amber-UI.
4. **V2-D forwardbeslut:** automatisk rapport mot de förregistrerade kriterierna.

Varje paket får egna tester och commit. Nuvarande modell och sharp-fair behålls
som kontrollgrupper hela vägen; misslyckad v2 innebär därför ingen försämring av
dagens produkt.
