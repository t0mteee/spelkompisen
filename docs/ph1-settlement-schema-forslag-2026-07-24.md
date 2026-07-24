# PH1 — förslag: immutable settlementlager för poolspelen (2026-07-24)

> **GENOMFÖRD samma dag** efter Samans "kör vidare med backloggen" —
> rekommendationerna följdes (fullt djup + framåtriktad settlement direkt).
> Facit: `docs/db-atgarder.md`; kod: `app/pool_settlement.py`,
> `scripts/migrera_pool_settlement.py`, `scripts/backfill_pool_settlement.py`,
> `tests/test_pool_settlement.py`; läs-API `/api/pool/history`.

Utkast för granskning innan något genomförs. Bygger på PH0-fynden
(`docs/ph0-kallaudit-2026-07-24.md`): result/slutstreck/omsättning är
åtkomliga till 2013/2014/2016/2024 beroende på produkt, aktuella odds kan
aldrig bakfyllas, `startOdds` är osemantiserad t.o.m. ~2022.

## Principer

1. **Semantiken i `snapshots`/`sharp_snapshots` ändras inte.** Settlement är
   ett NYTT, append-once-lager; befintliga tabeller rörs inte.
2. **Slug är identiteten.** `topptipset`/`topptipsetstryk`/`topptipsetextra`
   lagras var för sig; gruppering sker först i analyslagret.
3. **Ingen tyst overwrite.** Första lyckade settlement-läsningen är kanon
   (payload-hash sparas). Avvikande omhämtning skrivs ALDRIG över — den
   loggas som divergens och får utredas manuellt.
4. **Kohorten lagras INTE här.** Settlement är facit oavsett kohort;
   `observed_pit`/`final_only` är en egenskap hos feature-underlaget och
   stämplas i PH2-datasetet (härledbar: finns omgången i `snapshots`?).
5. **`startOdds` sparas rått med provenance men är spärrad** för PH2 tills
   providersemantiken verifierats (metodregel i överlämningen).

## Schema (nya tabeller)

```sql
CREATE TABLE IF NOT EXISTS pool_draw_settlement (
    product        TEXT NOT NULL,      -- slug, egen nummerserie per variant
    draw_number    INTEGER NOT NULL,
    draw_state     TEXT NOT NULL,      -- API:ts state vid läsning (Finalized)
    reg_close_time TEXT,               -- API:ts spelstopp (settlement-läsningen)
    net_sale       REAL,               -- slutomsättning (result.currentNetSale)
    row_price      REAL,
    n_events       INTEGER,
    n_cancelled    INTEGER NOT NULL DEFAULT 0,
    product_name   TEXT,               -- API:ts productName (namnbyten, t.ex. VM-tipset)
    source_version TEXT NOT NULL,      -- git-hash för backfill-koden
    payload_hash   TEXT NOT NULL,      -- sha256 över (rå draw-json + rå result-json)
    fetched_at     TEXT NOT NULL,      -- när settlement först observerades av oss
    PRIMARY KEY (product, draw_number)
);

CREATE TABLE IF NOT EXISTS pool_event_settlement (
    product        TEXT NOT NULL,
    draw_number    INTEGER NOT NULL,
    event_number   INTEGER NOT NULL,
    description    TEXT,               -- API:ts eventDescription vid settlement
    home           TEXT,
    away           TEXT,
    match_start    TEXT,
    outcome        TEXT,               -- '1'/'X'/'2' eller NULL (struken/okänd)
    cancelled      INTEGER NOT NULL DEFAULT 0,
    streck_one     INTEGER,            -- svenskaFolket vid settlement = slutstreck
    streck_x       INTEGER,
    streck_two     INTEGER,
    start_odds_one REAL,               -- rått startOdds om API:t bär det;
    start_odds_x   REAL,               --   SPÄRRAT för analys tills semantik
    start_odds_two REAL,               --   verifierats (se princip 5)
    PRIMARY KEY (product, draw_number, event_number)
);

CREATE TABLE IF NOT EXISTS pool_payout_tier (
    product     TEXT NOT NULL,
    draw_number INTEGER NOT NULL,
    tier_name   TEXT NOT NULL,         -- API:ts "13 rätt", "12 rätt", …
    correct     INTEGER,               -- parsat antal rätt (NULL om oparsbart)
    winners     INTEGER,
    amount      REAL,                  -- utdelning per vinnare (kr)
    PRIMARY KEY (product, draw_number, tier_name)
);

-- backfill-journal: gör körningen idempotent, resumable och retrybar
CREATE TABLE IF NOT EXISTS pool_backfill_log (
    product      TEXT NOT NULL,
    draw_number  INTEGER NOT NULL,
    attempted_at TEXT NOT NULL,
    status       TEXT NOT NULL,        -- ok | not_finalized | http_404 |
                                       -- incomplete_result | divergence | error
    detail       TEXT,
    PRIMARY KEY (product, draw_number, attempted_at)
);
```

