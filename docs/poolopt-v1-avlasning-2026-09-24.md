# Pooloptimerare v1 — formell avläsning vid 40 parade omgångar

Datum: 2026-09-24. Grund: Samans beslut 5aA samma dag. Protokoll:
`docs/poolopt-v1-forward-2026-09-02.md`.

## Avläsningsregeln (låst före beräkning)

Protokollet anger grinden, alltså minst 40 parade omgångar per arm mot
`dr1-b256-medel` och träff-Δ eller ROI-Δ med undre KI90 > 0 på framåtdata.
Det anger också avslutet efter 120 framåtomgångar. Det anger däremot inte när
grinden ska läsas av, och varje extra avläsning ökar risken för en falsk
träff. Därför gäller följande:

- **Två avläsningar totalt:** denna vid 40 och den sista vid 120
  framåtomgångar. Inga avläsningar däremellan. `cli.py gater` och UI:t visar
  bara räknare fram till dess.
- **Population per cell** (arm × horisont 180 och 20 min, enhet
  Topptipsfamiljen): de 40 första parade omgångarna i kronologisk ordning
  efter championens `frozen_at`, därefter produkt och omgångsnummer. "Parad"
  betyder exakt samma sak som i `research_gate`: båda raderna rättade,
  frysta i tid (`timely`) och med komplett utdelning.
- **Träff** per omgång: systemet har en rad med alla matcher rätt
  (`correct_max` lika med antalet matcher). Träff-Δ = arm − champion.
- **ROI** per omgång: `payout_kr / cost_kr − 1` ur PH3:s kontrafaktiska
  settlement. ROI-Δ = arm − champion, winsoriserad till ±2,0
  (`WINSOR_ROI_DIFF` i `scripts/optimera_topptips256.py`).
- **KI90:** percentilbootstrap över omgångar med 2 000 dragningar, samma
  funktion som optimerarens slutaudit (`_bootstrap_ci`, seed-bas 20260830),
  med seed-strängen `forward40|<horisont>|<nyckel>|hit` respektive `…|roi`.
- **Grind passerad** i en cell när undre KI90 > 0 för träff-Δ eller ROI-Δ.
  Ingen multipeljustering mellan de sex cellerna. Enligt protokollet leder en
  passerad cell bara till en ny förregistrerad PH3-utmanare med egen nyckel,
  och där gäller BH-FDR.

Transparens: statusauditen 2026-09-24 såg en preliminär egen bootstrap på
alla 47 parade omgångar, där ingen arm hade undre KI90 > 0. Populationen här
bestäms av regeln ovan och inte av det resultatet.

## Resultat

Körd 2026-09-24 med `backend/scripts/poolopt_avlasning.py` mot
produktionsdatabasen i read-only-läge. Underlaget per omgång ligger i
`docs/poolopt-v1-avlasning-2026-09-24.json`. Alla sex celler hade 47 parade
omgångar, exakt samma antal som `research_gate` räknar. De 40 första frystes
mellan 2026-09-03 och 2026-09-19.

| arm | horisont | träffar arm/champion | träff-Δ per omgång (KI90) | ROI-Δ winsor (KI90) | grind |
|---|---|---|---|---|---|
| träff | 180 min | 15/13 | +0,050 [-0,025; +0,125] | +0,076 [-0,074; +0,226] | ej passerad |
| träff | 20 min | 12/12 | +0,000 [-0,050; +0,050] | -0,024 [-0,124; +0,052] | ej passerad |
| balans | 180 min | 15/13 | +0,050 [-0,025; +0,125] | +0,076 [-0,050; +0,226] | ej passerad |
| balans | 20 min | 12/12 | +0,000 [-0,050; +0,050] | -0,024 [-0,124; +0,052] | ej passerad |
| X-kvot | 180 min | 14/13 | +0,025 [-0,050; +0,100] | +0,050 [-0,100; +0,200] | ej passerad |
| X-kvot | 20 min | 11/12 | -0,025 [-0,100; +0,050] | -0,074 [-0,200; +0,028] | ej passerad |

**Utfall: grinden är inte passerad i någon cell.** Ingen ny PH3-utmanare
föreslås. Familjen samlar vidare utan avläsningar tills den nått 120
framåtomgångar. Då görs den sista avläsningen med samma metod på alla parade
omgångar bland de 120, och passerar ingen cell pensioneras familjen enligt
protokollet.

Iakttagelser utan beslutsvärde: träff- och balans-armen ger identiska
träffar, eftersom deras rader nästan helt överlappar. Vid 180 minuter ligger
punktskattningen på två träffar fler än championen på 40 omgångar, men
intervallet rymmer noll. X-kvot-armen är svagast vid 20 minuter.

Gamla Pinnacle-priser (statusauditen 2026-09-24) påverkade arm och champion
lika i varje par, eftersom båda frystes i samma varv på samma underlag.
Alla 40 omgångar frystes före färskhetsregeln och matchregeln v5.
