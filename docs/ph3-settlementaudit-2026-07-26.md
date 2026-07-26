# PH3-settlementaudit — första riktiga systemfacitet

Datum: 2026-07-26 (Fable 5). Godkänd insats ur backloggen (C1). Detta är
granskningen som ENLIGT överlämningen 2026-07-25 skulle göras innan någon ROI
läses ur `/api/pool/systems`.

## Vad som auditerades

30 settlade system (av 42 frysta) i `pool_system_ledger`:
topptipset 24 st (4 omgångar × 3 benchmarkarmar × 2 horisonter h3/m20) och
topptipsetstryk 6 st (1 omgång × 3 × 2). Stryktipset/Europatipset har frysta
men ännu inte settlade system.

1. **Oberoende omräkning av `correct_dist`**: radtexterna re-zippades mot
   settlement-kanonens officiella `outcome` per eventNumber via events_order.
   **30/30 identiska.**
2. **Oberoende omräkning av utspädningen**: `counterfactual_payout`
   (egen vinst späder observerad nivåpott: `own × winners·amount /
   (winners + own)`) räknades om från `pool_payout_tier`-raderna.
   **30/30 identiska belopp, komplett-flaggor och publicerade belopp.**
3. **`payout_complete`**: 30/30 kompletta med utspädningsnot — inga saknade
   belopp, inga träffade nivåer med 0 officiella vinnare.
   ⚠ Det betyder också att **rollover-vägen (0 vinnare ⇒ okänd ROI) ännu inte
   har prövats av skarp data** — bara av tester. Bevaka första gången.
4. **Timing**: 30/30 `timely=1`. `n_evaluable` följer settlade+kompletta i
   `/api/pool/systems`-summeringen; osettlade grupper redovisar `roi: null`
   (aldrig 0).

**Domslut: maskineriet håller.** Ingen avvikelse i någon av de tre
oberoende omräkningarna.

## Siffrorna — får ännu inte tolkas

| arm | omgångar | snitt-ROI |
|---|---|---|
| ev50-medel-vw50 (primär) | 4+1 | −100 % (0 träffade utdelningsnivåer) |
| ev50-tuff-vw80 | 4+1 | −100 % |
| ev256-medel-vw50 | 4+1 | −68,5 % (topptipset; nivåträffar finns) |

h3 och m20 gav identiska utfall (samma rader överlevde till båda frysningarna
i dessa omgångar). **n = 5 omgångar.** Poolspel ger ~1 datapunkt per omgång
och toppvinster bär hela fördelningen — −100 % över 4 omgångar på en
50-kronorsarm är väntad varians, inte en dom. PH5-ablationen (3 976 omgångar)
är fortsatt rätt verktyg för radvalsfrågan; PH3-ledgern är facit för
HELA kedjan (byggare + timing + verklig utdelning) och behöver månader.

## Regler framåt

- ROI härifrån citeras inte förrän gruppen nått meningsfull volym; ingen
  förregistrerad PH3-gate finns ännu — skriv den INNAN någon vill läsa
  siffrorna som bevis.
- Rollover-fallet (0 officiella vinnare på träffad nivå) är oprövat i drift —
  verifiera manuellt första gången `payout_complete=0` dyker upp.
- Auditens omräkningsmetod (re-zip + omräknad utspädning) är återanvändbar:
  kör om den när n växt innan första riktiga avläsningen.
