# Överlämning 2026-11-06 — V2.2 v10 och poolstyrkan avslutade

**Beslut:** 2026-11-06-v22-manifest-pinnacle, val 0 (Saman på beslutssidan):
"Avsluta V2.2-kohorten v10 och styrkeskuggan som de är (missat är missat),
dokumentera slutdatum 2026-11-05 09:30Z, och släck varningarna på Idag. Ny
kohort mot anchor-v1 bara efter ett eget förregistrerat beslut."

## Bakgrund

Pinnacle spärrar Sverige sedan 2026-11-05 09:30Z. anchor-v1 (2026-11-06) gav
sharpen nya versioner (`s-dbe6089a`/`s-2bd0ddd1`) och modellen ny version
(`m-d3d8e5d0`). Båda spåren var frysta mot Pinnacle:

- **V2.2 v10** (`v22-fed39cbd`, `docs/model-v2.2-multileague-forward-manifest-v10.json`)
  fällde kohorten stängd med `source_contract_mismatch` — ett fel på Idag
  ("V2.2-insamlingen behöver tillsyn").
- **pool-strength-blend manifest v2** (`ps-8cbcf320`) visade
  `strength_shadow_stopped` ("styrkeshadowen står still").

## Vad som ändrades

- `oddset_v22.ENDED_COHORTS` och `pool_strength_shadow.ENDED_COHORTS`, nycklade på
  shadow_version, med `ended_at = 2026-11-05T09:30:00Z` och beslutets id.
  Manifestfilerna rörs inte (en ändring i dem vore en ny kohort).
- V2.2: `ended()`; `due_matches` tom, ledgerns sharp-capture hoppar över V2.2-
  grenen (den ordinarie sharp-capturen är orörd), `health()` → `status: "ended"`
  utan issues, `/api/health` räknar `ended` som friskt, `audit()` → `phase: "ended"`,
  `cli.py gater` → `avslutad`.
- Poolstyrkan: `capture_due` → `error: "cohort_ended"`, `stop_status` → `stopped:
  false` + `ended`, `report` → `status: "avslutad"`, ingen
  `strength_shadow_stopped`-varning, `cli.py gater` → `avslutad`, testkatalogen
  lägger Poolstyrka i arkivet med beslutstext.
- UI: Poolmodell-kortet visar "Avslutad", Labb visar V2.2 som avslutad, Oddset-vyns
  forskningsligetext säger att V2.2 avslutats. Pillen `AVSLUTAD` (grå).

## Data

Inga rader ändrade. V2.2 v10: 1 611 rader, 1 250 eligible (2026-08-22 –
2026-11-05 20:02Z; de fem raderna efter 09:30Z är alla oanvändbara —
`direct_fresh_sharp_1x2_missing`). Poolstyrkan v2: 3 088 captures, senaste
2026-11-04 22:02Z. Ingen av dem nådde sin träningsgrind; ingen skörd görs.

## Står kvar

- "För lite färsk Pinnacle" (`sharp_link_coverage`) per poolomgång står kvar på
  Idag: det gäller poolens sharp, som är ett eget beslut och inte ingick här.
- Pinnacle-koden och källprovet står kvar som stödkälla.
- Ny V2.2-/styrkekohort mot anchor-v1 kräver ett eget förregistrerat beslut och
  ett nytt manifest.
