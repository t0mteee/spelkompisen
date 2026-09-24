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

Fylls i av `backend/scripts/poolopt_avlasning.py` efter att regeln ovan
committats.
