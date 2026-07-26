# startOdds-semantiken verifierad — fältet låses upp med förbehåll

Datum: 2026-07-26 (Fable 5). Godkänd insats (backlogens wildcard i4).
Fältet har varit SPÄRRAT för analys sedan PH0 (2026-07-24) i väntan på detta.

## Metod

Egna observationer är facit: `snapshots`-tabellen bär SvS `startOdds`-fält
per hämtning för 98 omgångar (2 664 selektioner) parallellt med aktuella
odds. Fyra tester mot den serien + result-API:ts version.

## Resultat

1. **Inte stängning:** startOdds matchar vår FÖRSTA odds-observation exakt i
   81 % (MAE 0,058) mot SISTA i 17,8 % (MAE 0,344).
2. **Inte helt immutabelt:** 23 % av selektionerna får fältet reviderat någon
   gång i vår serie.
3. **Revisionerna är tidiga engångsjusteringar, inte tracking:** bland de
   instabila slutar bara 19 % lika med aktuellt odds, och sista ändringen
   ligger i median 4 % in i observationsfönstret (p90: 12 %) — därefter
   fryser fältet. Vi börjar observera i snitt 3,0 dagar före spelstopp.
4. **Result-API:t bär slutversionen:** 730/823 (89 %) identiska med
   draws-API:ts samtida värde; resten är just de tidigt reviderade, där
   result-API:t har den slutliga (frysta) versionen.

## Verdikt

`startOdds` = **SvS öppningsodds, med möjliga revisioner strax efter
listning, därefter fryst**. Result-API:ts version är kanonisk.

**UPPLÅST för analys** i `final_only`-kohorter med två hårda förbehåll:

- **Ingen tidsstämpel** ⇒ får ALDRIG användas som PIT-observation vid känd
  tid (kan inte gå in i pit-vN-features som "observerat vid T"). Den är en
  omgångs-kovariat: "SvS öppningsprissättning".
- Öppnings→facit- eller öppnings→slutstreck-studier ska nämna
  23 %-revisionsbrasklappen och att revisioner sker inom ~första dygnen.

Detta öppnar 8 278 historiska omgångar (till 2013) med öppningspris +
slutstreck + facit + utdelning — t.ex. öppningsodds-kalibrering mot facit,
folkets drift relativt öppningen, och öppningsbaserade features i
final_only-ablationer (PH5-familjen). Pinnacle-opening förblir avvisad ur
q-facitet (separat beslut 2026-07-16, orört).
