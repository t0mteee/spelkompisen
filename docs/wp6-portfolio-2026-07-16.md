# WP6 — Monte Carlo-portfölj för poolspel

Klar 2026-07-16. WP6 ersätter inte radbyggarens snabba rankning utan ger det
färdiga systemet en ärligare huvudvärdering där matchutfall, medvinnare och de
egna radernas inbördes konkurrens behandlas tillsammans.

## Vad som räknas

1. Varje matchs utfall dras från kupongens fair-sannolikheter.
2. För det dragna utfallet räknas den exakta Poisson-binomialfördelningen för
   hur många rätt en slumpmässig folkrad får utifrån slutstrecken.
3. Antalet externa vinnare på nivå `c` modelleras som
   `W_c ~ Poisson(fältrader × P_folk(c rätt | utfallet) × κ)`.
4. Om `k` av våra egna rader har samma vinstnivå får portföljen villkorat
   `pott × k × E[1/(W_c+k)]`. Förväntningen integreras numeriskt i stället för
   att ersättas med den gamla `1/(E[W]+1)`-approximationen.
5. Systemets totala utdelning sparas per scenario och ger medel, EV/ROI,
   standardavvikelse, pluschans, nollrisk och percentiler.

Topptipsets åtta matcher har bara `3^8 = 6 561` möjliga utfall och räknas därför
fullständigt med sannolikhetsvikter. Kuponger med 13 matcher använder ett
deterministiskt, reproducerbart urval om 10 000 utfall. Matchradsmatchningen
använder bitset, så 2 048 rader × 10 000 utfall tog cirka 0,38 sekunder lokalt.

## Produktbeteende

- Alla genererade system upp till 5 000 konkreta rader får `portfolio_mc` i
  `/api/system`; matematiska system materialiseras före simuleringen.
- Värderingen använder förväntad slutomsättning när prognosen finns. Vid
  källfel faller den tillbaka till liveomsättning och UI märker skillnaden.
- Jackpot/rullpott läggs till toppnivån och samma belopp används i radval,
  simulering och UI.
- `κ` ligger fortsatt på 1,00. Den historiska auditens lägre skattning får inte
  höja visad EV innan ett oberoende tidsfönster har bekräftat den.
- Den gamla radvisa formeln visas fortfarande i detaljtabellen och i svaret som
  jämförelse. Portföljkortet är huvudvärderingen för det genererade systemet.
- Radvalet för EV-/färgsystem är oförändrat. WP6 utvärderar den färdiga
  portföljen; det väljer inte om kandidatrader efter simuleringsutfallet.

UI-kortet visar förväntad utdelning, netto-EV/ROI, chans att gå plus, risk för
noll, median och 90:e percentil. Det redovisar även skillnaden mot snabbformeln,
egna raders konkurrens samt Monte Carlo-felet för 13-matchskuponger.

## Verifiering

- 83 backendtester gröna.
- Nytt handräknat ettmatchsfall verifierar hela kedjan.
- `E[1/(W+k)]` verifieras mot direkt Poissonsummering och sluten form för `k=1`.
- Samma seed ger identiskt 13-matchsresultat.
- Ett lägre vinstnivåfall verifierar att egna rader faktiskt delar potten.
- Stor-fältstestet håller toppnivåns Poisson-korrektion inom 5 % från den gamla
  formeln; aktuell Topptipset-smoke gav cirka 0,3 % skillnad.
- Frontendens produktionsbygge är grönt.
- Riktigt `/api/system`-anrop verifierat på öppen omgång 4215.
- UI verifierat i desktop-DOM och vid 390 px: två KPI-kolumner och ingen
  horisontell overflow.

## Kvarvarande osäkerhet

Detta är exakt **inom den valda modellen**, inte ett löfte om verklig utdelning.
Matchutfall antas oberoende, folkrader approximeras av slutstrecken och externa
vinnare antas Poissonfördelade. Korrelation i hur människor bygger system fångas
bara indirekt av `κ`, som ännu inte appliceras. Fair-sannolikheter, framtida
streck och slutomsättning kan också ändras före spelstopp. Därför visas
percentiler som riskintervall och aldrig som garanti.
