# PH3 sannolikhetsbas v1 — förregistrering av `dr1-b256-medel-sharp`

Datum: 2026-09-02. Status: fryst FÖRE den retroaktiva nomineringskontrollen
kördes och före första framåtfrysningen.

## Upptäckten

`build_ev_system` rankar rader på `_pq`, som tar `fair_prob` — i
`analysis.py` är det SvS-oddsen devigade när SvS-odds finns och Pinnacle bara
som reserv. Samma byggare tar däremot Pinnacle FÖRST i `ev_candidate_signs`
(kandidatuniversumet), `_size_to_budget` och dubbelkupongen. Championen
`dr1-b256-medel` rankar alltså på en annan bas än den väljer kandidater på.

PH4 pit-v4 (skördad 2026-09-02) fällde streck och streckrörelse mot REN
Pinnacle — men den arm som vann där är inte den EV-byggaren kör. Uppmätt
2026-09-02 vid h3 på matcher där båda källorna observerats: L1-avstånd
0,03–0,04 per match, ingen konsekvent riktning, överlapp 12–35 % av
matcherna. Skillnaden är liten men har aldrig mätts som RADVAL.

## Vad som registreras

- `builder.PROB_BASES = ("svs", "sharp")`. `prob_base="svs"` är byte-identisk
  med tidigare beteende och förblir standard i appen, alla profiler och alla
  befintliga nycklar. Ingen befintlig `config_key` ändrar semantik.
- Ny PH3-utmanare **`dr1-b256-medel-sharp`** (`PROB_BASE_CHALLENGERS` i
  `pool_system_ledger.py`): budget 256, strategi medel, värdevikt 0,5,
  draw-risk v1, `prob_base="sharp"` — alltså EXAKT championen med Pinnacle
  före SvS i `_pq`. Saknas Pinnacle för en match faller den matchen tillbaka
  på SvS, som i dag.
- Bara **Topptipset-familjen** (`benchmarks_for` för 8-matchsspelen): där är
  b256 champion, där är PH4:s out-of-time-krav passerat (79/40) och där finns
  retroaktiva pit-v4-omgångar att jämföra mot. Stryk/Europa får ingen
  utmanare förrän deras egna PH4-grindar (6–11/40) är passerade.
- Frysning sker i samma `freeze_due` som championen, vid samma horisonter
  (T−3h, T−20m), med samma turnover-prognos och jackpot. Systemnoten märks
  `Sannolikhetsbas sharp`.

## Två mätningar, en regel

1. **Retroaktiv nomineringskontroll** (`scripts/ph3_sannolikhetsbas_retro.py`,
   read-only mot snapshoten 2026-09-02): båda armarna byggs på pit-v4:s
   h3-sannolikheter (observed_pit, aldrig bakfyllda) och settlas
   kontrafaktiskt med `counterfactual_payout`. Rapporterar parad
   träffskillnad och winsoriserad ROI-skillnad med deterministisk
   bootstrap-KI90 (seed 20260902), andel delade rader och hur många omgångar
   som får identiskt radval. **Får nominera, aldrig promovera:** kohorten är
   retroaktiv även om priserna är point-in-time.
2. **Framåt i PH3** från nästa Topptipsomgång efter driftsättning.
   Promotion enligt PH3:s vanliga regel: BH-FDR över hela utmanarfamiljen
   och ≥ 40 parade omgångar. Championrapporten grupperar på `family_of()`.

Beslutsregel: utmanaren byts inte in i appen av något retroaktivt resultat.
Om den retroaktiva kontrollen visar noll skillnad i radval (identiska rader
i nästan alla omgångar) är det i sig ett fynd — då är inkonsekvensen
kosmetisk och utmanaren kan pensioneras efter 40 framåtomgångar utan vidare
åtgärd. Om den visar stor skillnad med KI90 som täcker noll: fortsätt mäta
framåt, ändra inget.

## Varför inte bara byta bas i appen

Det vore en ändrad datagenererande process för championen mitt i en löpande
PH3-generation. Alla frysta `dr1-b256-medel`-rader skulle då blanda två
baser under samma nyckel. Regeln är den vanliga: ny nyckel, aldrig ändrad
gammal.
