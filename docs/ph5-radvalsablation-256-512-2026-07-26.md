# PH5 v2 vid 256/512 rader — 13-matchsdomen

Datum: 2026-07-26 (Fable 5). Den förregistrerade uppföljningen av PH5 v2
(`docs/ph5-radvalsablation-2026-07-25.md`): är 13-matchs-underkännandet
budgetberoende eller strukturellt? Samma armar, samma parade winsoriserade
estimand (±200 pp), samma seed; per-omgångs-ROI i
`ph5-radvalsablation-{256,512}rader-2026-07-26.json`.

## Resultat (värderader mot slump, parad diff per omgång)

| budget | Stryktipset (n=223) | Europatipset (n=505) |
|---|---|---|
| 100 rader (v2-körningen 07-25) | −8,2 pp [−15,4..−1,7] | (del av samma underkännande) |
| 256 rader | −5,0 pp [−12,1..+1,5] | +1,0 pp [−3,4..+5,5] |
| 512 rader | −2,3 pp [−10,9..+5,8] | +2,4 pp [−2,2..+7,4] |

Toppnivåträffar vid 512 rader: värderader **2** mot favoritradens **7** och
folkradens **7** (Stryk); **6** mot **10/10** (Europa). Mot favorit-/folkrad
är alla parade differenser ~0 med breda KI.

## Dom

**Båda delarna av den förregistrerade frågan besvaras:**

1. **Underskottet är täthetsberoende** — det krymper monotont med budgeten
   (−8,2 → −5,0 → −2,3 pp mot slump för Stryktipset) precis som
   gleshetshypotesen förutsade (512 rader = 0,03 % av 1,6 M utfall mot ~8 %
   på Topptipsets 6 561).
2. **Men ingen spelbar budget vänder det till en fördel.** Även vid 512
   kronor är värderad-metoden i bästa fall likvärdig med att spela folk-
   eller favoritraden, och toppträffarna hamnar systematiskt hos de naiva
   raderna. Kontrasten mot 8-matchsprodukterna (+7,7 till +15,5 pp vid
   100 rader, alla undre KI-gränser > 0) är total.

**Konsekvens (enligt förregistreringen):** ärlig text i byggaren för
Stryktipset/Europatipset — radvalsmetoden har ingen påvisad fördel där vid
budgetar ≤ 512 rader; på Topptipset-spelen är fördelen bevisad. Ingen
logikändring: byggaren fungerar, men den ska inte LOVA något på 13-matchsspel.
En eventuell metod specifikt för gles täckning (t.ex. maximal
Hamming-spridning i stället för EV-ranking) är en egen förregistrerad fråga.
