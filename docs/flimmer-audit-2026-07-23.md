# Audit: kan 45-minutersvakten ge värde-pill-flimmer?

## Slutsats

Hypotesen är **strukturellt bekräftad** för AH/ÖU/hörnor på matcher utanför
3-timmarsfönstret. Det fulla varvet går inte alltid var 30:e minut i praktiken,
eftersom ett smart-pass kan fortsätta med tätvarv innan nästa launchd-start.
Det ger korta perioder där ett i övrigt oförändrat djuppris passerar
45-minutersgränsen och inte längre är spelbart i UI:t.

Vi ändrar **inte** färskhetsgränsen. Ett gammalt pris ska varken bli
värdesignal, notis, modell-edge eller closing-facit bara för att minska visuellt
flimmer.

## Mätning

Källa: tidsstämplarna för fulla `cli.py smart`-varv i
`backend/data/snapshot.log`, sjudygnsfönstret
2026-07-16 22:54:08–2026-07-23 22:24:50.

| Mått | Utfall |
|---|---:|
| Fulla varv | 237 |
| Intervall | 236 |
| Medianintervall | 51,0 min |
| 90:e percentil | 54,9 min |
| Längsta intervall | 63,0 min |
| Intervall över 45 min | 120/236 (50,8 %) |
| Samlad tid över 45-minutersgränsen | 1 030,8 min |
| Genomsnitt per dygn | 147,3 min (2 h 27 min) |

Den sista siffran är en **riskyta**, inte uppmätta av/på-växlingar. Databasen
bevarar prisändringar och senaste bekräftelse, men inte varje oförändrad
närvarobekräftelse historiskt; `oddset_source_health` är också senaste läget,
inte en tidsserie. Därför går det inte hederligt att påstå hur många faktiska
värdepills som blinkade i detta historiska fönster.

Matcher inom tre timmar får snabbvarv (inklusive SvS-deep för berörda matcher)
och har mindre risk. Problemet gäller främst tidigare visning av framtida
AH/ÖU/hörn-signaler.

## Rekommendation

1. Behåll `PRICE_MAX_AGE_MIN = 45` för all spelbar logik och allt facit.
2. Ändra inte pollfrekvens eller Pinnacle-trafik enbart på denna mätning.
3. Om fladdret stör användningen: visa separat en nedtonad
   **”senast sedd signal — väntar på färsk kontroll”** i högst 75 minuter.
   Den får aldrig ge Kelly-insats, loggas som flagga, notifiera eller räknas i
   ledger/facit.
4. Vill vi mäta faktiska övergångar först, lägg till en liten append-only
   UI-presence-audit per fullvarv. Det är ett separat DB-paket med backup,
   migration och retention — inte motiverat ännu.
