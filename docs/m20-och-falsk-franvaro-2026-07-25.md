# m20-horisonten — och den falska frånvaron bakom den (2026-07-25, Opus 5)

**Beställningen var att avgöra m20-horisonten för sharp medvetet.** Mätningen gav
ett annat svar än väntat: m20 är inte strukturellt omöjlig. Vi blockerade oss
själva.

## Vad som stod i överlämningen

> m20-horisonten för sharp kan strukturellt inte nå 10-minuterstoleransen:
> uppmätt ger Pinnacle en distinkt capture var 30:e minut i median (CDN-cache
> 905 s) […] frågan om sharp överhuvudtaget kan bära m20 bör avgöras medvetet.

Slutsatsen låg nära att skriva bort `sharp × m20` som scope. Det hade varit fel.

## Vad mätningen visade

`pool_pit_match_features` för `pit-v3`, per produkt och horisont — kolumnen
"i tid" är captures inom förregistrerad tolerans:

| produkt | horisont | n | i tid | har sharp-pris | behöriga |
|---|---|--:|--:|--:|--:|
| stryktipset | h3 | 13 | 13 | 12 | **12** |
| stryktipset | m20 | 13 | 13 | 0 | **0** |
| topptipset | m20 | 8 | 8 | 8 | **8** |
| topptipsetstryk | h3 | 8 | 8 | 0 | **0** |
| europatipset | h24 | 13 | 13 | 0 | **0** |

Captures var alltså **i tid överallt** — CDN-cachen var inte problemet. Det som
fattades var priset. Och Topptipset lyckades på m20 medan Stryktipset misslyckades
på samma horisont, vilket ingen strukturell CDN-förklaring klarar.

Statusserien för Stryktipset 4963 (spelstopp 13:59 UTC) avslöjade mönstret:

```
12:29   matched 12 / not_listed 1     ← riktig läsning
12:37   not_listed 13
12:42   not_listed 13
…       (var 5:e minut, 17 ticks i rad)
13:57   not_listed 13
```

Ingen gradvis avlistning, ingen livetransition — en binär växling. Och det
avgörande före/efter-talet:

| dag | helt tomma sharp-ticks | ticks med träff | andel tomma |
|---|--:|--:|--:|
| 2026-07-24 | 0 | 591 | **0 %** |
| 2026-07-25 | 228 | 207 | **52,4 %** |

## Grundorsaken

Dubbeltrafikspärren som infördes 2026-07-25 (`PINNACLE_MIN_INTERVAL_S = 600`)
returnerar `{"hits": {}, "status": {}, "skipped": "…"}` — **utan fel**.
`record_sharp_capture` skyddade bara mot `pinnacle_error`, och skrev därför:

```python
status.get(match.event_number, "not_listed")   # tom status ⇒ not_listed
```

Alltså: *vi frågade inte* bokfördes som *Pinnacle listar inte matchen*, med färsk
tidsstämpel, som en "värdefull lyckad frånvaroobservation". Eftersom Oddset-varvets
snabbpoll rör Pinnacle var 4:e minut hölls låset varmt nästan konstant, och poolen
förlorade sin sharp-observation i drygt hälften av alla ticks. Att Stryktipsets
m20-fönster hamnade på en låst tick medan Topptipsets hamnade på en fri var ren
slump.

Detta är samma familj som projektets egen regel *"källfel får aldrig markera ett
pris unavailable"* och som de tre observationstidsbuggarna: **ett tillstånd vi
aldrig observerade skrevs som ett observerat tillstånd.**

## Åtgärdat

1. `record_sharp_capture` bokför inte längre överhoppade hämtningar
   (`skipped` behandlas som `pinnacle_error`). En källa vi inte frågade är
   ingen observation.
2. `sharp_service.collect_pinnacle(force=…)` — spärren får förbigås **bara** i
   ett öppet horisontfönster (`pool_dataset.horizon_window_open`, horisont ±
   förregistrerad tolerans). Max ett anrop per horisont och omgång; alla andra
   ticks använder cachen precis som spärren avsåg. Toleranserna är oförändrade —
   de läses, aldrig skrivs.
3. `/api/external-odds` svarar `ej ompollad` i stället för `not_listed` när
   spärren slog till, och UI:t visar "cachat pris gäller". Panelen hävdade
   annars att Pinnacle inte listar matcher som Pinnacle listade.
4. Regressionstester: `tests/test_pool_pit.py::SharpCaptureTests` (fyra fall —
   överhoppad, källfel, verklig frånvaro, horisontfönstrets gränser).

## Svaret på m20-frågan

**Sharp × m20 skrivs INTE bort som scope.** Beslutet vilar på ett mätvärde som
var en artefakt av vår egen spärr. Rätt ordning är: fixa den falska frånvaron
(gjort), låt några omgångar passera med tvingade horisontanrop, och mät sedan om
sharp faktiskt når 10-minuterstoleransen. Topptipsets 8/8 på m20 antyder att den
gör det.

Kvar att avgöra av Saman: **de redan skrivna falska raderna.**
2 240 rader 2026-07-25 (och 474 den 24:e) bär statusen `not_listed` utan att någon
frågade. `pit-v3`-features är beräknade på dem, och `sharp_eligible = 0` i den
datan betyder "vi frågade inte", inte "sharp fanns inte". Två vägar, båda
förenliga med projektets metod:

- **A) Rensa + räkna om `pit-v3`.** Skript + backup + rapport, samma mönster som
  ankarrensningen. Billigt just nu: forward-utvärderingen står på `n = 0`
  (`docs/ph4-forward-status.json`), så ingenting är ännu scorat. Men det ändrar
  data i ett fryst experiment.
- **B) Bumpa till `pit-v4` med nytt manifest.** Exakt det mönster som användes
  v2→v3 i går ("nytt experiment i stället för att smyga in ändrad
  datasemantik"). Kostar ~1 dygns shadowdata och lämnar `pit-v3` orört som
  historik.

Rekommendation: **B**. Datasemantiken för `sharp_eligible` ändras faktiskt av
fixen, och projektet har redan bestämt att sådant startar ett nytt experiment
snarare än att skriva om ett gammalt. Kostnaden är en dag.
