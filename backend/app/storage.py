"""SQLite-lagring av snapshots.

Varje gång vi pollar Svenska Spel sparar vi ett "snapshot" per utfall.
Det gör att vi kan rita oddsrörelse och streckrörelse över tid fram till
matchstart — själva kärnan i att upptäcka tecken som stärks sent.

Tabeller
--------
draws       : en rad per (product, draw_number) vi sett
snapshots   : en rad per (draw, event, sign, mättidpunkt)
"""
from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
from pathlib import Path
from typing import Optional

from .svenskaspel import Draw

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "stryktips.db"

PREDICTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_prediction_capture (
    match_id       TEXT NOT NULL,
    horizon        TEXT NOT NULL,          -- h24 | h3 | m20
    tier           TEXT NOT NULL,          -- sharp | model
    signal_version TEXT NOT NULL,
    base_version   TEXT NOT NULL,
    match_start    TEXT NOT NULL,
    target_at      TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    offset_minutes REAL NOT NULL,          -- faktisk tid kvar till avspark
    delay_minutes  REAL NOT NULL,          -- hur sent efter nominell horisont
    row_count      INTEGER NOT NULL,
    PRIMARY KEY (match_id, horizon, tier, signal_version)
);

CREATE TABLE IF NOT EXISTS oddset_prediction_log (
    match_id       TEXT NOT NULL,
    horizon        TEXT NOT NULL,
    tier           TEXT NOT NULL,
    market         TEXT NOT NULL,
    sign           TEXT NOT NULL,
    line           REAL,
    line_key       INTEGER NOT NULL,
    league         TEXT,
    description    TEXT,
    match_start    TEXT NOT NULL,
    target_at      TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    offset_minutes REAL NOT NULL,
    fair_prob      REAL NOT NULL,
    fair_source    TEXT NOT NULL,           -- pinnacle | derived | model
    fair_available INTEGER NOT NULL,
    fair_fresh     INTEGER NOT NULL,
    model_anchored INTEGER,
    book           TEXT,
    book_odds      REAL,
    book_available INTEGER NOT NULL,
    book_fresh     INTEGER NOT NULL,
    edge           REAL,
    eligible       INTEGER NOT NULL,        -- får ingå i signalutvärdering
    is_flag        INTEGER NOT NULL,        -- förregistrerad regel vid capture
    signal_version TEXT NOT NULL,
    base_version   TEXT NOT NULL,
    git_hash       TEXT,
    closing_fair   REAL,
    closing_odds   REAL,
    closing_line   REAL,
    line_delta     REAL,
    line_move_score REAL,
    closing_note   TEXT,
    PRIMARY KEY (match_id, horizon, tier, market, sign, signal_version)
);
CREATE INDEX IF NOT EXISTS idx_prediction_open
    ON oddset_prediction_log (match_start, closing_fair, closing_note);
CREATE INDEX IF NOT EXISTS idx_prediction_group
    ON oddset_prediction_log (tier, league, market, signal_version, is_flag);

CREATE TABLE IF NOT EXISTS oddset_prediction_group_state (
    tier           TEXT NOT NULL,
    league         TEXT NOT NULL,
    market         TEXT NOT NULL,
    signal_version TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'amber',
    candidate_at   TEXT,
    green_at       TEXT,
    PRIMARY KEY (tier, league, market, signal_version)
);
"""

ABSENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_absence_capture (
    match_id        TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    source_event_id TEXT,
    match_start     TEXT,
    confirmed       INTEGER NOT NULL,
    payload_hash    TEXT NOT NULL,
    home_missing    INTEGER NOT NULL,
    away_missing    INTEGER NOT NULL,
    missing_count   INTEGER NOT NULL,
    PRIMARY KEY (match_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_absence_capture_match
    ON oddset_absence_capture (match_id, captured_at);

CREATE TABLE IF NOT EXISTS oddset_absence_player (
    match_id        TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('home', 'away')),
    player_key      TEXT NOT NULL,
    player_id       INTEGER,
    name            TEXT NOT NULL,
    position        TEXT,
    reason_code     INTEGER,
    reason          TEXT,
    description     TEXT,
    expected_end    TEXT,
    appearances     INTEGER,
    rating          REAL,
    PRIMARY KEY (match_id, captured_at, side, player_key)
);
CREATE INDEX IF NOT EXISTS idx_absence_player_identity
    ON oddset_absence_player (player_id, captured_at);
"""

