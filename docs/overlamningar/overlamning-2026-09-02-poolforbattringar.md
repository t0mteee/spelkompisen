# Överlämning 2026-09-02 (kväll) — poolförbättringar: fyra spår på en dag

Samans fråga: "Vart står vi nu? … Att simulera olika modeller för att hitta en
bättre poolmodell framåt var en idé, vi har ju historiska rader som vi kan
backtracka mot." Beslut: "Ja kör samtliga" på fyra förslag. Allt nedan är
levererat, testat och committat; inget av det ändrar ett enda kupongförslag i
appen — allt nytt är mätning bakom förregistrerade grindar.

## 0. Före: chansmotorn (cbc8749)

`0 %` chans utan avgjord match var ett samplingsartefakt: Monte Carlo med
20 000 drag såg aldrig 13 rätt. Nu räknas chansen EXAKT som en union av
Hamming-klot (`_ball_union_probabilities`), verifierat mot full uppräkning på
85 slumpade system; `_round_chance` bevarar ≥ 3 värdesiffror så 3·10⁻⁷ aldrig
blir noll. Tiden 9,8 → 5,0 s i process; resten är en synkron CPU-endpoint.

## 1. Pooloptimerare v1 — fullsökning och forwardtest

- Snapshot `data/optimizer/snapshot-2026-09-02.db` (onlinebackup, 517 MB,
  sha256 `d821f3b1…`), pilot rent, fullsökning 10 000 konfigurationer på 2 006
  Topptipsomgångar, 38 min, 4 workers.
- Slutaudit (402 omgångar som aldrig användes för urval): **ingen arm slog
  Standard på ROI** (+8,4 %). Träff-armen +3 träffar, KI90 [0; +0,017].
  Gemensamt för de tre bästa: värdevikt ≈ 0,3 (mot 0,5) och κ-skala > 1.
- Tre armar nominerade och förregistrerade som research-familj **`poolopt`**
  (`POOLOPT_FORWARD_CONFIGS`): träff / balans / X-kvot, 256 rader, Topptipset
  4309 / Stryk 979 / Extra 1864 →. Radvalskärnan flyttad till
  **`app/pool_optimizer.py`** utan numerisk ändring (regressionstest: champion-
  konfigurationen = `build_ev_system` rad för rad). Skriptet importerar därifrån.
- Visas i Historik (familj 🔬), `/api/pool/poolopt`, `cli.py gater`
  (`poolopt-v1`), poolhälsan larmar om armarna saknas.
- Dokument: `docs/poolopt-v1-forward-2026-09-02.md`.

## 2. Sannolikhetsbasen i EV-byggaren

- Upptäckt: `_rank_ev_rows` rankar på `fair_prob` (SvS-odds först) medan
  kandidatuniversum, budgetstorlek och dubbelkupong tar Pinnacle först.
- `builder.PROB_BASES`, `prob_base="svs"` byte-identisk standard;
  `"sharp"` = Pinnacle först. Ny PH3-utmanare **`dr1-b256-medel-sharp`** i
  Topptipset-familjen (`benchmarks_for` ger nu 10 nycklar för 8-matchsspelen).
- Retro på pit-v4 (`scripts/ph3_sannolikhetsbas_retro.py`, snapshoten):
  h3 77 omg, radval skiljer i 17, facit identiskt (21/21 träffar, ROI lika).
  m20 79 omg, radval skiljer i 54, 21/21 träffar, ROI +10,6 % / +8,5 % (rå Δ
  −2,1 %, KI90 [−0,15; +0,09], ROI skiljer i 2 omg). Nominering utan riktning;
  utmanaren mäts framåt.
- **Bifynd som betyder mer än frågan:** Pinnacle är sharp-eligible vid h3 i
  bara 18/87 Topptipsomgångar (h24 29/83, m20 56/88) — 286 `not_listed`-
  captures. Pinnacle listar de flesta Topptipsmatcher först nära avspark. Det
  gör h3 till en tunn horisont för allt Pinnacle-baserat på 8-matchsspelen.
  Frågan om m20 ska vara primär horisont för dem är öppen (backlog 12a).
- Dokument: `docs/ph3-sannolikhetsbas-v1-2026-09-02.md` + JSON (h3, m20).

## 3. pit-total-v1

- Ny tabell `pool_pit_total_features`, `TOTAL_FEATURE_VERSION = "pit-total-v1"`,
  byggd av `pool_dataset.build_total_draw` i varje `build_recent`. Presence-
  regeln är pit-v4:s `sharp_eligible`; totalen är senaste punkt ≤ capture.
  Capture utan total ⇒ rad med `total_eligible=0`; ingen capture ⇒ ingen rad.
  Aldrig bakfylld. pit-v4 orörd.
- Skörd: ≥ 40 Topptipsomgångar med total på alla åtta; frågan är
  förregistrerad i `docs/pool-pit-total-v1-2026-09-02.md`.

## 4. jackpot_close

- `pool_draw_settlement.jackpot_close` + `_observed_at`: senast VERIFIERADE
  snapshot ≤ regCloseTime (`pool_settlement.jackpot_at_close`). Migrering
  `scripts/migrera_jackpot_close.py --skarp`: 9 omgångar, backup
  `stryktips-backup-jackpot-20260902-174304.db`, rapport i `docs/db-atgarder.md`.
- `/api/pool/turnover-prognos` bär `jackpot_close_n/krav` + `jackpot_rader`
  (prognos vid stängning mot utfall). Historik → Prognosträff visar dem.
- Prognosen är jackpotblind tills `JACKPOT_MODEL_MIN_N` = 30 per produkt.

## Regler som tillkom (även i CLAUDE.md)

- En ändrad sannolikhetsbas är en ny `config_key`, aldrig en ändring av
  championen. `prob_base="svs"` förblir standard i appen.
- En ny PIT-feature är en SYSKONSERIE med egen version när den skulle ändra
  en löpande series datagenererande process.
- `jackpot_close` kommer ENBART ur egna verifierade observationer före
  stängning — aldrig `draw.fund`, aldrig dagens jackpotlista. NULL ≠ 0.
- Optimerarens kärna bor i `app/pool_optimizer.py`; skriptet är ett skal.
  Forwardarmar byggs av samma funktion som sökningen.

## Nästa session

1. Verifiera på servern att `poolopt`-armarna fryses på Topptipset 4309
   (h3-fönster 2026-09-03 ~16:00) och att `pit-total-v1` får rader
   (`SELECT COUNT(*) FROM pool_pit_total_features`).
2. Lägg pit-total-grinden i `cli.py gater` när första raden finns.
3. Rör inget av spåren förrän `cli.py gater` säger 40.
