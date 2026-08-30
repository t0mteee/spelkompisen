# Lokal systemoptimerare v1 — förregistrering

Datum: 2026-08-30

Status: fryst specifikation innan den första pilotsökningen körs. Detta är ett
offlineforskningsverktyg. Det ändrar inte standardbyggaren, lämnar inga spel
och skriver aldrig i produktionsdatabasen.

## Fråga och första scope

Kan en deterministisk sökning över många sätt att välja **exakta rader** hitta
Topptipssystem som är robustare än dagens Standard vid 256 kr, utan att köpa
träffchans genom orimligt folkliga rader eller i efterhand anpassa sig till en
enskild storvinst?

Första versionen gäller bara familjen `topptipset`, `topptipsetstryk` och
`topptipsetextra`, exakt åtta matcher och 256 unika rader. Sannolikhetsmodellen
hålls fast. Det som söks är radportföljen och den relativa
medvinnarkorrektionen efter antal X. Stryktipset, Europatipset, andra budgetar
och dubbelkuponger kräver nya versioner efter att v1:s motor verifierats.

## Historikens begränsning

Kohorten är `final_only`: officiellt facit, omsättning, utdelning,
öppningsodds och slutstreck ur settlementlagret. Alla kandidater ser exakt
samma data, så deras **relativa radval** kan jämföras. Slutstrecket var däremot
inte känt vid ett verkligt h3-/m20-beslut. Absolut ROI är därför inte en
spelprognos och får aldrig blandas med `observed_pit` eller användas för direkt
promotion.

Perioden börjar 2024-01-01. Topptipset 4289 utesluts: just den kända
fyrkrysskupongen motiverade X-frågan och får inte bli ett träningsmål. Alla
kvalificerade omgångar sorteras globalt efter spelstopp och delas
kronologiskt 60/20/20 i utveckling, validering och historisk slutaudit. Ingen
slumpmässig train/test-split används.

Den historiska slutauditen är låst relativt den nya sökningen men inte ett
fullständigt nytt vetenskapligt holdout: projektets tidigare analyser har
redan påverkat vilka parameterfamiljer vi frågar om. Endast ett senare,
versionsmärkt point-in-time-forwardtest kan godkänna en vinnare.

## Champion och kandidater

Champion är produktionsbyggarens Standard:

- `value_weight=0.50`;
- produktens befintliga toppnivå-κ;
- ingen X-gruppjustering;
- ingen X-kvot;
- inget exponeringstak utöver 256 unika rader.

Motorn måste i regressionstest välja exakt samma 256 rader som
`build_ev_system` på samma syntetiska analys innan någon sökning får köras.

Övriga konfigurationer skapas deterministiskt med seed `20260830`. Sökrymden:

- värdevikt 0,00–1,00;
- global κ-skala 0,75–1,40;
- linjär X-gruppjustering −0,25–+0,25;
- kvadratisk X-gruppjustering −0,08–+0,12;
- minsta X-kvot 0/25/50/75/100 procent av marknadens implicerade
  X-antalsspridning;
- maximalt 65/70/80/90/100 procent av raderna på samma tecken i en match.

X- och κ-parametrarna påverkar bara kandidatens urval. Alla valda portföljer
utvärderas därefter med **samma frysta referensmodell** (championens κ). En
kandidat kan alltså inte vinna genom att värdera sina egna rader mer
optimistiskt.

## Successiv gallring

En full sökning får skapa upp till 10 000 unika konfigurationer men kör dem
inte naivt genom hela historiken:

1. jämnt tidsfördelat grovurval ur utvecklingsdelen;
2. bredare utvecklingsurval för cirka 20 procent av kandidaterna;
3. hela utvecklingsdelen för den kvarvarande femtedelen;
4. hela valideringsdelen för högst 40 kandidater;
5. historisk slutaudit för högst åtta kandidater, utan ny trimning.

Champion följer med i varje steg. Gallringen behåller en deterministisk union
av ledare för balanserat mått, faktisk träff, marknadsberäknad portföljträff,
referens-EV och parad winsoriserad ROI. Detta hindrar en enda godtycklig
skalär från att kasta bort hela träff- eller utdelningsfronten.

Piloten använder högst 500 konfigurationer och ett litet, jämnt utspritt
historikurval. Pilotresultat är en teknisk kontroll av identitet, kostnad,
facit, återupptagning och rimlig körtid — aldrig en modelldom.

## Mått och vakter

Per omgång och konfiguration sparas/ackumuleras:

- exakt åttarättsträff;
- kontrafaktisk ROI där den publicerade potten är identifierbar;
- parad ROI-skillnad mot champion, winsoriserad till ±200 procentenheter;
- summan av de valda radernas marknadsberäknade träffsannolikhet;
- referensmodellens förväntade utdelning;
- genomsnittligt antal X, andel rader med minst fyra X och största
  teckenexponering i en match;
- ogiltiga/ej kompletta 256-radersbyggen.

En kandidat får inte gallras vidare som balanserad om dess beräknade
träffmassa är under 95 procent eller dess referens-EV under 90 procent av
championens på samma omgångar. Rå medel-ROI är diagnostik. Urvalsgrunden är
parad och den historiska slutauditen rapporteras utan parameterändring.

Tio tusen sökta modeller innebär data-snooping. Ett vanligt bootstrap-KI för
den historiskt bästa modellen är därför inte ett giltigt promotionsbevis.
V1 får bara nominera versionsmärkta forwardkandidater. Innan en sådan kandidat
kan ersätta Standard krävs projektets vanliga senare point-in-time-grind och
en separat multipeltestskorrigerad jämförelse.

## Drift och reproducerbarhet

- Indata är en fixerad SQLite-snapshot som öppnas `mode=ro`.
- CLI:n skriver bara en lokal JSON-checkpoint/resultatfil under en ignorerad
  optimizer-katalog eller till explicit angiven sökväg.
- Spec-, dataset-, konfigurations- och kodfingeravtryck sparas. `--resume`
  vägrar fortsätta om något av dem ändrats.
- Delresultat skrivs atomiskt och körningen kan återupptas efter avbrott.
- Själva Python-processen kör lokalt och använder inga AI-tokens.
- Ingen kandidat läggs in i UI, ledger eller produktion under pilotsteget.

## Nästa beslut efter pilot

Om regressionstesterna och pilotens kontrolltal håller körs den fulla
Topptipset-256-sökningen på en färsk, skrivskyddad server-snapshot. Därefter
förregistreras högst tre forwardarmar: träfffokus, ROI/referensvärde och
balanserad kandidat. Underkänd eller överanpassad kandidat trimmas aldrig
under samma versionsnamn.