ELO_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_elo_capture (
    captured_at   TEXT PRIMARY KEY,
    requested_date TEXT NOT NULL,
    source        TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,
    row_count     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_elo_capture_current
    ON oddset_elo_capture (source, captured_at);

CREATE TABLE IF NOT EXISTS oddset_elo_rating (
    captured_at TEXT NOT NULL,
    club_key    TEXT NOT NULL,
    club_raw    TEXT NOT NULL,
    country     TEXT,
    level       INTEGER,
    elo         REAL NOT NULL,
    valid_from  TEXT,
    valid_to    TEXT,
    PRIMARY KEY (captured_at, club_key)
);
CREATE INDEX IF NOT EXISTS idx_elo_rating_club
    ON oddset_elo_rating (club_key, captured_at);

CREATE TABLE IF NOT EXISTS oddset_elo_history (
    club_key         TEXT NOT NULL,
    valid_from       TEXT NOT NULL,
    valid_to         TEXT NOT NULL,
    club_raw         TEXT NOT NULL,
    country          TEXT NOT NULL,
    level            INTEGER,
    elo              REAL NOT NULL,
    first_fetched_at TEXT NOT NULL,
    last_fetched_at  TEXT NOT NULL,
    PRIMARY KEY (club_key, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_elo_history_asof
    ON oddset_elo_history (valid_from, valid_to, club_key);
"""

V2_FEATURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_v2_feature_capture (
    match_id            TEXT NOT NULL,
    horizon             TEXT NOT NULL,
    model_signal_version TEXT NOT NULL,
    feature_version     TEXT NOT NULL,
    captured_at         TEXT NOT NULL,
    match_start         TEXT NOT NULL,
    capture_mode        TEXT NOT NULL,       -- live | reconstructed
    payload_hash        TEXT NOT NULL,
    payload_json        TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    PRIMARY KEY (match_id, horizon, model_signal_version, feature_version)
);
CREATE INDEX IF NOT EXISTS idx_v2_feature_version
    ON oddset_v2_feature_capture (feature_version, captured_at, match_id);
"""

V22_SHADOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_v22_shadow_capture (
    match_id             TEXT NOT NULL,
    horizon              TEXT NOT NULL,
    shadow_version       TEXT NOT NULL,
    feature_version      TEXT NOT NULL,
    sharp_signal_version TEXT NOT NULL,
    model_signal_version TEXT NOT NULL,
    league               TEXT NOT NULL,
    match_start          TEXT NOT NULL,
    target_at            TEXT NOT NULL,
    captured_at          TEXT NOT NULL,
    offset_minutes       REAL NOT NULL,
    delay_minutes        REAL NOT NULL,
    state                TEXT NOT NULL,
    eligible             INTEGER NOT NULL,
    fallback_reason      TEXT NOT NULL,
    issues_json          TEXT NOT NULL,
    sharp_p1             REAL,
    sharp_px             REAL,
    sharp_p2             REAL,
    v22_p1               REAL,
    v22_px               REAL,
    v22_p2               REAL,
    feature_payload_hash TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    PRIMARY KEY (match_id, horizon, shadow_version)
);
CREATE INDEX IF NOT EXISTS idx_v22_shadow_version
    ON oddset_v22_shadow_capture
       (shadow_version, league, horizon, captured_at, match_id);
"""

TEAM_EVENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_sofa_team (
    team_id           INTEGER PRIMARY KEY,
    team_key          TEXT NOT NULL,
    name              TEXT NOT NULL,
    country_code      TEXT,
    sport             TEXT NOT NULL,
    venue_id          INTEGER,
    venue_name        TEXT,
    venue_city        TEXT,
    venue_lat         REAL,
    venue_lon         REAL,
    first_seen_at     TEXT NOT NULL,
    last_seen_at      TEXT NOT NULL,
    detail_fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sofa_team_key
    ON oddset_sofa_team (team_key, team_id);

CREATE TABLE IF NOT EXISTS oddset_sofa_team_scope (
    team_id       INTEGER NOT NULL,
    league        TEXT NOT NULL,
    season_id     INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    PRIMARY KEY (team_id, league, season_id)
);
CREATE INDEX IF NOT EXISTS idx_sofa_team_scope_league
    ON oddset_sofa_team_scope (league, season_id, team_id);

CREATE TABLE IF NOT EXISTS oddset_sofa_team_event_capture (
    team_id         INTEGER NOT NULL,
    captured_at     TEXT NOT NULL,
    policy_version  TEXT NOT NULL,
    page_count      INTEGER NOT NULL,
    raw_event_count INTEGER NOT NULL,
    event_count     INTEGER NOT NULL,
    oldest_start    TEXT,
    newest_start    TEXT,
    payload_hash    TEXT NOT NULL,
    PRIMARY KEY (team_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_sofa_team_event_capture_latest
    ON oddset_sofa_team_event_capture (team_id, captured_at);

CREATE TABLE IF NOT EXISTS oddset_sofa_team_event (
    event_id             INTEGER PRIMARY KEY,
    start_at             TEXT NOT NULL,
    status               TEXT NOT NULL,
    home_team_id         INTEGER NOT NULL,
    away_team_id         INTEGER NOT NULL,
    tournament_id        INTEGER,
    unique_tournament_id INTEGER,
    tournament_name      TEXT,
    tournament_slug      TEXT,
    country_code         TEXT,
    home_score           INTEGER,
    away_score           INTEGER,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sofa_team_event_home
    ON oddset_sofa_team_event (home_team_id, start_at);
CREATE INDEX IF NOT EXISTS idx_sofa_team_event_away
    ON oddset_sofa_team_event (away_team_id, start_at);
CREATE INDEX IF NOT EXISTS idx_sofa_team_event_pit
    ON oddset_sofa_team_event (first_seen_at, start_at);

-- PIT-förändringsserie för avsparkstid (granskningsfix F5a 2026-07-26):
-- upserten ovan skriver över start_at vid ombokning, så en as-of-läsning
-- behöver tiden SOM DEN VAR KÄND vid as_of. En rad per observerad ändring.
CREATE TABLE IF NOT EXISTS oddset_sofa_team_event_start (
    event_id INTEGER NOT NULL,
    start_at TEXT NOT NULL,
    seen_at  TEXT NOT NULL,
    PRIMARY KEY (event_id, seen_at)
);
"""

# PH1 (2026-07-24): immutable settlementlager för poolspelen. Append-once:
# första lyckade settlement-läsningen är kanon (payload_hash), avvikande
# omhämtningar loggas som divergens i pool_backfill_log utan overwrite.
# Kohort (observed_pit/final_only) lagras INTE här — den stämplas i PH2.
POOL_SETTLEMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_draw_settlement (
    product        TEXT NOT NULL,
    draw_number    INTEGER NOT NULL,
    draw_state     TEXT NOT NULL,
    reg_close_time TEXT,
    net_sale       REAL,
    row_price      REAL,
    n_events       INTEGER,
    n_cancelled    INTEGER NOT NULL DEFAULT 0,
    product_name   TEXT,
    source_version TEXT NOT NULL,
    payload_hash   TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    PRIMARY KEY (product, draw_number)
);

CREATE TABLE IF NOT EXISTS pool_event_settlement (
    product        TEXT NOT NULL,
    draw_number    INTEGER NOT NULL,
    event_number   INTEGER NOT NULL,
    description    TEXT,
    home           TEXT,
    away           TEXT,
    match_start    TEXT,
    outcome        TEXT,
    cancelled      INTEGER NOT NULL DEFAULT 0,
    streck_one     INTEGER,
    streck_x       INTEGER,
    streck_two     INTEGER,
    start_odds_one REAL,
    start_odds_x   REAL,
    start_odds_two REAL,
    PRIMARY KEY (product, draw_number, event_number)
);

CREATE TABLE IF NOT EXISTS pool_payout_tier (
    product     TEXT NOT NULL,
    draw_number INTEGER NOT NULL,
    tier_name   TEXT NOT NULL,
    correct     INTEGER,
    winners     INTEGER,
    amount      REAL,
    PRIMARY KEY (product, draw_number, tier_name)
);

CREATE TABLE IF NOT EXISTS pool_backfill_log (
    product      TEXT NOT NULL,
    draw_number  INTEGER NOT NULL,
    attempted_at TEXT NOT NULL,
    status       TEXT NOT NULL,
    detail       TEXT,
    PRIMARY KEY (product, draw_number, attempted_at)
);
CREATE INDEX IF NOT EXISTS idx_pool_backfill_latest
    ON pool_backfill_log (product, draw_number, attempted_at DESC);
"""

# PH2/PH3 (2026-07-24): PIT-dataset + systemledger för poolspelen.
# pool_draw_snapshot är den FRAMÅTRIKTADE omsättnings-/jackpottserien
# (fanns inte historiskt — turnover_asof är därför null för äldre omgångar).
# pool_pit_* fryser features per omgång/horisont ur snapshots-kohorten
# (observed_pit ENBART — final_only har per definition inga horisonter).
# pool_system_ledger fryser byggarens konkreta förslag före spelstopp
# (förregistrerad benchmarkmatris) och settlas mot pool_draw_settlement.
POOL_PIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_draw_snapshot (
    product     TEXT NOT NULL,
    draw_number INTEGER NOT NULL,
    fetched_at  TEXT NOT NULL,
    net_sale    REAL,
    jackpot     REAL,
    jackpot_source TEXT NOT NULL DEFAULT 'missing',
    PRIMARY KEY (product, draw_number, fetched_at)
);

-- Presence-ledger: en rad per lyckad källäsning och event, även när pris/
-- streck INTE ändrades. snapshots/sharp_snapshots fortsätter vara kompakta
-- förändringsserier; den här tabellen är observationsklockan för PIT.
CREATE TABLE IF NOT EXISTS pool_market_capture (
    product         TEXT NOT NULL,
    draw_number     INTEGER NOT NULL,
    source          TEXT NOT NULL CHECK (source IN ('svs', 'sharp')),
    event_number    INTEGER NOT NULL,
    fetched_at      TEXT NOT NULL,
    status          TEXT NOT NULL,
    odds_complete   INTEGER NOT NULL,
    streck_complete INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (product, draw_number, source, event_number, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_pool_market_capture_asof
    ON pool_market_capture
       (product, draw_number, source, event_number, fetched_at DESC);

CREATE TABLE IF NOT EXISTS pool_pit_draw_features (
    product         TEXT NOT NULL,
    draw_number     INTEGER NOT NULL,
    horizon         TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    cohort          TEXT NOT NULL,
    asof            TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    n_events        INTEGER,
    n_covered_svs   INTEGER,
    n_covered_sharp INTEGER,
    n_covered_streck INTEGER,
    entropy_folk    REAL,
    entropy_market  REAL,
    favorite_pressure REAL,
    difficulty      REAL,
    turnover_asof   REAL,
    jackpot_asof    REAL,
    timing_policy   TEXT,
    PRIMARY KEY (product, draw_number, horizon, feature_version)
);

CREATE TABLE IF NOT EXISTS pool_pit_match_features (
    product         TEXT NOT NULL,
    draw_number     INTEGER NOT NULL,
    horizon         TEXT NOT NULL,
    event_number    INTEGER NOT NULL,
    feature_version TEXT NOT NULL,
    asof            TEXT NOT NULL,
    svs_lag_min     REAL,
    sharp_lag_min   REAL,
    svs_eligible    INTEGER NOT NULL DEFAULT 0,
    sharp_eligible  INTEGER NOT NULL DEFAULT 0,
    p_svs_1 REAL, p_svs_x REAL, p_svs_2 REAL,
    p_sharp_1 REAL, p_sharp_x REAL, p_sharp_2 REAL,
    streck_1 INTEGER, streck_x INTEGER, streck_2 INTEGER,
    move_svs_pp_1 REAL, move_svs_pp_x REAL, move_svs_pp_2 REAL,
    move_sharp_pp_1 REAL, move_sharp_pp_x REAL, move_sharp_pp_2 REAL,
    gap_1 REAL, gap_x REAL, gap_2 REAL,
    reversal_sign   TEXT,
    PRIMARY KEY (product, draw_number, horizon, event_number, feature_version)
);

CREATE TABLE IF NOT EXISTS pool_system_ledger (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    horizon       TEXT NOT NULL,
    config_key    TEXT NOT NULL,
    frozen_at     TEXT NOT NULL,
    lag_min       REAL NOT NULL,
    timely        INTEGER NOT NULL,
    code_version  TEXT NOT NULL,
    budget        REAL NOT NULL,
    strategy      TEXT NOT NULL,
    value_weight  REAL NOT NULL,
    row_price     REAL,
    n_rows        INTEGER NOT NULL,
    cost_kr       REAL NOT NULL,
    events_order  TEXT NOT NULL,
    rows_text     TEXT NOT NULL,
    rows_hash     TEXT NOT NULL,
    n_events_covered INTEGER,
    turnover_used REAL,
    turnover_basis TEXT,
    jackpot_used  REAL,
    jackpot_source TEXT NOT NULL DEFAULT 'missing',
    build_note    TEXT,
    settled_at    TEXT,
    correct_max   INTEGER,
    correct_dist  TEXT,
    payout_kr     REAL,
    published_payout_kr REAL,
    payout_complete INTEGER,
    settlement_version TEXT,
    roi           REAL,
    settle_note   TEXT,
    PRIMARY KEY (product, draw_number, horizon, config_key)
);
CREATE INDEX IF NOT EXISTS idx_pool_system_open
    ON pool_system_ledger (settled_at, product, draw_number);

-- VERKLIGT SPELADE KUPONGER (2026-07-25). Skild från pool_system_ledger med
-- avsikt: ledgern innehåller KONTRAFAKTISKA benchmarksystem som aldrig lämnades
-- in, och därför späds deras vinst ut mot observerad nivåpott. En kupong Saman
-- faktiskt spelat ligger redan i potten — SvS publicerade belopp per vinnare
-- inkluderar honom. Utdelningen är alltså `andel_rader_på_nivån × publicerat
-- belopp`, RAKT, utan utspädningskorrigering. Att blanda de två hade gett fel
-- siffra i båda riktningarna.
CREATE TABLE IF NOT EXISTS pool_played_coupon (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    played_at     TEXT NOT NULL,
    label         TEXT,
    build_kind    TEXT,                -- värderader | reducerat | garanti | ...
    strategy      TEXT,
    value_weight  REAL,
    budget        REAL,
    row_price     REAL NOT NULL,
    n_rows        INTEGER NOT NULL,
    cost_kr       REAL NOT NULL,
    events_order  TEXT NOT NULL,       -- eventnummer i radernas ordning
    rows_text     TEXT NOT NULL,       -- en rad per spelrad, tecken utan skiljetecken
    rows_hash     TEXT NOT NULL,
    code_version  TEXT,
    note          TEXT,
    settled_at    TEXT,
    correct_max   INTEGER,
    correct_dist  TEXT,
    payout_kr     REAL,
    payout_complete INTEGER,
    roi           REAL,
    settle_note   TEXT,
    UNIQUE (product, draw_number, rows_hash)
);
CREATE INDEX IF NOT EXISTS idx_pool_played_open
    ON pool_played_coupon (settled_at, product, draw_number);
"""

# Live-radar (2026-07-25): observerade, kumulativa matchstats i shadow mode.
# Tabellen lagrar källobservationer, inte spelrekommendationer. Signalen kan
# därmed ändras/versioneras och utvärderas i efterhand utan att rådata skrivs om.
LIVE_RADAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS oddset_live_capture (
    event_id          INTEGER NOT NULL,
    captured_at       TEXT NOT NULL,
    capture_version   TEXT NOT NULL,
    league            TEXT NOT NULL,
    tournament        TEXT,
    home              TEXT NOT NULL,
    away              TEXT NOT NULL,
    start_at          TEXT,
    status            TEXT NOT NULL,
    minute            INTEGER,
    home_score        INTEGER NOT NULL,
    away_score        INTEGER NOT NULL,
    xg_home           REAL,
    xg_away           REAL,
    big_chances_home  INTEGER,
    big_chances_away  INTEGER,
    shots_home        INTEGER,
    shots_away        INTEGER,
    shots_on_home     INTEGER,
    shots_on_away     INTEGER,
    shots_inside_home INTEGER,
    shots_inside_away INTEGER,
    touches_box_home  INTEGER,
    touches_box_away  INTEGER,
    corners_home      INTEGER,
    corners_away      INTEGER,
    PRIMARY KEY (event_id, captured_at, capture_version)
);
CREATE INDEX IF NOT EXISTS idx_oddset_live_capture_recent
    ON oddset_live_capture (captured_at DESC, event_id);

-- FotMob-livecaptures i EGEN tabell (2026-07-25). xG blandas ALDRIG mellan
-- providers (WP9a-regeln): FotMobs id-rymd, fältuppsättning och xG-modell är
-- sina egna, och en radarserie för en match måste hålla sig till en provider —
-- annars mäter xG-deltat mellan två ticks skillnaden mellan två modeller.
-- Sofascore saknar xG helt för Allsvenskan, vilket är hela skälet att källan
-- finns. Shadow: aldrig tips, Kelly, notiser, CLV eller modellinput.
CREATE TABLE IF NOT EXISTS oddset_live_fotmob (
    fotmob_id         INTEGER NOT NULL,
    captured_at       TEXT NOT NULL,     -- hämtningstid − HTTP Age
    capture_version   TEXT NOT NULL,
    league            TEXT NOT NULL,
    tournament        TEXT,
    home              TEXT NOT NULL,
    away              TEXT NOT NULL,
    start_at          TEXT,
    minute            INTEGER,
    home_score        INTEGER,
    away_score        INTEGER,
    xg_home           REAL,
    xg_away           REAL,
    xgot_home         REAL,
    xgot_away         REAL,
    xg_open_home      REAL,
    xg_open_away      REAL,
    big_chances_home  REAL,
    big_chances_away  REAL,
    shots_home        REAL,
    shots_away        REAL,
    shots_on_home     REAL,
    shots_on_away     REAL,
    shots_inside_home REAL,
    shots_inside_away REAL,
    PRIMARY KEY (fotmob_id, captured_at, capture_version)
);
CREATE INDEX IF NOT EXISTS idx_oddset_live_fotmob_recent
    ON oddset_live_fotmob (captured_at DESC, fotmob_id);

-- Settlement per capture-ÖGONBLICK (2026-07-26, steg 2–3 i den förregistrerade
-- planen docs/live-radar-2026-07-25.md). VARJE capture-rad settlas — signal
-- eller inte — eftersom kontrollgruppen för den villkorade basraten är just
-- icke-signal-ögonblicken. Signalen räknas om deterministiskt ur radens råa
-- fält med SAMMA funktion som API:t (live_radar.radar_signal); providrar
-- blandas aldrig (Sofascore-serier settlas mot Sofascore, FotMob mot FotMob).
-- Append-once: INSERT OR IGNORE på naturlig nyckel — en settlad rad skrivs
-- ALDRIG om. NULL-utfall betyder censorerat (orsak i egen kolumn), aldrig 0.
-- Shadow: läses bara av radar-facit, aldrig av tips/Kelly/notiser/CLV/modell.
CREATE TABLE IF NOT EXISTS oddset_live_moment_settlement (
    provider          TEXT NOT NULL,      -- 'sofascore' | 'fotmob' (= xg_source)
    event_id          INTEGER NOT NULL,   -- sofa event_id resp. fotmob_id
    captured_at       TEXT NOT NULL,
    capture_version   TEXT NOT NULL,
    league            TEXT,
    minute            INTEGER,
    score_diff        INTEGER,            -- hemma − borta vid ögonblicket
    signal            INTEGER NOT NULL,   -- 0/1, omräknad ur råa capturefält
    signal_type       TEXT,               -- radar_signal-kind: xg/proxy/no_stats/no_clock
    signal_version    TEXT NOT NULL,
    outcome_15min     INTEGER,            -- utfall A: mål inom 15 min SPELTID (NULL = censur)
    outcome_more_before_ft INTEGER,       -- utfall B: fler mål före full tid (NULL = censur)
    censored_15min    TEXT,               -- orsak när outcome_15min är NULL
    censored_ft       TEXT,               -- orsak när outcome_more_before_ft är NULL
    settled_at        TEXT NOT NULL,
    PRIMARY KEY (provider, event_id, captured_at, capture_version)
);
CREATE INDEX IF NOT EXISTS idx_live_moment_settlement_facit
    ON oddset_live_moment_settlement (signal_type, signal, league);
"""

MATCHBOOK_SCHEMA = """
-- Matchbook (2026-07-27): TREDJE oberoende marknadsreferensen — ENDAST
-- skugginsamling i snabbfönstret (docs/bookmaker-kallplan-2026-07-25.md).
-- Oddsen ligger i oddset_odds (source='matchbook'); denna tabell bär den
-- TILLGÄNGLIGA back-likviditeten (EUR, vid bästa back-odds) per selektion,
-- ur SAMMA källsvar som priset (en observationstid). Append-serie med
-- monotonisk seen_at: nytt belopp = ny rad; oförändrat belopp flyttar
-- senaste radens seen_at framåt; ett svar äldre än senaste observation
-- skrivs aldrig (klockan går bara framåt). Läses av inget runtime-flöde —
-- bara det kommande frysta shadow-facitet (>= 28 dagar). Tunn likviditet
-- får ALDRIG bekräfta eller underkänna en edge.
CREATE TABLE IF NOT EXISTS oddset_matchbook_liquidity (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id  TEXT NOT NULL,
    sign      TEXT NOT NULL,             -- 1/X/2
    available REAL,                      -- EUR vid bästa tillgängliga back-odds
    seen_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_oddset_matchbook_liq
    ON oddset_matchbook_liquidity (match_id, sign, seen_at);
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    state         TEXT,
    reg_close_time TEXT,
    PRIMARY KEY (product, draw_number)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    odds          REAL,
    start_odds    REAL,
    streck        INTEGER,
    fetched_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snap_lookup
    ON snapshots (product, draw_number, event_number, sign, fetched_at);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sharp_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    odds          REAL,
    fetched_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sharpsnap_lookup
    ON sharp_snapshots (product, draw_number, event_number, sign, fetched_at);

CREATE TABLE IF NOT EXISTS sharp_odds (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    bookmaker     TEXT,
    one           REAL,
    x             REAL,
    two           REAL,
    confidence    REAL,
    matched       TEXT,
    fetched_at    TEXT,
    PRIMARY KEY (product, draw_number, event_number)
);

-- Flaggade värdetecken (CLV-facit): first/best per selektion + devigad
-- Pinnacle-stängning före avspark + facit. Positiv snitt-CLV = signalen äkta.
CREATE TABLE IF NOT EXISTS value_log (
    product       TEXT NOT NULL,
    draw_number   INTEGER NOT NULL,
    event_number  INTEGER NOT NULL,
    sign          TEXT NOT NULL,
    description   TEXT,
    match_start   TEXT,
    flag_type     TEXT,
    first_at      TEXT,
    first_odds    REAL,
    first_prob    REAL,
    prob_src      TEXT,
    first_streck  INTEGER,
    first_ratio   REAL,
    best_ratio    REAL,
    best_at       TEXT,
    closing_prob  REAL,
    closing_odds  REAL,
    closing_note  TEXT,
    outcome       INTEGER,
    PRIMARY KEY (product, draw_number, event_number, sign)
);

-- Oddset-delen (enskilda matcher, se app/oddset.py)
CREATE TABLE IF NOT EXISTS oddset_matches (
    id           TEXT PRIMARY KEY,      -- 'pin:<matchupId>' | 'svs:<eventId>'
    league       TEXT NOT NULL,         -- nyckel i oddset.LEAGUES
    home         TEXT NOT NULL,
    away         TEXT NOT NULL,
    start        TEXT,                  -- UTC ISO
    pinnacle_id  TEXT,
    kambi_id     TEXT,
    status       TEXT,
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_oddset_matches_start ON oddset_matches (start);
-- En extern provideridentitet får höra till exakt en canonical match.
-- Indexen skapades på prod-DB först efter backup + audit/sanering via
-- scripts/sanera_oddset_identitetskrockar.py (2026-07-26).
CREATE UNIQUE INDEX IF NOT EXISTS uq_oddset_matches_pinnacle_id
    ON oddset_matches (pinnacle_id) WHERE pinnacle_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_oddset_matches_kambi_id
    ON oddset_matches (kambi_id) WHERE kambi_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS oddset_odds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    TEXT NOT NULL,
    source      TEXT NOT NULL,          -- 'pinnacle' | 'derived' | 'svenskaspel'
    market      TEXT NOT NULL,          -- '1x2' | 'ah' | 'ou'
    sign        TEXT NOT NULL,          -- 1x2: 1/X/2 · ah: H/A · ou: O/U
    line        REAL,                   -- handikapp (hemmaperspektiv) / totallinje
    odds        REAL,
    fetched_at  TEXT NOT NULL,          -- när just detta pris/denna linje först sågs
    last_seen_at TEXT NOT NULL,         -- senaste lyckade svar som fortfarande bar priset
    available   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_oddset_odds
    ON oddset_odds (match_id, source, market, sign, fetched_at);

CREATE TABLE IF NOT EXISTS oddset_source_health (
    source       TEXT NOT NULL,
    league       TEXT NOT NULL,
    scope        TEXT NOT NULL,          -- 1x2 | markets | deep
    checked_at   TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    event_count  INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    PRIMARY KEY (source, league, scope)
);

CREATE TABLE IF NOT EXISTS oddset_results (
    league    TEXT NOT NULL,
    date      TEXT NOT NULL,            -- YYYY-MM-DD
    home      TEXT NOT NULL,            -- normaliserat (oddset.norm_team)
    away      TEXT NOT NULL,
    home_raw  TEXT,
    away_raw  TEXT,
    hg INTEGER, ag INTEGER,
    xg_h REAL, xg_a REAL,
    cor_h REAL, cor_a REAL,
    source    TEXT,
    PRIMARY KEY (league, date, home, away)
);

-- Sharpens ALLA linjer per parmarknad (alt-linjer): möjliggör samma-linje-
-- jämförelse när boken visar en annan lina än huvudlinan (steg-upp 2026-07-20).
-- Endast Pinnacle — fair-sidan. Dedup per (match, marknad, linje, tecken);
-- oförändrat pris flyttar last_seen_at; linje borta ur lyckat svar => available=0.
CREATE TABLE IF NOT EXISTS oddset_sharp_alt (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id     TEXT NOT NULL,
    market       TEXT NOT NULL,          -- 'ah' | 'ou' | 'cor'
    line         REAL NOT NULL,          -- ah: hemmaperspektiv; ou/cor: total
    sign         TEXT NOT NULL,          -- H/A | O/U
    odds         REAL,
    fetched_at   TEXT NOT NULL,          -- när priset senast ändrades
    last_seen_at TEXT NOT NULL,          -- senaste lyckade svar som bar priset
    available    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_oddset_sharp_alt
    ON oddset_sharp_alt (match_id, market, line, sign, fetched_at);

CREATE TABLE IF NOT EXISTS oddset_value_log (
    match_id     TEXT NOT NULL,
    market       TEXT NOT NULL,
    sign         TEXT NOT NULL,
    line         REAL,
    line_key     INTEGER NOT NULL,       -- round(line*1000), sentinel för 1X2
    league       TEXT,
    description  TEXT,
    match_start  TEXT,
    first_at     TEXT,
    first_odds   REAL,
    first_fair   REAL,
    first_edge   REAL,
    best_edge    REAL,
    best_at      TEXT,
    closing_fair REAL,
    closing_odds REAL,
    closing_line REAL,
    line_delta   REAL,
    line_move_score REAL,                -- >0 = linan rörde sig med selektionen
    closing_note TEXT,
    book         TEXT,
    tier         TEXT DEFAULT 'sharp',
    model_version TEXT NOT NULL DEFAULT 'legacy',
    git_hash     TEXT,
    -- ANDRA ANKARET (skuggmätning, 2026-07-25): påverkar ALDRIG urval, edge,
    -- notiser eller signal_version. Finns bara för att kunna svara på frågan
    -- "är edgen marknadens eller devigmetodens?" — devigvalet rör ~3 pp medan
    -- flaggtröskeln är 2 pp. Skrivs vid first (aldrig omskrivet) + vid stängning.
    anchor2_source       TEXT,
    anchor2_fair         REAL,
    anchor2_edge         REAL,
    anchor2_closing_fair REAL,
    anchor2_note         TEXT,
    -- UTFALLS-FACIT (P2, 2026-07-28): resultatbaserad ROI som KOMPLEMENT till
    -- close-EV. Grindarna (grönt-kriteriet) ägs fortsatt av close-EV; utfallet
    -- är display/validering. Settlas endast för 1X2 i v1 (par-marknaders
    -- push-/kvartslinjelogik är en egen fråga). NULL = ej settlad än.
    outcome      INTEGER,
    outcome_key  TEXT,
    PRIMARY KEY (match_id, market, sign, line_key, model_version)
);
""" + PREDICTION_SCHEMA + ABSENCE_SCHEMA + ELO_SCHEMA + V2_FEATURE_SCHEMA + V22_SHADOW_SCHEMA + TEAM_EVENT_SCHEMA + POOL_SETTLEMENT_SCHEMA + POOL_PIT_SCHEMA + LIVE_RADAR_SCHEMA + MATCHBOOK_SCHEMA


class Storage:
    ODDSET_ELO_COUNTRIES = frozenset(
        {"SWE", "NOR", "ENG", "ITA", "ESP", "GER"})
    ODDSET_NO_LINE_KEY = 2_147_483_647

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._bulk = False
        # WP0 (granskningen): WAL = läsare blockeras inte av skrivare (API:t +
        # 25-min-smartpasset kör parallellt); busy_timeout i stället för
        # "database is locked" vid krock.
        self.conn = sqlite3.connect(self.db_path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(_SCHEMA)
        for mig in ("ALTER TABLE oddset_value_log ADD COLUMN book TEXT",
                    "ALTER TABLE oddset_value_log ADD COLUMN tier TEXT DEFAULT 'sharp'",
                    "ALTER TABLE oddset_value_log ADD COLUMN model_version TEXT",
                    "ALTER TABLE oddset_value_log ADD COLUMN git_hash TEXT",
                    "ALTER TABLE oddset_odds ADD COLUMN last_seen_at TEXT",
                    "ALTER TABLE oddset_odds ADD COLUMN available INTEGER NOT NULL DEFAULT 1",
                    # andra ankaret (skuggmätning) — additivt och nullbart:
                    # gamla flaggor får NULL och räknas som "ej mätt", aldrig
                    # som "ankarna var eniga". Ingen bakfyllning är möjlig:
                    # Smarkets-serien börjar 2026-07-24.
                    "ALTER TABLE oddset_value_log ADD COLUMN anchor2_source TEXT",
                    "ALTER TABLE oddset_value_log ADD COLUMN anchor2_fair REAL",
                    "ALTER TABLE oddset_value_log ADD COLUMN anchor2_edge REAL",
                    "ALTER TABLE oddset_value_log ADD COLUMN anchor2_closing_fair REAL",
                    "ALTER TABLE oddset_value_log ADD COLUMN anchor2_note TEXT",
                    # utfalls-facitet (P2, 2026-07-28) — additivt och nullbart:
                    # gamla flaggor settlas i efterhand när resultat finns
                    "ALTER TABLE oddset_value_log ADD COLUMN outcome INTEGER",
                    "ALTER TABLE oddset_value_log ADD COLUMN outcome_key TEXT"):
            try:   # migreringar för befintliga DB:er
                self.conn.execute(mig)
            except sqlite3.OperationalError:
                pass
        # Befintliga prisrader saknar observationsklocka. Första migreringen
        # utgår konservativt från prisets egen tid; nästa lyckade poll flyttar
        # last_seen_at utan att skapa en falsk rörelsepunkt.
        self.conn.execute(
            "UPDATE oddset_odds SET last_seen_at=fetched_at WHERE last_seen_at IS NULL")
        self._commit()

    def close(self) -> None:
        self.conn.close()

    def _commit(self) -> None:
        """Commit per operation — utom inne i bulk(), då committas allt på slutet."""
        if not self._bulk:
            self.conn.commit()

    @contextlib.contextmanager
    def bulk(self):
        """Batcha många skrivningar i EN transaktion (WP0) — commit per rad gav
        ~1 700 commits per football-data-refresh. Rollback vid fel.

        Nestning får inte committa den yttre transaktionen i förtid: V2.2
        skriver ledger, features och shadowrad som en gemensam enhet.
        """
        outermost = not self._bulk
        if outermost:
            self._bulk = True
        try:
            yield
            if outermost:
                self.conn.commit()
        except Exception:
            if outermost:
                self.conn.rollback()
            raise
        finally:
            if outermost:
                self._bulk = False

    def save_snapshot(self, draw: Draw) -> int:
        """Spara hela omgången som ett snapshot. Returnerar antal rader."""
        self.conn.execute(
            "INSERT INTO draws(product, draw_number, state, reg_close_time) "
            "VALUES(?,?,?,?) ON CONFLICT(product, draw_number) "
            "DO UPDATE SET state=excluded.state, reg_close_time=excluded.reg_close_time",
            (draw.product, draw.draw_number, draw.state, draw.reg_close_time),
        )
        rows = 0
        for m in draw.matches:
            for sign, o in m.outcomes.items():
                self.conn.execute(
                    "INSERT INTO snapshots(product, draw_number, event_number, sign, "
                    "odds, start_odds, streck, fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                    (draw.product, draw.draw_number, m.event_number, sign,
                     o.odds, o.start_odds, o.streck, draw.fetched_at),
                )
                rows += 1
        self._commit()
        return rows

    def _latest_values(self, product: str, draw_number: int) -> dict[tuple[int, str], tuple]:
        """Senast lagrade (odds, streck) per (event, sign) för en omgång."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, streck FROM snapshots s "
            "WHERE product=? AND draw_number=? AND fetched_at = ("
            "  SELECT MAX(fetched_at) FROM snapshots WHERE product=s.product "
            "  AND draw_number=s.draw_number AND event_number=s.event_number AND sign=s.sign)",
            (product, draw_number)).fetchall()
        return {(r["event_number"], r["sign"]): (r["odds"], r["streck"]) for r in rows}

    def save_snapshot_if_changed(self, draw: Draw) -> int:
        """Spara bara de utfall som ändrats (odds eller streck) sedan senast.

        Returnerar antal sparade rader (0 = inget nytt). Håller DB:n liten
        även vid tät pollning."""
        prev = self._latest_values(draw.product, draw.draw_number)
        self.conn.execute(
            "INSERT INTO draws(product, draw_number, state, reg_close_time) "
            "VALUES(?,?,?,?) ON CONFLICT(product, draw_number) "
            "DO UPDATE SET state=excluded.state, reg_close_time=excluded.reg_close_time",
            (draw.product, draw.draw_number, draw.state, draw.reg_close_time),
        )
        rows = 0
        for m in draw.matches:
            for sign, o in m.outcomes.items():
                if prev.get((m.event_number, sign)) == (o.odds, o.streck):
                    continue  # oförändrat -> hoppa
                self.conn.execute(
                    "INSERT INTO snapshots(product, draw_number, event_number, sign, "
                    "odds, start_odds, streck, fetched_at) VALUES(?,?,?,?,?,?,?,?)",
                    (draw.product, draw.draw_number, m.event_number, sign,
                     o.odds, o.start_odds, o.streck, draw.fetched_at),
                )
                rows += 1
        self._commit()
        return rows

    def history(self, product: str, draw_number: int,
                event_number: int, sign: Optional[str] = None) -> list[dict]:
        q = ("SELECT event_number, sign, odds, streck, fetched_at FROM snapshots "
             "WHERE product=? AND draw_number=? AND event_number=?")
        args: list = [product, draw_number, event_number]
        if sign:
            q += " AND sign=?"
            args.append(sign)
        q += " ORDER BY fetched_at"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    # --- nyckel/värde-meta ---
    def meta_get(self, key: str) -> Optional[str]:
        r = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self._commit()

    def meta_delete(self, key: str) -> None:
        self.conn.execute("DELETE FROM meta WHERE key=?", (key,))
        self._commit()

    # --- sharp-odds (cache från the-odds-api) ---
    def save_sharp(self, product: str, draw_number: int, hits: list[dict]) -> int:
        """Spara/uppdatera sharp-odds per match. `hits` är poster med
        event_number, bookmaker, odds{1,X,2}, confidence, matched."""
        n = 0
        for h in hits:
            o = h.get("odds") or {}
            self.conn.execute(
                "INSERT INTO sharp_odds(product, draw_number, event_number, bookmaker, "
                "one, x, two, confidence, matched, fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(product, draw_number, event_number) DO UPDATE SET "
                "bookmaker=excluded.bookmaker, one=excluded.one, x=excluded.x, "
                "two=excluded.two, confidence=excluded.confidence, "
                "matched=excluded.matched, fetched_at=excluded.fetched_at",
                (product, draw_number, h["event_number"], h.get("bookmaker"),
                 o.get("1"), o.get("X"), o.get("2"), h.get("confidence"),
                 h.get("matched"), h.get("fetched_at")),
            )
            n += 1
        self._commit()
        return n

    def save_sharp_snapshot(self, product: str, draw_number: int, hits: dict[int, dict],
                            fetched_at: str) -> int:
        """Lägg till en tidsserie-punkt för sharp-odds (Pinnacle) per utfall, men
        bara om oddset ändrats sedan senaste punkten (håller serien liten)."""
        prev = {}
        for r in self.conn.execute(
            "SELECT event_number, sign, odds FROM sharp_snapshots s WHERE product=? AND draw_number=? "
            "AND fetched_at=(SELECT MAX(fetched_at) FROM sharp_snapshots WHERE product=s.product "
            "AND draw_number=s.draw_number AND event_number=s.event_number AND sign=s.sign)",
            (product, draw_number)).fetchall():
            prev[(r["event_number"], r["sign"])] = r["odds"]
        n = 0
        for ev, h in hits.items():
            o = h.get("odds") or {}
            for sign in ("1", "X", "2"):
                val = o.get(sign)
                if val is None or prev.get((ev, sign)) == val:
                    continue
                self.conn.execute(
                    "INSERT INTO sharp_snapshots(product, draw_number, event_number, sign, odds, fetched_at) "
                    "VALUES(?,?,?,?,?,?)", (product, draw_number, ev, sign, val, fetched_at))
                n += 1
        self._commit()
        return n

    def sharp_movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"]); a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["odds"], "first_t": r["fetched_at"],
                          "last": r["odds"], "last_t": r["fetched_at"], "n": 1,
                          "min": r["odds"], "max": r["odds"]}
            else:
                a["last"], a["last_t"], a["n"] = r["odds"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["odds"]), max(a["max"], r["odds"])
        return agg

    def sharp_history_all(self, product: str, draw_number: int) -> list[dict]:
        """Hela sharp-serien för en omgång (alla matcher/tecken, tidsordnad) —
        underlag för steam-beräkningen (devigade skift över tidsfönster)."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        return [dict(r) for r in rows]

    def sharp_history(self, product: str, draw_number: int, event_number: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT sign, odds, fetched_at FROM sharp_snapshots WHERE product=? AND draw_number=? "
            "AND event_number=? ORDER BY fetched_at", (product, draw_number, event_number)).fetchall()
        return [dict(r) for r in rows]

    def get_sharp(self, product: str, draw_number: int) -> dict[int, dict]:
        rows = self.conn.execute(
            "SELECT event_number, bookmaker, one, x, two, confidence, matched, fetched_at "
            "FROM sharp_odds WHERE product=? AND draw_number=?",
            (product, draw_number)).fetchall()
        return {r["event_number"]: {
            "odds": {"1": r["one"], "X": r["x"], "2": r["two"]},
            "bookmaker": r["bookmaker"], "confidence": r["confidence"],
            "matched": r["matched"], "fetched_at": r["fetched_at"]}
            for r in rows}

    def movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Per (event, sign): odds vid första vs senaste snapshot, antal punkter,
        samt min/max. Underlag för rörelsesignalen (stärks/försvagas över tid)."""
        rows = self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"])
            a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["odds"], "first_t": r["fetched_at"],
                          "last": r["odds"], "last_t": r["fetched_at"],
                          "n": 1, "min": r["odds"], "max": r["odds"]}
            else:
                a["last"], a["last_t"], a["n"] = r["odds"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["odds"]), max(a["max"], r["odds"])
        return agg

    def streck_movement(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Per (event, sign): folkets streck vid första vs senaste snapshot.
        Underlag för att flagga matcher där folket svängt markant."""
        rows = self.conn.execute(
            "SELECT event_number, sign, streck, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND streck IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall()
        agg: dict[tuple[int, str], dict] = {}
        for r in rows:
            k = (r["event_number"], r["sign"]); a = agg.get(k)
            if a is None:
                agg[k] = {"first": r["streck"], "first_t": r["fetched_at"],
                          "last": r["streck"], "last_t": r["fetched_at"],
                          "n": 1, "min": r["streck"], "max": r["streck"]}
            else:
                a["last"], a["last_t"], a["n"] = r["streck"], r["fetched_at"], a["n"] + 1
                a["min"], a["max"] = min(a["min"], r["streck"]), max(a["max"], r["streck"])
        return agg

    def odds_series(self, product: str, draw_number: int) -> dict[tuple[int, str], dict]:
        """Hela oddsserien per (event, sign) för både SvS och Pinnacle —
        underlag för rörelse-tooltipen (alla mätpunkter + min/max)."""
        out: dict[tuple[int, str], dict] = {}
        for r in self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall():
            out.setdefault((r["event_number"], r["sign"]),
                           {"svs": [], "pinnacle": []})["svs"].append(
                {"t": r["fetched_at"], "odds": r["odds"]})
        for r in self.conn.execute(
            "SELECT event_number, sign, odds, fetched_at FROM sharp_snapshots "
            "WHERE product=? AND draw_number=? AND odds IS NOT NULL ORDER BY fetched_at",
            (product, draw_number)).fetchall():
            out.setdefault((r["event_number"], r["sign"]),
                           {"svs": [], "pinnacle": []})["pinnacle"].append(
                {"t": r["fetched_at"], "odds": r["odds"]})
        return out

    # --- CLV-facit: flaggade värdetecken vs devigad stängningslinje ---
    def log_value_flag(self, r: dict, at: str) -> None:
        """first/best per selektion: insert vid ny flagga, uppdatera best om
        värde-kvoten är bättre än tidigare bästa."""
        cur = self.conn.execute(
            "SELECT best_ratio FROM value_log WHERE product=? AND draw_number=? "
            "AND event_number=? AND sign=?",
            (r["product"], r["draw_number"], r["event_number"], r["sign"])).fetchone()
        if cur is None:
            self.conn.execute(
                "INSERT INTO value_log(product, draw_number, event_number, sign, "
                "description, match_start, flag_type, first_at, first_odds, first_prob, "
                "prob_src, first_streck, first_ratio, best_ratio, best_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["product"], r["draw_number"], r["event_number"], r["sign"],
                 r.get("description"), r.get("match_start"), r.get("flag_type"),
                 at, r.get("odds"), r.get("prob"), r.get("prob_src"),
                 r.get("streck"), r.get("ratio"), r.get("ratio"), at))
        elif (r.get("ratio") or 0) > (cur["best_ratio"] or 0):
            self.conn.execute(
                "UPDATE value_log SET best_ratio=?, best_at=? WHERE product=? "
                "AND draw_number=? AND event_number=? AND sign=?",
                (r.get("ratio"), at, r["product"], r["draw_number"],
                 r["event_number"], r["sign"]))
        self._commit()

    def unresolved_closings(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM value_log WHERE closing_prob IS NULL AND closing_note IS NULL "
            "AND match_start IS NOT NULL").fetchall()
        return [dict(r) for r in rows]

    def set_closing(self, product: str, draw_number: int, event_number: int, sign: str,
                    prob: Optional[float] = None, odds: Optional[float] = None,
                    note: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE value_log SET closing_prob=?, closing_odds=?, closing_note=? "
            "WHERE product=? AND draw_number=? AND event_number=? AND sign=?",
            (prob, odds, note, product, draw_number, event_number, sign))
        self._commit()

    def draws_missing_outcome(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT DISTINCT product, draw_number FROM value_log WHERE outcome IS NULL").fetchall()
        return [(r["product"], r["draw_number"]) for r in rows]

    def set_outcomes(self, product: str, draw_number: int, facit: dict[int, str]) -> int:
        n = 0
        for r in self.conn.execute(
                "SELECT event_number, sign FROM value_log WHERE product=? AND draw_number=? "
                "AND outcome IS NULL", (product, draw_number)).fetchall():
            f = facit.get(r["event_number"])
            if f:
                self.conn.execute(
                    "UPDATE value_log SET outcome=? WHERE product=? AND draw_number=? "
                    "AND event_number=? AND sign=?",
                    (1 if r["sign"] == f else 0, product, draw_number,
                     r["event_number"], r["sign"]))
                n += 1
        self._commit()
        return n

    def clv_rows(self, product: Optional[str] = None, limit: int = 300) -> list[dict]:
        q, args = "SELECT * FROM value_log", []
        if product:
            q += " WHERE product=?"
            args.append(product)
        q += " ORDER BY first_at DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def last_snapshot(self) -> Optional[str]:
        r = self.conn.execute("SELECT MAX(fetched_at) AS m FROM snapshots").fetchone()
        return r["m"]

    def snapshot_count(self) -> int:
        r = self.conn.execute(
            "SELECT COUNT(DISTINCT fetched_at) AS c FROM snapshots").fetchone()
        return r["c"]

    def snapshot_times(self, product: str, draw_number: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT fetched_at FROM snapshots WHERE product=? AND draw_number=? "
            "ORDER BY fetched_at", (product, draw_number)).fetchall()
        return [r["fetched_at"] for r in rows]

    # ---------------- Oddset (enskilda matcher, app/oddset.py) ----------------

    ODDSET_SIGNS = {"1x2": ("1", "X", "2"), "ah": ("H", "A"), "ou": ("O", "U"),
                    "cor": ("O", "U")}

    @staticmethod
    def _line_key(line: float) -> int:
        return int(round(float(line) * 1000))

    def oddset_save_sharp_alt(self, match_id: str, market: str,
                              pairs: list[dict], at: str) -> int:
        """Sharpens ALLA linjer för en parmarknad efter ett LYCKAT svar.
        pairs = [{'a','b','line'}] där a/b följer ODDSET_SIGNS[market].
        Oförändrat pris flyttar last_seen_at utan historikpunkt; linjer som
        försvunnit ur svaret markeras unavailable (plockade/suspenderade)."""
        signs = self.ODDSET_SIGNS.get(market, ())
        if len(signs) != 2:
            return 0
        prev: dict[tuple, dict] = {}
        for r in self.conn.execute(
                "SELECT id, line, sign, odds, available FROM oddset_sharp_alt s "
                "WHERE match_id=? AND market=? AND fetched_at=("
                " SELECT MAX(fetched_at) FROM oddset_sharp_alt WHERE match_id=s.match_id"
                " AND market=s.market AND line=s.line AND sign=s.sign)",
                (match_id, market)):
            prev[(self._line_key(r["line"]), r["sign"])] = dict(r)
        n = 0
        seen: set[tuple] = set()
        for p in pairs:
            if p.get("line") is None:
                continue
            for sign, odds in ((signs[0], p.get("a")), (signs[1], p.get("b"))):
                if odds is None:
                    continue
                key = (self._line_key(p["line"]), sign)
                seen.add(key)
                old = prev.get(key)
                if old and old["odds"] == odds:
                    # Monotonispärr, samma skäl som i oddset_odds: CDN-Age gör
                    # observationstiden bakåtdaterad och den får inte backa.
                    self.conn.execute(
                        "UPDATE oddset_sharp_alt "
                        "SET last_seen_at=MAX(last_seen_at, ?), available=1 "
                        "WHERE id=?", (at, old["id"]))
                    continue
                observed = at
                if old and old.get("last_seen_at") and observed < old["last_seen_at"]:
                    observed = old["last_seen_at"]
                self.conn.execute(
                    "INSERT INTO oddset_sharp_alt(match_id, market, line, sign, "
                    "odds, fetched_at, last_seen_at) VALUES(?,?,?,?,?,?,?)",
                    (match_id, market, p["line"], sign, odds, observed, observed))
                n += 1
        for key, old in prev.items():
            if key not in seen and old["available"]:
                self.conn.execute(
                    "UPDATE oddset_sharp_alt SET available=0 WHERE id=?",
                    (old["id"],))
        self._commit()
        return n

    def oddset_sharp_alt_latest(self, ids: list[str]) -> dict[str, dict]:
        """{match_id: {market: {line_key: {sign: odds, 'line', 'last_seen_at',
        'available'}}}} — senaste raden per (match, marknad, linje, tecken)."""
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        out: dict[str, dict] = {}
        for r in self.conn.execute(
                f"SELECT * FROM oddset_sharp_alt s WHERE match_id IN ({marks}) "
                "AND fetched_at=(SELECT MAX(fetched_at) FROM oddset_sharp_alt "
                "WHERE match_id=s.match_id AND market=s.market AND line=s.line "
                "AND sign=s.sign)", ids):
            slot = out.setdefault(r["match_id"], {}) \
                .setdefault(r["market"], {}) \
                .setdefault(self._line_key(r["line"]), {"line": r["line"]})
            slot[r["sign"]] = r["odds"]
            prev_seen = slot.get("last_seen_at")
            if prev_seen is None or r["last_seen_at"] < prev_seen:
                slot["last_seen_at"] = r["last_seen_at"]   # äldsta av paren styr
            slot["available"] = min(slot.get("available", 1), r["available"])
        return out

    def oddset_sharp_alt_before(self, match_id: str, market: str,
                                before_iso: str) -> list[dict]:
        """Alt-linje-historik före en tidpunkt, i tidsordning (för stängning)."""
        return [dict(r) for r in self.conn.execute(
            "SELECT sign, odds, line, fetched_at, last_seen_at, available "
            "FROM oddset_sharp_alt WHERE match_id=? AND market=? AND fetched_at<? "
            "AND odds IS NOT NULL ORDER BY fetched_at",
            (match_id, market, before_iso))]

    def oddset_upsert_match(self, m: dict, prefer_names: bool = False) -> None:
        """Inkrementell upsert: None skriver aldrig över. prefer_names=True låter
        källans namn (Kambis svenska) ersätta befintliga visningsnamn."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.conn.execute(
            "INSERT INTO oddset_matches(id, league, home, away, start, pinnacle_id, "
            "kambi_id, status, updated_at) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            + ("home=excluded.home, away=excluded.away, "
               if prefer_names else
               "home=COALESCE(oddset_matches.home, excluded.home), "
               "away=COALESCE(oddset_matches.away, excluded.away), ")
            + "start=COALESCE(excluded.start, oddset_matches.start), "
              "pinnacle_id=COALESCE(oddset_matches.pinnacle_id, excluded.pinnacle_id), "
              "kambi_id=COALESCE(oddset_matches.kambi_id, excluded.kambi_id), "
              "status=COALESCE(excluded.status, oddset_matches.status), "
              "updated_at=excluded.updated_at",
            (m["id"], m["league"], m.get("home"), m.get("away"), m.get("start"),
             m.get("pinnacle_id"), m.get("kambi_id"), m.get("status"), now))
        self._commit()

    def oddset_matches(self, since: Optional[str] = None,
                       until: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_matches WHERE 1=1", []
        if since:
            q += " AND start >= ?"
            args.append(since)
        if until:
            q += " AND start <= ?"
            args.append(until)
        q += " ORDER BY start"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def oddset_match(self, match_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM oddset_matches WHERE id=?", (match_id,)).fetchone()
        return dict(row) if row else None

    def oddset_match_by_source_id(
            self, id_field: str, source_id) -> Optional[dict]:
        """Globalt one-to-one-uppslag; får inte begränsas av UI-tidsfönstret."""
        if id_field not in {"pinnacle_id", "kambi_id"}:
            raise ValueError(f"otillåtet käll-id-fält: {id_field}")
        row = self.conn.execute(
            f"SELECT * FROM oddset_matches WHERE {id_field}=?",
            (str(source_id),)).fetchone()
        return dict(row) if row else None

    def oddset_identity_conflicts(
            self, match_ids: list[str]) -> dict[str, list[str]]:
        """Härled identitetskollisioner som måste karantänsättas i läs-API:t.

        Detta är medvetet en ren läsning: även innan en sanering hunnit köras
        får en förorenad match aldrig skapa värdekort, modellfacit eller
        prediktionscaptures. Tre oberoende invariants kontrolleras:
        självbärande pin:/svs:-id, unikt externt id och två olika priser från
        samma källa/marknad/tecken vid exakt samma observationstid.
        """
        if not match_ids:
            return {}
        wanted = set(match_ids)
        marks = ",".join("?" for _ in match_ids)
        conflicts: dict[str, list[str]] = {}

        def add(mid: str, reason: str) -> None:
            if mid in wanted and reason not in conflicts.setdefault(mid, []):
                conflicts[mid].append(reason)

        matches = [dict(row) for row in self.conn.execute(
            f"SELECT id, pinnacle_id, kambi_id FROM oddset_matches "
            f"WHERE id IN ({marks})", match_ids)]
        for match in matches:
            mid = match["id"]
            if (mid.startswith("pin:") and match.get("pinnacle_id") is not None
                    and mid[4:] != str(match["pinnacle_id"])):
                add(mid, "Pinnacle-id stämmer inte med matchens canonical-id")
            if (mid.startswith("svs:") and match.get("kambi_id") is not None
                    and mid[4:] != str(match["kambi_id"])):
                add(mid, "SvS-id stämmer inte med matchens canonical-id")

        for field, label in (("pinnacle_id", "Pinnacle"),
                             ("kambi_id", "SvS")):
            rows = self.conn.execute(
                f"SELECT {field}, GROUP_CONCAT(id) AS ids, COUNT(*) AS n "
                f"FROM oddset_matches WHERE {field} IS NOT NULL "
                f"GROUP BY {field} HAVING COUNT(*)>1").fetchall()
            for row in rows:
                for mid in str(row["ids"]).split(","):
                    add(mid, f"{label}-id delas av flera matcher")

        rows = self.conn.execute(
            f"SELECT match_id, source, market, sign, fetched_at, "
            f"COUNT(DISTINCT CAST(odds AS TEXT) || '|' || "
            f"COALESCE(CAST(line AS TEXT), '')) AS variants "
            f"FROM oddset_odds WHERE match_id IN ({marks}) "
            f"GROUP BY match_id, source, market, sign, fetched_at "
            f"HAVING variants>1", match_ids).fetchall()
        for row in rows:
            add(row["match_id"],
                f"{row['source']} har flera priser för samma matchögonblick")
        return conflicts

    def _oddset_latest_values(self, match_id: str, source: str,
                              market: str) -> dict[str, dict]:
        rows = self.conn.execute(
            "SELECT id, sign, odds, line, fetched_at, last_seen_at, available "
            "FROM oddset_odds s WHERE match_id=? AND source=? AND market=? "
            "AND id=(SELECT id FROM oddset_odds WHERE match_id=s.match_id "
            "AND source=s.source AND market=s.market AND sign=s.sign "
            "ORDER BY fetched_at DESC, id DESC LIMIT 1)",
            (match_id, source, market)).fetchall()
        return {r["sign"]: dict(r) for r in rows}

    def oddset_save_market(self, match_id: str, source: str, market: str,
                           rows: dict, fetched_at: str) -> int:
        """Registrera ett lyckat marknadssvar.

        rows = {sign: {'odds': float, 'line': float|None}}. Ett oförändrat pris
        flyttar last_seen_at utan ny historikpunkt. Saknade tecken markeras som
        unavailable; metoden ska därför bara anropas när källsvaret lyckades.
        """
        prev = self._oddset_latest_values(match_id, source, market)
        n = 0
        for sign in self.ODDSET_SIGNS.get(market, ()):
            val = rows.get(sign)
            if not val or val.get("odds") is None:
                if sign in prev:
                    self.conn.execute(
                        "UPDATE oddset_odds SET available=0 WHERE id=?",
                        (prev[sign]["id"],))
                continue
            cur = (val.get("odds"), val.get("line"))
            old = prev.get(sign)
            if old and (old["odds"], old["line"]) == cur:
                # MONOTONISPÄRR (2026-07-25): observationstiden är sedan
                # CDN-fixen bakåtdaterad med HTTP Age, och olika CDN-noder kan
                # svara med olika ålder. Utan MAX() kunde ett senare svar med
                # större Age flytta färskhetsklockan BAKÅT — då blir raden
                # osynlig för "senaste"-sorteringen, nästa varv jämför mot fel
                # föregående rad och skriver samma pris igen som en falsk
                # rörelsepunkt. Klockan får bara gå framåt.
                self.conn.execute(
                    "UPDATE oddset_odds SET last_seen_at=MAX(last_seen_at, ?), "
                    "available=1 WHERE id=?",
                    (fetched_at, old["id"]))
                continue
            # FÖRÅLDRAT CACHEOBJEKT: har vi redan bekräftat en observation
            # SENARE än det här svarets ursprungstid bär svaret ingen ny
            # information om nuvarande pris — det är ett gammalt pris vi ser
            # sent. Att skriva det bakåtdaterat skapar en rad före en tidigare
            # observation; att skriva det med nutid vore en lögn om färskhet.
            # Hoppa över det helt.
            if old and old.get("last_seen_at") and fetched_at < old["last_seen_at"]:
                continue
            self.conn.execute(
                "INSERT INTO oddset_odds(match_id, source, market, sign, line, odds, "
                "fetched_at, last_seen_at, available) VALUES(?,?,?,?,?,?,?,?,1)",
                (match_id, source, market, sign, val.get("line"), val.get("odds"),
                 fetched_at, fetched_at))
            n += 1
        self._commit()
        return n

    def oddset_mark_market_unavailable(self, match_id: str, source: str,
                                       market: str) -> None:
        """Markera senaste raderna som plockade/suspenderade efter ett lyckat svar."""
        prev = self._oddset_latest_values(match_id, source, market)
        if prev:
            self.conn.executemany(
                "UPDATE oddset_odds SET available=0 WHERE id=?",
                [(r["id"],) for r in prev.values()])
            self._commit()

    def oddset_save_odds(self, match_id: str, source: str,
                         odds: dict, fetched_at: str) -> int:
        """Bekvämlighet för 1X2."""
        rows = {s: {"odds": odds.get(s), "line": None} for s in ("1", "X", "2")}
        return self.oddset_save_market(match_id, source, "1x2", rows, fetched_at)

    def oddset_save_matchbook_liquidity(self, match_id: str, liquidity: dict,
                                        seen_at: str) -> int:
        """Matchbooks tillgängliga back-likviditet (EUR) per selektion — ren
        skuggserie (se MATCHBOOK_SCHEMA). Append/upsert med monotonisk seen_at:
        nytt belopp = ny rad, oförändrat belopp flyttar senaste radens seen_at
        framåt med MAX(), och ett svar äldre än senaste observationen bär ingen
        ny information och skrivs aldrig (observationstidsregeln p.4)."""
        n = 0
        for sign in ("1", "X", "2"):
            value = liquidity.get(sign)
            if value is None:
                continue
            prev = self.conn.execute(
                "SELECT id, available, seen_at FROM oddset_matchbook_liquidity "
                "WHERE match_id=? AND sign=? ORDER BY seen_at DESC, id DESC "
                "LIMIT 1", (match_id, sign)).fetchone()
            if prev and seen_at < prev["seen_at"]:
                continue      # föråldrat svar — klockan går bara framåt
            if prev and prev["available"] == value:
                self.conn.execute(
                    "UPDATE oddset_matchbook_liquidity "
                    "SET seen_at=MAX(seen_at, ?) WHERE id=?",
                    (seen_at, prev["id"]))
                continue
            self.conn.execute(
                "INSERT INTO oddset_matchbook_liquidity"
                "(match_id, sign, available, seen_at) VALUES(?,?,?,?)",
                (match_id, sign, value, seen_at))
            n += 1
        self._commit()
        return n

    @staticmethod
    def _oddset_ids_clause(ids: list[str]) -> tuple[str, list]:
        if not ids:
            return "1=0", []
        return f"match_id IN ({','.join('?' * len(ids))})", list(ids)

    def oddset_latest(self, ids: list[str]) -> dict[str, dict]:
        """Senaste pris + observationsstatus per marknad.

        fetched_at är senaste prisförändringen, last_seen_at den äldsta senaste
        bekräftelsen bland marknadens obligatoriska tecken. derived viks in
        under Pinnacle men vinner bara när den direkta 1X2-marknaden inte är
        tillgänglig.
        """
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT id, match_id, source, market, sign, odds, line, fetched_at, "
            f"last_seen_at, available FROM oddset_odds s WHERE {where} AND id=("
            f"SELECT id FROM oddset_odds WHERE match_id=s.match_id "
            f"AND source=s.source AND market=s.market AND sign=s.sign "
            f"ORDER BY fetched_at DESC, id DESC LIMIT 1)", args).fetchall()
        raw: dict[str, dict] = {}
        for r in rows:
            m = raw.setdefault(r["match_id"], {}).setdefault(r["source"], {}) \
                   .setdefault(r["market"], {"_selections": {}})
            m[r["sign"]] = r["odds"]
            if r["line"] is not None:
                m["line"] = r["line"]
            m["_selections"][r["sign"]] = {
                "available": bool(r["available"]),
                "last_seen_at": r["last_seen_at"],
                "fetched_at": r["fetched_at"],
                "line": r["line"],
            }

        def finalize(market: str, m: dict) -> dict:
            signs = self.ODDSET_SIGNS.get(market, ())
            states = m.pop("_selections", {})
            complete = all(s in states for s in signs)
            lines = {states[s]["line"] for s in signs if s in states}
            line_ok = market == "1x2" or (complete and len(lines) == 1 and None not in lines)
            m["available"] = bool(
                complete and line_ok and all(states[s]["available"] for s in signs))
            seen = [states[s]["last_seen_at"] for s in signs
                    if s in states and states[s]["last_seen_at"]]
            changed = [states[s]["fetched_at"] for s in signs
                       if s in states and states[s]["fetched_at"]]
            m["last_seen_at"] = min(seen) if seen else None
            m["fetched_at"] = max(changed) if changed else None
            m["selections"] = states
            return m

        for sources in raw.values():
            for markets in sources.values():
                for market, m in list(markets.items()):
                    markets[market] = finalize(market, m)

        out: dict[str, dict] = {}
        for mid, sources in raw.items():
            target = out.setdefault(mid, {})
            for source, markets in sources.items():
                if source == "derived":
                    continue
                target[source] = markets
            derived = sources.get("derived", {}).get("1x2")
            if derived:
                direct = target.setdefault("pinnacle", {}).get("1x2")
                if direct is None or (not direct.get("available") and derived.get("available")):
                    target["pinnacle"]["1x2"] = {**derived, "derived": True}
        return out

    def oddset_record_source_health(self, source: str, league: str, scope: str,
                                    checked_at: str, ok: bool, event_count: int = 0,
                                    error: Optional[str] = None) -> None:
        self.conn.execute(
            "INSERT INTO oddset_source_health(source, league, scope, checked_at, ok, "
            "event_count, error) VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,league,scope) "
            "DO UPDATE SET checked_at=excluded.checked_at, ok=excluded.ok, "
            "event_count=excluded.event_count, error=excluded.error",
            (source, league, scope, checked_at, int(ok), event_count,
             (error or "")[:240] or None))
        self._commit()

    def oddset_source_health(self) -> list[dict]:
        return [dict(r) | {"ok": bool(r["ok"])} for r in self.conn.execute(
            "SELECT source, league, scope, checked_at, ok, event_count, error "
            "FROM oddset_source_health ORDER BY source, league, scope").fetchall()]

    def oddset_save_live_capture(self, capture: dict) -> int:
        """Spara en observerad livebild idempotent; inga härledda signaler."""
        required = ("event_id", "captured_at", "capture_version", "league",
                    "home", "away", "status", "home_score", "away_score")
        if any(capture.get(key) is None for key in required):
            raise ValueError("live-capture saknar obligatoriskt fält")
        columns = (
            "event_id", "captured_at", "capture_version", "league",
            "tournament", "home", "away", "start_at", "status", "minute",
            "home_score", "away_score", "xg_home", "xg_away",
            "big_chances_home", "big_chances_away", "shots_home",
            "shots_away", "shots_on_home", "shots_on_away",
            "shots_inside_home", "shots_inside_away", "touches_box_home",
            "touches_box_away", "corners_home", "corners_away",
        )
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO oddset_live_capture({','.join(columns)}) "
            f"VALUES({','.join('?' for _ in columns)})",
            tuple(capture.get(key) for key in columns))
        self._commit()
        return cur.rowcount

    LIVE_FOTMOB_COLUMNS = (
        "fotmob_id", "captured_at", "capture_version", "league", "tournament",
        "home", "away", "start_at", "minute", "home_score", "away_score",
        "xg_home", "xg_away", "xgot_home", "xgot_away", "xg_open_home",
        "xg_open_away", "big_chances_home", "big_chances_away", "shots_home",
        "shots_away", "shots_on_home", "shots_on_away", "shots_inside_home",
        "shots_inside_away",
    )

    def live_fotmob_save(self, capture: dict) -> int:
        """Append-once per (match, observationstid, version) — egen tabell så
        FotMobs xG aldrig kan blandas med Sofascores."""
        cols = self.LIVE_FOTMOB_COLUMNS
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO oddset_live_fotmob({','.join(cols)}) "
            f"VALUES({','.join('?' for _ in cols)})",
            tuple(capture.get(key) for key in cols))
        self._commit()
        return cur.rowcount

    def live_fotmob_captures(self, since: Optional[str] = None,
                             capture_version: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM oddset_live_fotmob WHERE 1=1"
        args: list = []
        if since:
            query += " AND captured_at>=?"
            args.append(since)
        if capture_version:
            query += " AND capture_version=?"
            args.append(capture_version)
        query += " ORDER BY fotmob_id, captured_at"
        return [dict(row) for row in self.conn.execute(query, args)]

    def oddset_live_captures(
            self, since: Optional[str] = None,
            capture_version: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM oddset_live_capture WHERE 1=1"
        args: list = []
        if since:
            query += " AND captured_at>=?"
            args.append(since)
        if capture_version:
            query += " AND capture_version=?"
            args.append(capture_version)
        query += " ORDER BY event_id, captured_at"
        return [dict(row) for row in self.conn.execute(query, args).fetchall()]

    LIVE_SETTLEMENT_COLUMNS = (
        "provider", "event_id", "captured_at", "capture_version", "league",
        "minute", "score_diff", "signal", "signal_type", "signal_version",
        "outcome_15min", "outcome_more_before_ft", "censored_15min",
        "censored_ft", "settled_at",
    )

    def live_settlement_save(self, row: dict) -> int:
        """Append-once per ögonblick — en settlad rad skrivs aldrig om."""
        cols = self.LIVE_SETTLEMENT_COLUMNS
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO oddset_live_moment_settlement"
            f"({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
            tuple(row.get(key) for key in cols))
        self._commit()
        return cur.rowcount

    def live_settlement_keys(self) -> set[tuple]:
        """Naturliga nycklar för redan settlade ögonblick (aldrig omskrivning)."""
        return {(r["provider"], int(r["event_id"]), r["captured_at"],
                 r["capture_version"])
                for r in self.conn.execute(
                    "SELECT provider, event_id, captured_at, capture_version "
                    "FROM oddset_live_moment_settlement")}

    def live_settlement_rows(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM oddset_live_moment_settlement "
            "ORDER BY provider, event_id, captured_at")]

    def oddset_movement(self, ids: list[str]) -> dict[str, dict]:
        """Rörelse (first/last/min/max/n + punktserie) för alla givna matcher i en
        fråga. -> {match_id: {source: {market: {sign: agg}}}}. 'derived' → 'pinnacle'.
        Punkterna bär linjen (AH/ÖU/hörnor) — first_l/last_l visar linjeflytt."""
        where, args = self._oddset_ids_clause(ids)
        rows = self.conn.execute(
            f"SELECT match_id, source, market, sign, odds, line, fetched_at "
            f"FROM oddset_odds "
            f"WHERE {where} AND odds IS NOT NULL ORDER BY fetched_at", args).fetchall()
        out: dict[str, dict] = {}
        for r in rows:
            src = "pinnacle" if r["source"] == "derived" else r["source"]
            agg = out.setdefault(r["match_id"], {}).setdefault(src, {}) \
                     .setdefault(r["market"], {})
            a = agg.get(r["sign"])
            o, t, ln = r["odds"], r["fetched_at"], r["line"]
            if a is None:
                agg[r["sign"]] = {"first": o, "last": o, "min": o, "max": o, "n": 1,
                                  "first_t": t, "last_t": t, "first_l": ln, "last_l": ln,
                                  "pts": [{"t": t, "o": o, "l": ln}]}
            else:
                a["last"], a["last_t"], a["n"] = o, t, a["n"] + 1
                a["last_l"] = ln
                a["min"], a["max"] = min(a["min"], o), max(a["max"], o)
                a["pts"].append({"t": t, "o": o, "l": ln})
        return out

    def oddset_save_result(self, r: dict) -> None:
        """COALESCE-upsert: xG från Sofascore fyller på football-data-rader
        (samma PK tack vare normaliserade namn) utan att skriva över mål."""
        self.conn.execute(
            "INSERT INTO oddset_results(league, date, home, away, home_raw, away_raw, "
            "hg, ag, xg_h, xg_a, cor_h, cor_a, source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(league, date, home, away) DO UPDATE SET "
            "hg=COALESCE(oddset_results.hg, excluded.hg), "
            "ag=COALESCE(oddset_results.ag, excluded.ag), "
            "xg_h=COALESCE(excluded.xg_h, oddset_results.xg_h), "
            "xg_a=COALESCE(excluded.xg_a, oddset_results.xg_a), "
            "cor_h=COALESCE(excluded.cor_h, oddset_results.cor_h), "
            "cor_a=COALESCE(excluded.cor_a, oddset_results.cor_a)",
            (r["league"], r["date"], r["home"], r["away"], r.get("home_raw"),
             r.get("away_raw"), r.get("hg"), r.get("ag"), r.get("xg_h"),
             r.get("xg_a"), r.get("cor_h"), r.get("cor_a"), r.get("source")))
        self._commit()

    def oddset_results(self, league: str, since: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_results WHERE league=? AND hg IS NOT NULL", [league]
        if since:
            q += " AND date >= ?"
            args.append(since)
        q += " ORDER BY date"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def meta_like(self, prefix: str) -> list[tuple[str, str]]:
        return [(r["key"], r["value"]) for r in self.conn.execute(
            "SELECT key, value FROM meta WHERE key LIKE ?", (prefix + "%",)).fetchall()]

    def oddset_log_flag(self, r: dict) -> None:
        """First/best per (match, marknad, tecken, lina, signalversion).

        First skrivs aldrig över. Lina och version ingår i identiteten så en
        edge på ny lina eller under ny algoritmregim inte blandas med den gamla.
        model_version = semantiskt signal-fingeravtryck (facitet delas på den);
        git_hash = exakt kodversion vid first (reproducerbarhet). Granskningen
        punkt 5: docs-commits får inte fragmentera facitet.

        anchor2_* är skuggmätning av det ANDRA ankaret vid first — aldrig
        omskrivet (samma regel som first_fair: vi mäter läget när flaggan
        föddes, inte det bästa läget i efterhand)."""
        line = r.get("line")
        line_key = (self.ODDSET_NO_LINE_KEY if line is None
                    else int(round(float(line) * 1000)))
        version = r.get("model_version") or "legacy"
        self.conn.execute(
            "INSERT INTO oddset_value_log(match_id, market, sign, line, line_key, league, "
            "description, match_start, first_at, first_odds, first_fair, first_edge, "
            "best_edge, best_at, book, tier, model_version, git_hash, "
            "anchor2_source, anchor2_fair, anchor2_edge, anchor2_note) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(match_id, market, sign, line_key, model_version) DO UPDATE SET "
            "best_edge=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_edge ELSE oddset_value_log.best_edge END, "
            "best_at=CASE WHEN excluded.best_edge > oddset_value_log.best_edge "
            "THEN excluded.best_at ELSE oddset_value_log.best_at END",
            (r["match_id"], r["market"], r["sign"], line, line_key, r.get("league"),
             r.get("description"), r.get("match_start"), r["at"], r["odds"],
             r["fair"], r["edge"], r["edge"], r["at"], r.get("book"),
             r.get("tier", "sharp"), version, r.get("git_hash"),
             r.get("anchor2_source"), r.get("anchor2_fair"),
             r.get("anchor2_edge"), r.get("anchor2_note")))
        self._commit()

    def oddset_unresolved_closings(self, now_iso: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log WHERE closing_fair IS NULL "
            "AND closing_note IS NULL AND match_start IS NOT NULL AND match_start < ?",
            (now_iso,)).fetchall()]

    def oddset_unsettled_outcomes(self, now_iso: str,
                                  max_age_days: int = 45) -> list[dict]:
        """1X2-flaggor utan utfall, för matcher som rimligen hunnit avgöras.
        Åldersgränsen hindrar evig omskanning av rader vars resultat aldrig
        dyker upp (ligor utan resultatkälla)."""
        floor = (dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
                 - dt.timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log WHERE outcome IS NULL "
            "AND market='1x2' AND match_start IS NOT NULL "
            "AND match_start < ? AND match_start > ?",
            (now_iso, floor)).fetchall()]

    def oddset_set_outcome(self, flag: dict, outcome: int,
                           outcome_key: Optional[str]) -> None:
        self.conn.execute(
            "UPDATE oddset_value_log SET outcome=?, outcome_key=? "
            "WHERE match_id=? AND market=? AND sign=? AND line_key=? "
            "AND model_version=?",
            (outcome, outcome_key,
             flag["match_id"], flag["market"], flag["sign"], flag["line_key"],
             flag.get("model_version") or "legacy"))
        self._commit()

    def oddset_history_before(self, match_id: str, market: str,
                              before_iso: str,
                              sources: tuple[str, ...] = ("pinnacle", "derived")
                              ) -> list[dict]:
        """Prisserien för valda källor före en tidpunkt, i tidsordning.

        Default = Pinnacle (inkl. derived) — det ordinarie stängningsankaret.
        `sources` finns för skuggmätningen av ANDRA ankaret (Smarkets); byt
        ALDRIG default utan att läsa 🎯 ANKARE ≠ BOK i CLAUDE.md."""
        holes = ",".join("?" * len(sources))
        return [dict(r) for r in self.conn.execute(
            "SELECT sign, odds, line, fetched_at, last_seen_at, available "
            "FROM oddset_odds WHERE match_id=? "
            f"AND market=? AND source IN ({holes}) AND fetched_at < ? "
            "AND odds IS NOT NULL ORDER BY fetched_at, id",
            (match_id, market, *sources, before_iso)).fetchall()]

    def oddset_set_closing(self, flag: dict, fair: Optional[float],
                           odds: Optional[float], note: Optional[str],
                           closing_line: Optional[float] = None,
                           line_delta: Optional[float] = None,
                           line_move_score: Optional[float] = None,
                           anchor2_closing_fair: Optional[float] = None) -> None:
        self.conn.execute(
            "UPDATE oddset_value_log SET closing_fair=?, closing_odds=?, closing_note=?, "
            "closing_line=?, line_delta=?, line_move_score=?, "
            "anchor2_closing_fair=? WHERE match_id=? "
            "AND market=? AND sign=? AND line_key=? AND model_version=?",
            (fair, odds, note, closing_line, line_delta, line_move_score,
             anchor2_closing_fair,
             flag["match_id"], flag["market"], flag["sign"], flag["line_key"],
             flag.get("model_version") or "legacy"))
        self._commit()

    def oddset_clv_rows(self, limit: Optional[int] = None) -> list[dict]:
        """Flaggor i CLV-facitet. limit=None = HELA historiken.

        Default var tidigare 300, vilket gjorde clv_report till ett rullande
        fönster: n, snitt och grönt-kriteriet räknades bara på de 300 senaste
        flaggorna medan äldre utfall föll tyst ur facitet (survivorship).
        Sätt limit endast för visningslistor — aldrig för statistiken."""
        if limit is None:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM oddset_value_log ORDER BY first_at DESC").fetchall()]
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_value_log ORDER BY first_at DESC LIMIT ?",
            (limit,)).fetchall()]

    # --- WP5 prediction ledger -------------------------------------------------

    def oddset_prediction_captured(self, match_id: str, horizon: str, tier: str,
                                   signal_version: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM oddset_prediction_capture WHERE match_id=? AND horizon=? "
            "AND tier=? AND signal_version=?",
            (match_id, horizon, tier, signal_version)).fetchone() is not None

    def oddset_capture_predictions(self, capture: dict, rows: list[dict]) -> int:
        """Spara en horisont atomärt och exakt en gång.

        Capture-raden skrivs även när rows är tom: källfrånvaro får inte
        senare maskeras som en skenbart exakt horisont. Returnerar antal nya
        prediktionsrader; 0 om horisonten redan var fångad.
        """
        with self.bulk():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO oddset_prediction_capture(match_id, horizon, "
                "tier, signal_version, base_version, match_start, target_at, "
                "captured_at, offset_minutes, delay_minutes, row_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (capture["match_id"], capture["horizon"], capture["tier"],
                 capture["signal_version"], capture["base_version"],
                 capture["match_start"], capture["target_at"],
                 capture["captured_at"], capture["offset_minutes"],
                 capture["delay_minutes"], len(rows)))
            if cur.rowcount == 0:
                return 0
            for r in rows:
                self.conn.execute(
                    "INSERT INTO oddset_prediction_log(match_id, horizon, tier, market, "
                    "sign, line, line_key, league, description, match_start, target_at, "
                    "captured_at, offset_minutes, fair_prob, fair_source, fair_available, "
                    "fair_fresh, model_anchored, book, book_odds, book_available, "
                    "book_fresh, edge, eligible, is_flag, signal_version, base_version, "
                    "git_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (capture["match_id"], capture["horizon"], capture["tier"],
                     r["market"], r["sign"], r.get("line"), r["line_key"],
                     capture.get("league"), capture.get("description"),
                     capture["match_start"], capture["target_at"],
                     capture["captured_at"], capture["offset_minutes"],
                     r["fair_prob"], r["fair_source"], int(r["fair_available"]),
                     int(r["fair_fresh"]), r.get("model_anchored"), r.get("book"),
                     r.get("book_odds"), int(r["book_available"]),
                     int(r["book_fresh"]), r.get("edge"), int(r["eligible"]),
                     int(r["is_flag"]), capture["signal_version"],
                     capture["base_version"], capture.get("git_hash")))
        return len(rows)

    def oddset_unresolved_predictions(self, now_iso: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_prediction_log WHERE closing_fair IS NULL "
            "AND closing_note IS NULL AND match_start < ?",
            (now_iso,)).fetchall()]

    def oddset_set_prediction_closing(
            self, row: dict, fair: Optional[float], odds: Optional[float],
            note: Optional[str], closing_line: Optional[float] = None,
            line_delta: Optional[float] = None,
            line_move_score: Optional[float] = None) -> None:
        self.conn.execute(
            "UPDATE oddset_prediction_log SET closing_fair=?, closing_odds=?, "
            "closing_note=?, closing_line=?, line_delta=?, line_move_score=? "
            "WHERE match_id=? AND horizon=? AND tier=? AND market=? AND sign=? "
            "AND signal_version=?",
            (fair, odds, note, closing_line, line_delta, line_move_score,
             row["match_id"], row["horizon"], row["tier"], row["market"],
             row["sign"], row["signal_version"]))
        self._commit()

    def oddset_prediction_rows(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, c.delay_minutes FROM oddset_prediction_log p "
            "JOIN oddset_prediction_capture c ON c.match_id=p.match_id "
            "AND c.horizon=p.horizon AND c.tier=p.tier "
            "AND c.signal_version=p.signal_version "
            "ORDER BY p.captured_at, p.match_id, p.tier, p.market, p.sign").fetchall()]

    def oddset_prediction_captures(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_prediction_capture ORDER BY captured_at, match_id, tier"
        ).fetchall()]

    def oddset_prediction_market_rows(
            self, match_id: str, horizon: str, tier: str,
            signal_version: str, market: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM oddset_prediction_log WHERE match_id=? AND horizon=? "
            "AND tier=? AND signal_version=? AND market=? ORDER BY sign",
            (match_id, horizon, tier, signal_version, market)).fetchall()]

    def oddset_prediction_capture(
            self, match_id: str, horizon: str, tier: str,
            signal_version: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM oddset_prediction_capture WHERE match_id=? "
            "AND horizon=? AND tier=? AND signal_version=?",
            (match_id, horizon, tier, signal_version)).fetchone()
        return dict(row) if row else None

    # --- Modell v2: frysta point-in-time-features -----------------------------

    def oddset_save_v2_features(self, capture: dict) -> bool:
        """Spara ett semantiskt versionerat feature-payload exakt en gång."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO oddset_v2_feature_capture(match_id, horizon, "
            "model_signal_version, feature_version, captured_at, match_start, "
            "capture_mode, payload_hash, payload_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (capture["match_id"], capture["horizon"],
             capture["model_signal_version"], capture["feature_version"],
             capture["captured_at"], capture["match_start"],
             capture["capture_mode"], capture["payload_hash"],
             capture["payload_json"], capture["created_at"]))
        self._commit()
        return bool(cur.rowcount)

    def oddset_v2_features(self, feature_version: Optional[str] = None) -> list[dict]:
        q, args = "SELECT * FROM oddset_v2_feature_capture", []
        if feature_version:
            q += " WHERE feature_version=?"
            args.append(feature_version)
        q += " ORDER BY captured_at, match_id, horizon, model_signal_version"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    # --- Modell v2.2: isolerad shadowkontroll ---------------------------------

    def oddset_save_v22_shadow(self, capture: dict) -> bool:
        columns = (
            "match_id", "horizon", "shadow_version", "feature_version",
            "sharp_signal_version", "model_signal_version", "league",
            "match_start", "target_at", "captured_at", "offset_minutes",
            "delay_minutes", "state", "eligible", "fallback_reason",
            "issues_json", "sharp_p1", "sharp_px", "sharp_p2", "v22_p1",
            "v22_px", "v22_p2", "feature_payload_hash", "created_at",
        )
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO oddset_v22_shadow_capture({','.join(columns)}) "
            f"VALUES({','.join('?' for _ in columns)})",
            tuple(capture[column] for column in columns))
        self._commit()
        return bool(cur.rowcount)

    def oddset_v22_shadows(
            self, shadow_version: Optional[str] = None) -> list[dict]:
        query, args = "SELECT * FROM oddset_v22_shadow_capture", []
        if shadow_version:
            query += " WHERE shadow_version=?"
            args.append(shadow_version)
        query += " ORDER BY captured_at,match_id,horizon"
        return [dict(row) for row in self.conn.execute(query, args).fetchall()]

    # --- WP9c: Sofascore lagmatcher i alla tävlingar ------------------------

    def oddset_save_sofa_team(self, team: dict, captured_at: str,
                              league: Optional[str] = None,
                              season_id: Optional[int] = None) -> None:
        """Upserta ett verifierat fotbollslag och, om angivet, ligascopet.

        En stub från eventlistan får aldrig radera redan hämtade arenafält.
        `detail_fetched_at` sätts därför bara av ett lyckat `/team/{id}`-svar.
        """
        if team.get("sport") != "football":
            raise ValueError(f"Sofascore-lag är inte fotboll: {team.get('sport')!r}")
        if team.get("team_id") is None or not team.get("team_key") or not team.get("name"):
            raise ValueError("Sofascore-lag saknar id eller namn")
        if (league is None) != (season_id is None):
            raise ValueError("league och season_id måste anges tillsammans")
        with self.bulk():
            self.conn.execute(
                "INSERT INTO oddset_sofa_team(team_id, team_key, name, country_code, "
                "sport, venue_id, venue_name, venue_city, venue_lat, venue_lon, "
                "first_seen_at, last_seen_at, detail_fetched_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(team_id) DO UPDATE SET "
                "team_key=excluded.team_key, name=excluded.name, "
                "country_code=COALESCE(excluded.country_code,oddset_sofa_team.country_code), "
                "sport=excluded.sport, "
                "venue_id=COALESCE(excluded.venue_id,oddset_sofa_team.venue_id), "
                "venue_name=COALESCE(excluded.venue_name,oddset_sofa_team.venue_name), "
                "venue_city=COALESCE(excluded.venue_city,oddset_sofa_team.venue_city), "
                "venue_lat=COALESCE(excluded.venue_lat,oddset_sofa_team.venue_lat), "
                "venue_lon=COALESCE(excluded.venue_lon,oddset_sofa_team.venue_lon), "
                "first_seen_at=MIN(oddset_sofa_team.first_seen_at,excluded.first_seen_at), "
                "last_seen_at=MAX(oddset_sofa_team.last_seen_at,excluded.last_seen_at), "
                "detail_fetched_at=COALESCE(excluded.detail_fetched_at,"
                "oddset_sofa_team.detail_fetched_at)",
                (team["team_id"], team["team_key"], team["name"],
                 team.get("country_code"), team["sport"], team.get("venue_id"),
                 team.get("venue_name"), team.get("venue_city"), team.get("venue_lat"),
                 team.get("venue_lon"), captured_at, captured_at,
                 team.get("detail_fetched_at")))
            if league is not None:
                self.conn.execute(
                    "INSERT INTO oddset_sofa_team_scope(team_id,league,season_id,"
                    "first_seen_at,last_seen_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(team_id,league,season_id) DO UPDATE SET "
                    "first_seen_at=MIN(oddset_sofa_team_scope.first_seen_at,"
                    "excluded.first_seen_at), last_seen_at=MAX("
                    "oddset_sofa_team_scope.last_seen_at,excluded.last_seen_at)",
                    (team["team_id"], league, int(season_id), captured_at, captured_at))

    def oddset_sofa_teams(self, league: Optional[str] = None) -> list[dict]:
        q = ("SELECT t.*,s.league,s.season_id,s.first_seen_at AS scope_first_seen_at,"
             "s.last_seen_at AS scope_last_seen_at FROM oddset_sofa_team t "
             "JOIN oddset_sofa_team_scope s ON s.team_id=t.team_id")
        args: list = []
        if league is not None:
            q += " WHERE s.league=?"
            args.append(league)
        q += " ORDER BY s.league,s.season_id DESC,t.team_key,t.team_id"
        return [dict(row) for row in self.conn.execute(q, args).fetchall()]

    def oddset_sofa_team(self, team_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM oddset_sofa_team WHERE team_id=?", (team_id,)).fetchone()
        return dict(row) if row else None

    def oddset_sofa_team_latest_capture(self, team_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT MAX(captured_at) AS captured_at FROM oddset_sofa_team_event_capture "
            "WHERE team_id=?", (team_id,)).fetchone()
        return row["captured_at"] if row and row["captured_at"] else None

    def oddset_save_sofa_team_event_capture(
            self, capture: dict, events: list[dict]) -> int:
        """Spara ett lyckat teamsvar och dess event atomärt.

        Eventens `first_seen_at` är kunskapsgränsen för framtida PIT-features.
        Ett felaktigt event eller en capture som redan finns lämnar ingen
        halvskriven historik.
        """
        team_id = int(capture["team_id"])
        if not capture.get("policy_version"):
            raise ValueError("Sofascore-capture saknar policyversion")
        for event in events:
            # Sedan 2026-07-25 samlas även planerade/pågående matcher
            # (rotationsrisk). Valideringen krävde fortfarande `finished` och
            # hade fällt VARJE lagcapture med en kommande fixtur så fort
            # TTL:n gjorde lagen förfallna (~16:26 2026-07-26) — 0 scheduled-
            # event fanns sparade före fixen (granskningsfix F5c 2026-07-26).
            if (event.get("status") not in ("finished", "scheduled", "inprogress")
                    or event.get("event_id") is None
                    or not event.get("start_at")):
                raise ValueError("ogiltigt Sofascore-event")
            if team_id not in (event.get("home_team_id"), event.get("away_team_id")):
                raise ValueError("Sofascore-eventet tillhör inte capture-laget")
        starts = [event["start_at"] for event in events]
        with self.bulk():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO oddset_sofa_team_event_capture(team_id,"
                "captured_at,policy_version,page_count,raw_event_count,event_count,"
                "oldest_start,newest_start,payload_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                (team_id, capture["captured_at"], capture["policy_version"],
                 capture["page_count"],
                 capture["raw_event_count"], len(events), min(starts) if starts else None,
                 max(starts) if starts else None, capture["payload_hash"]))
            if cur.rowcount == 0:
                return 0
            for event in events:
                self.conn.execute(
                    "INSERT INTO oddset_sofa_team_event(event_id,start_at,status,"
                    "home_team_id,away_team_id,tournament_id,unique_tournament_id,"
                    "tournament_name,tournament_slug,country_code,home_score,away_score,"
                    "first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(event_id) DO UPDATE SET start_at=excluded.start_at, "
                    "status=excluded.status,home_team_id=excluded.home_team_id,"
                    "away_team_id=excluded.away_team_id,tournament_id=excluded.tournament_id,"
                    "unique_tournament_id=excluded.unique_tournament_id,"
                    "tournament_name=excluded.tournament_name,"
                    "tournament_slug=excluded.tournament_slug,"
                    "country_code=excluded.country_code,home_score=excluded.home_score,"
                    "away_score=excluded.away_score,first_seen_at=MIN("
                    "oddset_sofa_team_event.first_seen_at,excluded.first_seen_at),"
                    "last_seen_at=MAX(oddset_sofa_team_event.last_seen_at,"
                    "excluded.last_seen_at)",
                    (event["event_id"], event["start_at"], event["status"],
                     event["home_team_id"], event["away_team_id"],
                     event.get("tournament_id"), event.get("unique_tournament_id"),
                     event.get("tournament_name"), event.get("tournament_slug"),
                     event.get("country_code"), event.get("home_score"),
                     event.get("away_score"), capture["captured_at"],
                     capture["captured_at"]))
                latest_start = self.conn.execute(
                    "SELECT start_at FROM oddset_sofa_team_event_start "
                    "WHERE event_id=? ORDER BY seen_at DESC LIMIT 1",
                    (event["event_id"],)).fetchone()
                if latest_start is None or latest_start[0] != event["start_at"]:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO oddset_sofa_team_event_start("
                        "event_id,start_at,seen_at) VALUES(?,?,?)",
                        (event["event_id"], event["start_at"],
                         capture["captured_at"]))
        return len(events)

    def oddset_sofa_team_events_as_of(self, team_id: int, as_of: str,
                                      since: Optional[str] = None) -> list[dict]:
        """Avslutade matcher som både spelats och observerats före `as_of`."""
        q = ("SELECT * FROM oddset_sofa_team_event WHERE status='finished' "
             "AND (home_team_id=? OR away_team_id=?) AND start_at<? "
             "AND first_seen_at<=?")
        args: list = [team_id, team_id, as_of, as_of]
        if since is not None:
            q += " AND start_at>=?"
            args.append(since)
        q += " ORDER BY start_at,event_id"
        return [dict(row) for row in self.conn.execute(q, args).fetchall()]

    def oddset_sofa_team_fixtures_as_of(self, team_id: int,
                                        as_of: str) -> list[dict]:
        """PLANERADE matcher som var kända före `as_of` (rotationsrisk).

        PIT-regeln är densamma som för historiken: `first_seen_at <= as_of`
        avgör vad vi visste, inte vad som senare visade sig. Statusen läses inte
        — en fixtur vi såg som planerad räknas som planerad även om raden i dag
        är `finished`, annars smyger facit in i en förhandsfeature.
        Avsparkstiden läses ur förändringsserien `oddset_sofa_team_event_start`
        som den var känd VID `as_of` — huvudradens `start_at` skrivs över vid
        ombokning och får inte användas retroaktivt (granskningsfix F5a).
        """
        out = []
        for row in self.conn.execute(
                "SELECT * FROM oddset_sofa_team_event WHERE "
                "(home_team_id=? OR away_team_id=?) AND first_seen_at<=?",
                (team_id, team_id, as_of)):
            fixture = dict(row)
            known = self.conn.execute(
                "SELECT start_at FROM oddset_sofa_team_event_start "
                "WHERE event_id=? AND seen_at<=? ORDER BY seen_at DESC LIMIT 1",
                (fixture["event_id"], as_of)).fetchone()
            # Fallback till huvudraden gäller bara data från före migreringen
            # (scripts/migrera_team_event_start.py seedar serien).
            start = known[0] if known else fixture["start_at"]
            if start > as_of:
                out.append({**fixture, "start_at": start})
        out.sort(key=lambda fixture: (fixture["start_at"], fixture["event_id"]))
        return out

    def oddset_prediction_states(self) -> dict[tuple, dict]:
        rows = self.conn.execute("SELECT * FROM oddset_prediction_group_state").fetchall()
        return {(r["tier"], r["league"], r["market"], r["signal_version"]): dict(r)
                for r in rows}

    def oddset_set_prediction_state(self, key: tuple, status: str, at: str) -> None:
        tier, league, market, version = key
        candidate = at if status == "candidate" else None
        green = at if status == "green" else None
        self.conn.execute(
            "INSERT INTO oddset_prediction_group_state(tier, league, market, "
            "signal_version, status, candidate_at, green_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(tier,league,market,signal_version) DO UPDATE SET "
            "status=excluded.status, "
            "candidate_at=COALESCE(oddset_prediction_group_state.candidate_at, "
            "excluded.candidate_at), green_at=COALESCE(oddset_prediction_group_state.green_at, "
            "excluded.green_at)",
            (tier, league, market, version, status, candidate, green))
        self._commit()

    # --- WP8 frånvaro-snapshots ---------------------------------------------

    def oddset_save_absence_capture(self, capture: dict, players: list[dict]) -> int:
        """Spara ett lyckat lineup-svar atomärt, även när frånvarolistan är tom.

        Samma match/tid är idempotent. Separata spelarrader med stabilt provider-
        ID gör att frånvaroförändringar senare kan kopplas till oddsrörelser.
        """
        home_n = sum(p.get("side") == "home" for p in players)
        away_n = sum(p.get("side") == "away" for p in players)
        with self.bulk():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO oddset_absence_capture(match_id, captured_at, "
                "source_event_id, match_start, confirmed, payload_hash, home_missing, "
                "away_missing, missing_count) VALUES(?,?,?,?,?,?,?,?,?)",
                (capture["match_id"], capture["captured_at"],
                 capture.get("source_event_id"), capture.get("match_start"),
                 int(bool(capture.get("confirmed"))), capture["payload_hash"],
                 home_n, away_n, home_n + away_n))
            if cur.rowcount == 0:
                return 0
            for i, p in enumerate(players):
                side = p.get("side")
                if side not in ("home", "away"):
                    raise ValueError(f"ogiltig frånvarosida: {side!r}")
                player_id = p.get("player_id")
                name = p.get("name") or f"okänd-{i + 1}"
                player_key = (f"sofa:{player_id}" if player_id is not None
                              else "name:" + name.casefold().strip())
                self.conn.execute(
                    "INSERT INTO oddset_absence_player(match_id, captured_at, side, "
                    "player_key, player_id, name, position, reason_code, reason, "
                    "description, expected_end, appearances, rating) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (capture["match_id"], capture["captured_at"], side, player_key,
                     player_id, name, p.get("position"), p.get("reason_code"),
                     p.get("reason"), p.get("description"), p.get("expected_end"),
                     p.get("apps"), p.get("rating")))
        return len(players)

    def oddset_latest_absences(self, match_ids: list[str]) -> dict[str, dict]:
        if not match_ids:
            return {}
        marks = ",".join("?" for _ in match_ids)
        captures = self.conn.execute(
            "SELECT c.* FROM oddset_absence_capture c JOIN ("
            " SELECT match_id, MAX(captured_at) AS captured_at "
            f" FROM oddset_absence_capture WHERE match_id IN ({marks}) GROUP BY match_id"
            ") latest ON latest.match_id=c.match_id "
            "AND latest.captured_at=c.captured_at",
            match_ids).fetchall()
        out: dict[str, dict] = {}
        for c in captures:
            rec = {"at": c["captured_at"], "confirmed": bool(c["confirmed"]),
                   "source_event_id": c["source_event_id"], "home": [], "away": []}
            rows = self.conn.execute(
                "SELECT side, player_id, name, position, reason_code, reason, "
                "description, expected_end, appearances AS apps, rating "
                "FROM oddset_absence_player WHERE match_id=? AND captured_at=? "
                "ORDER BY side, name",
                (c["match_id"], c["captured_at"])).fetchall()
            for row in rows:
                player = {k: row[k] for k in row.keys() if k != "side" and row[k] is not None}
                rec[row["side"]].append(player)
            out[c["match_id"]] = rec
        return out

    def oddset_absence_history(self, match_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM oddset_absence_capture WHERE match_id=? "
            "ORDER BY captured_at", (match_id,)).fetchall()]

    # --- WP8 ClubElo: observerade snapshots + historiska PIT-intervall -------

    def oddset_save_elo_capture(self, capture: dict, ratings: list[dict]) -> int:
        """Spara en lyckad ranking atomärt. Tomma/ogiltiga svar sparas aldrig."""
        if not ratings:
            raise ValueError("ClubElo-capture saknar ratings")
        for rating in ratings:
            country = rating.get("country")
            if country is not None and country not in self.ODDSET_ELO_COUNTRIES:
                raise ValueError(f"ogiltigt ClubElo-land: {country!r}")
            if not rating.get("club_key") or rating.get("elo") is None:
                raise ValueError("ClubElo-rating saknar klubb eller Elo")
        with self.bulk():
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO oddset_elo_capture(captured_at, requested_date, "
                "source, payload_hash, row_count) VALUES(?,?,?,?,?)",
                (capture["captured_at"], capture["requested_date"],
                 capture["source"], capture["payload_hash"], len(ratings)))
            if cur.rowcount == 0:
                return 0
            for rating in ratings:
                self.conn.execute(
                    "INSERT INTO oddset_elo_rating(captured_at, club_key, club_raw, "
                    "country, level, elo, valid_from, valid_to) VALUES(?,?,?,?,?,?,?,?)",
                    (capture["captured_at"], rating["club_key"],
                     rating.get("club_raw") or rating["club_key"],
                     rating.get("country"), rating.get("level"), rating["elo"],
                     rating.get("valid_from"), rating.get("valid_to")))
        return len(ratings)

    def oddset_latest_elo(self) -> dict[str, int]:
        """Senaste observerade produktion/capture; backfill-ankare ignoreras."""
        capture = self.conn.execute(
            "SELECT captured_at FROM oddset_elo_capture "
            "WHERE source IN ('daily', 'legacy') "
            "ORDER BY julianday(captured_at) DESC, captured_at DESC LIMIT 1"
        ).fetchone()
        if not capture:
            return {}
        return {r["club_key"]: round(r["elo"]) for r in self.conn.execute(
            "SELECT club_key, elo FROM oddset_elo_rating WHERE captured_at=?",
            (capture["captured_at"],)).fetchall()}

    def oddset_save_elo_history(self, ratings: list[dict], fetched_at: str) -> int:
        """Upserta ClubElos giltighetsintervall; identisk omkörning ger noll."""
        changed = 0
        with self.bulk():
            for rating in ratings:
                if rating.get("country") not in self.ODDSET_ELO_COUNTRIES:
                    raise ValueError(f"ogiltigt ClubElo-land: {rating.get('country')!r}")
                cur = self.conn.execute(
                    "INSERT INTO oddset_elo_history(club_key, valid_from, valid_to, "
                    "club_raw, country, level, elo, first_fetched_at, last_fetched_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(club_key, valid_from) DO "
                    "UPDATE SET valid_to=excluded.valid_to, club_raw=excluded.club_raw, "
                    "country=excluded.country, level=excluded.level, elo=excluded.elo, "
                    "last_fetched_at=excluded.last_fetched_at WHERE "
                    "oddset_elo_history.valid_to != excluded.valid_to OR "
                    "oddset_elo_history.club_raw != excluded.club_raw OR "
                    "oddset_elo_history.country != excluded.country OR "
                    "COALESCE(oddset_elo_history.level,-1) != COALESCE(excluded.level,-1) OR "
                    "ABS(oddset_elo_history.elo-excluded.elo) > 0.000001",
                    (rating["club_key"], rating["valid_from"], rating["valid_to"],
                     rating["club_raw"], rating["country"], rating.get("level"),
                     rating["elo"], fetched_at, fetched_at))
                changed += cur.rowcount
        return changed

    def oddset_elo_as_of(self, day: str) -> dict[str, int]:
        """Rating vars providerintervall omfattar dagen (inklusive ändpunkter)."""
        rows = self.conn.execute(
            "SELECT club_key, elo, valid_from FROM oddset_elo_history "
            "WHERE valid_from<=? AND valid_to>=? ORDER BY club_key, valid_from DESC",
            (day, day)).fetchall()
        out: dict[str, int] = {}
        for row in rows:
            out.setdefault(row["club_key"], round(row["elo"]))
        return out

    def oddset_elo_details_as_of(self, day: str) -> dict[str, dict]:
        """PIT-Elo med providerintervallet kvar för feature-audit."""
        rows = self.conn.execute(
            "SELECT club_key, club_raw, country, level, elo, valid_from, valid_to, "
            "first_fetched_at, last_fetched_at FROM oddset_elo_history "
            "WHERE valid_from<=? AND valid_to>=? "
            "ORDER BY club_key, valid_from DESC", (day, day)).fetchall()
        out: dict[str, dict] = {}
        for row in rows:
            out.setdefault(row["club_key"], dict(row))
        return out
