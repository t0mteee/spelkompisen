# Två ankare — förregistrerad plan (2026-07-25, Opus 5)

**Frågan:** är sharp-tierns `+2,65 % [1,19..4,11]` close-EV marknadens felprissättning
eller vår devig/vårt ankarval? Devigmetodens val rör ~3 pp medan flaggtröskeln är
2 pp, och den uppmätta oenigheten Pinnacle vs Smarkets är median 1,12 pp med **11 %
av selektionerna över hela tröskeln**. Den siffran är hela projektets fundament, så
den måste tåla ett andra ankare.

Denna plan är skriven INNAN data finns, och den beslutar ingenting av sig själv.

## Varför mätning i skugga och inte en gate direkt

En gate ändrar urvalet ⇒ `signal_version` måste bumpas ⇒ de 147 stängda flaggorna
hamnar i en annan facitgrupp och klockan nollställs. Att kasta bort projektets enda
positiva evidens för att testa en hypotes är fel ordning. Skuggmätningen kostar
ingenting, ändrar ingen flagga och gör frågan avgörbar med data i stället för
argument.

**Runtime är oförändrat.** `SHARP_PARAMS` orörd, `signal_version` orörd, samma
flaggor, samma notiser, samma Kelly. Regressionstesterna i
`tests/test_oddset_value.py::AnchorSourceTests` låser fast det.

## Vad som mäts

Nya kolumner i `oddset_value_log` (additiva, nullbara):

| kolumn | betydelse |
|---|---|
| `anchor2_source` | vilket andra ankare (i dag `smarkets`) |
| `anchor2_fair` | ankare 2:s devigade fair för selektionen **vid first** |
| `anchor2_edge` | `anchor2_fair × first_odds − 1` — samma bokpris, andra ankaret |
| `anchor2_closing_fair` | ankare 2:s fair vid stängning (samma färskhetskrav) |
| `anchor2_note` | varför mätning saknas (aldrig tyst tolkat som enighet) |

Rapport: `oddset_value.anchor2_report()`, exponerad som `anchor2` i
`/api/oddset/clv`. Nyckeltal: `median_disagree_pp`,
`share_disagree_over_threshold`, `avg_close_ev_survives_both` mot
`avg_close_ev_pinnacle_only`.

**Skrivs bara vid first**, aldrig i efterhand — samma regel som `first_fair`. De 737
flaggor som redan finns får därför NULL och räknas som ej mätta. Ingen bakfyllning
är möjlig eller tillåten: Smarkets-serien börjar 2026-07-24.

Första mätta flaggan (2026-07-25, New England Revolution, 1X2 tvåa) visar caset
direkt: Pinnacle-edge **+2,6 %** (över tröskeln ⇒ flaggad), Smarkets-edge **−0,4 %**
(under tröskeln ⇒ hade inte flaggats), oenighet 0,82 pp. Flaggan existerar alltså
för att vi valde Pinnacle.

## Kohort och förväntad tid till beslut

- **Kohortstart:** flaggor med `first_at ≥ 2026-07-25`.
- **Primärgrupp:** `sharp × 1x2 × {allsvenskan, superettan, eliteserien,
  obosligaen, mls}` — samma förregistrerade primärgrupper som grönt v3.
  Träningsmatcher och forskningsligor är utforskande och kräver BH-FDR 10 %.
- **Takt:** 25–70 nya sharp-flaggor per dygn, varav 14–32 är 1X2 (uppmätt
  2026-07-18→25). n = 50 mätta OCH stängda 1X2-flaggor bör nås inom ~1 vecka.

## Beslutsregel (förregistrerad)

Utvärdera på **veckokadens** (samma `EVAL_INTERVAL_H` som grönt-status — utvärdering
varje varv är sekventiell testning och lyser förr eller senare grönt på brus).
Estimand: winsoriserad close-EV ±20 %, kluster-bootstrap per match, 90 % KI —
identiskt med `_tier_stats`, annars jämförs olika storheter.

Vid n ≥ 50 mätta och stängda flaggor i primärgruppen:

1. **Promotera gaten** (kräv att edgen överlever mot BÅDA ankarna) om
   `survives_both` har undre KI-gräns > 0 **och** punktskattningen överstiger
   `pinnacle_only` med ≥ 1,0 pp. Då är ankaroenighet en äkta filtreringssignal.
2. **Behåll ett ankare** om skillnaden är mindre än 1,0 pp eller går åt andra
   hållet. Det är ett *positivt* resultat: devigtvetydigheten förklarar inte
   edgen, och vi slipper halvera flaggvolymen i onödan.
3. **Eskalera** om BÅDA grupperna ligger ≤ 0. Då replikerar inte +2,65 % i den nya
   kohorten och frågan är inte längre vilket ankare som är bäst, utan om signalen
   finns. Fortsätt inte flagga som om inget hänt.

Promotion i fall 1 innebär en medveten `signal_version`-bump med egen rad i
`docs/db-atgarder.md`; den gamla gruppen förblir läsbar och får aldrig blandas in.

## Vad detta INTE svarar på

Smarkets är en börs med overround ≈ 1,00, så power-devigen är nästan identitet
där. Mätningen testar därför **ankaroenighet** — inte devigmetodens eget bidrag.
Den frågan är en separat, helt offline-körbar ablation: räkna om samma flaggor
under power / proportionell / Shin på *Pinnacles* priser och räkna hur många som
överlever varje metod. Rekommenderad uppföljning; kräver ingen ny insamling.

Smarkets täcker bara 1X2 i dag (180 matcher/dygn mot Pinnacles 271). AH/Ö/U/hörnor
får `anchor2_note` = "smarkets saknar …" och kan inte ingå — deras devigfråga är
öppen tills ett ankare med de marknaderna finns.
