# Pooloptimerare v1 — fullsökning, nominering och forwardtest

Datum: 2026-09-02. Förregistreringen: `docs/pooloptimerare-v1-forregistrering.md`.
Piloten: `docs/pooloptimerare-v1-pilot-2026-08-30.md`.

## Fullsökningen (körd 2026-09-02, lokalt, read-only)

- Källa: `data/optimizer/snapshot-2026-09-02.db` (SQLite onlinebackup 517,2 MB,
  sha256 `d821f3b1…f96`, integrity ok), 8 395 settlade omgångar.
- Kod `61c1c36`, spec `poolopt-topptips256-v1`, seed 20260830, 10 000
  konfigurationer, 4 workers, 38 minuter.
- 2 006 kvalificerade Topptipsfamiljeomgångar sedan 2024-01-01, global
  kronologisk delning 60/20/20: utveckling 1 203, validering 401, historisk
  slutaudit 402.
- Gallring: 10 000 → 1 454 (coarse, 12 omg) → 400 (wide, 64 omg) → 40 (full,
  1 203 omg) → 8 (validering, 401 omg) → 8 i slutauditen. Championen
  (Standard, exakt `build_ev_system`) följde med i varje steg utan ogiltiga
  omgångar.
- Resultatfil: `data/optimizer/topptips256-v1-full-2026-09-02.json` (lokal,
  ej i git). Varningen i filen gäller: `final_only` med slutstreck, relativ
  screening, aldrig spelbar ROI eller promotionsbevis.

## Historisk slutaudit — 402 omgångar som aldrig användes för urval

Champion: 115 av 402 träffar (28,6 %), medel-ROI +8,4 %.

| arm | κ-skala | värdevikt | X-kurva | X-lutning | X-kvot | träffar | Δträff/omg (KI90) | ΔROI winsor (KI90) |
|---|---|---|---|---|---|---|---|---|
| cfg-ed3168f57bceacd6 | 1,114 | 0,29 | −0,039 | −0,008 | 0 | 118 | +0,0075 [0; +0,0174] | +0,013 [−0,002; +0,033] |
| cfg-6c2b6d8c8b242b82 | 1,117 | 0,32 | +0,025 | +0,085 | 0 | 117 | +0,0050 [−0,003; +0,012] | +0,008 [−0,007; +0,023] |
| cfg-859356724deca5af | 1,345 | 0,33 | +0,106 | +0,084 | 0,25 | 117 | +0,0050 [−0,005; +0,015] | +0,006 [−0,012; +0,023] |
| cfg-336ad4488e96002c | 0,860 | 0,32 | +0,087 | +0,198 | 0 | 112 | −0,0075 | −0,017 |
| cfg-7c3642a8e77334ba | 0,936 | 0,27 | +0,093 | +0,191 | 0 | 112 | −0,0075 | −0,017 |
| cfg-115093598d28a627 | 0,989 | 0,60 | −0,012 | +0,039 | 0 | 110 | −0,0124 [−0,025; −0,003] | −0,015 |
| cfg-50d14088eb068f0f | 0,854 | 0,60 | +0,043 | +0,146 | 0 | 104 | −0,0274 [−0,042; −0,015] | −0,044 [−0,067; −0,022] |

Läsning:

- **Ingen arm slår championen på ROI** i slutauditen; championens +8,4 % är
  högst av alla åtta. Armarna med fler träffar träffar billigare omgångar.
- **Träff-armen** är den enda vars KI90 för träffskillnaden ligger helt på
  rätt sida (nedre gräns exakt 0), och dess ROI-KI täcker noll. Det är en
  nominering, inte ett bevis: efter en 10 000-sökning är ojusterade KI:n
  diagnostik.
- Alla tre nominerade delar två drag: **lägre värdevikt (≈0,3 mot 0,5)** och
  **κ-skala > 1** (mer utspädning antagen). De två armar som höjde
  värdevikten (0,60) blev sämre. Det är en hypotes om Standard, inte en
  slutsats — den testas framåt.
- Sign-cap kom aldrig under 1,0 bland finalisterna: teckentaket bidrog inget.

## Nominering (högst tre tydligt olika, enligt förregistreringen)

| nyckel | arm | källa |
|---|---|---|
| `poolopt-v1-b256-traff` | träff | cfg-ed3168f57bceacd6 |
| `poolopt-v1-b256-balans` | balans | cfg-6c2b6d8c8b242b82 |
| `poolopt-v1-b256-xkvot` | X-kvot (enda med X-minimikvot) | cfg-859356724deca5af |

En ren ROI-/referensarm nominerades INTE: ingen finalist slog championen på
den axeln, och att välja "minst dålig" vore urval på slutauditen.

## Forwardtestet

- Research-familj `poolopt` i `pool_system_ledger.POOLOPT_FORWARD_CONFIGS`,
  bara Topptipset-familjen (8 matcher). Start: nästa omgång vars h3-fönster
  inte öppnat vid driftsättningen — Topptipset 4309, Stryk 979, Extra 1864.
- Raderna byggs av `app/pool_optimizer.rows_for` — sökningens radval,
  flyttat till appen utan numerisk ändring (regressionstest: championens
  konfiguration reproducerar `build_ev_system` rad för rad).
- Samma frysta referensmodell (fair_prob + streck), samma prognosomsättning
  som championen, **ingen jackpot** (sökningen kördes utan). Horisonter h3 och
  m20 som övriga PH3.
- Research-only: aldrig promotion, aldrig kupongförslag. Grind för att
  överhuvudtaget FÖRESLÅ en PH3-utmanare ur familjen: ≥ 40 parade omgångar
  per arm mot `dr1-b256-medel`, träff-Δ med undre KI90 > 0 ELLER ROI-Δ med
  undre KI90 > 0 på framåtdata. Uppfyllt ⇒ ny förregistrerad utmanare med
  egen nyckel, aldrig promotion direkt ur research-familjen.
- Avslut: efter 120 framåtomgångar utan passerad grind pensioneras familjen.

## Nästa optimerarversion

Enligt piloten: v2 för 512 rader, sedan Stryk/Europa — var för sig, aldrig
blandade budgetar. En v2 ska ta X-risk v1 (`pool-draw-risk-v1`) som egen
champion; v1 mätte medvetet mot den gamla standarden.