Skrivregel: hela omgången (draw + events + tiers + logg) i EN transaktion.
`INSERT`-endast; finns raden i `pool_draw_settlement` redan är omgången klar
och hoppas över (idempotens). Divergens (samma nyckel, annan payload_hash vid
kontrolläsning) loggas i `pool_backfill_log` utan att röra kanonraderna.

## Genomförande

- `scripts/migrera_pool_settlement.py`: backup av `data/stryktips.db` →
  skapar tabellerna → rapportsektion i `docs/db-atgarder.md`. Ingen data.
- `scripts/backfill_pool_settlement.py`: läser API:t (0,35 s throttling,
  ~2 anrop/omgång), `--product`, `--from/--to`, `--max-requests`,
  `--retry`-flaggor för `http_404`/`error`-rader. Kräver `Finalized` +
  komplett distribution (vinnare + belopp per nivå), annars
  `incomplete_result` (retrybar). Körs i omgångar; avbrott är ofarligt
  (journalen + PK gör resten).
- Framåtriktat: snapshot-varvet kan efter PH1 skriva settlement för nyss
  avgjorda omgångar via samma kodväg (först observerade settlement = kanon),
  så lagret växer utan separata körningar.

## Testfall (unittest, temp-DB + fejkad API-klient)

1. **Idempotens**: samma omgång backfillas två gånger → identiska rader,
   andra körningen skriver inget och loggar `ok`/skip.
2. **Ingen tyst overwrite**: kontrolläsning med ändrad payload →
   kanonraderna oförändrade, `divergence` loggad med båda hasharna i detail.
3. **Struken match**: event med `cancelled=true` → `cancelled=1`,
   `outcome=NULL`, omgången i övrigt komplett; `n_cancelled` på draw-raden.
4. **Ej färdigspelad**: `Open`/`Closed` eller result=None →
   `not_finalized`, inga settlementrader, retrybar.
5. **Ofullständig distribution**: tier utan winners/amount →
   `incomplete_result`, inga rader (allt-eller-inget per omgång).
6. **Transaktionsatomicitet**: fel mitt i events-skrivningen → inga
   delvisa rader (rollback), `error` loggad.
7. **Variantseparation**: `topptipset` #100 och `topptipsetextra` #100
   samexisterar utan kollision.
8. **startOdds-provenance**: omgång utan startOdds → NULL; med → råvärden
   sparade; inget härlett fält skapas.
9. **Resumability**: avbruten körning (max-requests nådd) → nästa körning
   fortsätter exakt där journalen slutade.

## Öppna frågor till Saman

- Backfill-djup: allt åtkomligt (~3 500 omgångar, ~40 min API-tid) eller
  börja med t.ex. 2 säsonger per produkt? Rekommendation: allt — kostnaden
  är låg och äldsta-gränserna dokumenteras exakt på köpet.
- Ska snapshot-varvet koppla på framåtriktad settlement direkt i PH1 eller
  vänta till PH2? Rekommendation: direkt (samma kodväg, mer observed_pit).
