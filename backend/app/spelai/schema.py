"""Schema för facitsidans tabeller (designens avsnitt 5.1).

DDL:en här körs BARA av `scripts/migrera_spelai.py` (och av testerna mot
temporära databaser). `Storage` kör den aldrig: facitsidans tabeller ska finnas
för att de migrerats med backup och rapport, inte för att en process råkade
öppna databasen.

Allt är append-only. Triggrarna nedan gör regeln teknisk i stället för en
överenskommelse: en UPDATE eller DELETE på en spelai-tabell avbryts av SQLite.
Status som ändras (inkorgens "besvarad", paus) härleds ur nya rader.
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = "spelai-schema-v1"

TABLES = (
    "spelai_state", "spelai_event", "spelai_input", "spelai_pool_proposal",
    "spelai_pool_result", "spelai_run", "spelai_inbox", "spelai_inbox_answer",
    "spelai_played", "spelai_live_price", "spelai_live_bet",
    "spelai_live_result",
)

SPELAI_SCHEMA = """
-- Nyckel/värde som HÄNDELSER: senaste raden per nyckel gäller (paus,
-- facit_start). Ingen rad skrivs över.
CREATE TABLE IF NOT EXISTS spelai_state (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    key     TEXT NOT NULL,
    value   TEXT,
    set_at  TEXT NOT NULL,
    source  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spelai_state_key ON spelai_state (key, id);

-- Facitsidans journal: frysning, missat, notis skickad, misstänkt svar.
-- dedup_key gör en händelse (t.ex. en notis) idempotent.
CREATE TABLE IF NOT EXISTS spelai_event (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ref         TEXT,
    detail_json TEXT,
    dedup_key   TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_spelai_event_kind ON spelai_event (kind, id);

-- Indatapaketet: poolvarvets FÄRSKA draw + sharp (färskhetsregeln) +
-- movement + värderingsomsättning + jackpot, fruset när en horisont är due.
-- Standarden och agenten bygger ur exakt samma paket.
CREATE TABLE IF NOT EXISTS spelai_input (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product        TEXT NOT NULL,
    draw_number    INTEGER NOT NULL,
    horizon        TEXT NOT NULL CHECK (horizon IN ('6h', '30m')),
    observed_at    TEXT NOT NULL,
    captured_at    TEXT NOT NULL,
    reg_close_time TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json   TEXT NOT NULL,
    payload_hash   TEXT NOT NULL,
    UNIQUE (product, draw_number, horizon)
);

CREATE TABLE IF NOT EXISTS spelai_pool_proposal (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    product           TEXT NOT NULL,
    draw_number       INTEGER NOT NULL,
    level_kr          INTEGER NOT NULL,
    horizon           TEXT NOT NULL CHECK (horizon IN ('6h', '30m')),
    role              TEXT NOT NULL CHECK (role IN ('agent', 'standard')),
    status            TEXT NOT NULL CHECK (status IN
                        ('fryst', 'ogiltigt', 'saknas', 'missat', 'pausad')),
    reason            TEXT,
    strategy_version  TEXT,
    config_key        TEXT,
    format            TEXT CHECK (format IS NULL OR format IN ('rows', 'msystem')),
    events_order      TEXT,
    rows_text         TEXT,
    msystem_json      TEXT,
    n_rows            INTEGER,
    cost_kr           REAL,
    rows_hash         TEXT,
    motivation        TEXT,
    input_id          INTEGER REFERENCES spelai_input(id),
    input_observed_at TEXT,
    obs_svs_at        TEXT,
    obs_sharp_at      TEXT,
    obs_turnover_at   TEXT,
    reg_close_time    TEXT NOT NULL,
    frozen_at         TEXT NOT NULL,
    code_version      TEXT,
    agent_stderr      TEXT,
    UNIQUE (product, draw_number, level_kr, horizon, role)
);
CREATE INDEX IF NOT EXISTS idx_spelai_proposal_draw
    ON spelai_pool_proposal (product, draw_number, horizon);

CREATE TABLE IF NOT EXISTS spelai_pool_result (
    proposal_id         INTEGER PRIMARY KEY REFERENCES spelai_pool_proposal(id),
    settled_at          TEXT NOT NULL,
    settlement_version  TEXT NOT NULL,
    correct_max         INTEGER,
    correct_dist        TEXT,
    payout_kr           REAL,
    published_payout_kr REAL,
    payout_complete     INTEGER,
    cost_kr             REAL,
    roi                 REAL,
    note                TEXT
);

CREATE TABLE IF NOT EXISTS spelai_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT NOT NULL,
    task        TEXT,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL,
    model       TEXT,
    usage_json  TEXT,
    cost_usd    REAL,
    note        TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spelai_run_started ON spelai_run (started_at);

CREATE TABLE IF NOT EXISTS spelai_inbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT NOT NULL UNIQUE,
    typ             TEXT NOT NULL CHECK (typ IN
                      ('beslut', 'forslag_forbattring', 'forslag_spelrad')),
    kalla           TEXT NOT NULL,
    rubrik          TEXT NOT NULL,
    varfor          TEXT NOT NULL,
    alternativ_json TEXT NOT NULL,
    sista_tid       TEXT,
    file_name       TEXT,
    payload_hash    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spelai_inbox_answer (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inbox_id      INTEGER NOT NULL REFERENCES spelai_inbox(id),
    val           TEXT NOT NULL,
    kommentar     TEXT,
    answered_at   TEXT NOT NULL,
    user_agent    TEXT,
    forwarded_for TEXT,
    client_host   TEXT,
    misstankt     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_spelai_answer_inbox
    ON spelai_inbox_answer (inbox_id, id);

CREATE TABLE IF NOT EXISTS spelai_played (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL CHECK (kind IN ('pool', 'live')),
    proposal_id   INTEGER REFERENCES spelai_pool_proposal(id),
    live_bet_id   INTEGER,
    product       TEXT,
    draw_number   INTEGER,
    level_kr      INTEGER,
    note          TEXT,
    played_at     TEXT NOT NULL,
    user_agent    TEXT,
    forwarded_for TEXT,
    client_host   TEXT
);

-- Livedelen (fas E). Skapas nu men används inte ännu.
CREATE TABLE IF NOT EXISTS spelai_live_price (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_ref   TEXT NOT NULL,
    market      TEXT NOT NULL,
    line        REAL,
    sign        TEXT NOT NULL,
    odds        REAL,
    market_open INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    http_age_s  REAL,
    source      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spelai_live_price
    ON spelai_live_price (match_ref, market, observed_at);

CREATE TABLE IF NOT EXISTS spelai_live_bet (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    match_ref         TEXT NOT NULL,
    minute            INTEGER,
    score             TEXT,
    market            TEXT NOT NULL,
    line              REAL,
    sign              TEXT NOT NULL,
    odds              REAL NOT NULL,
    price_id          INTEGER REFERENCES spelai_live_price(id),
    price_observed_at TEXT NOT NULL,
    stake_kr          REAL NOT NULL,
    model_version     TEXT,
    motivation        TEXT,
    placed_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spelai_live_result (
    bet_id                 INTEGER PRIMARY KEY REFERENCES spelai_live_bet(id),
    outcome                TEXT NOT NULL CHECK (outcome IN
                             ('vinst', 'forlust', 'push', 'halv_vinst', 'halv_forlust')),
    net_kr                 REAL NOT NULL,
    settled_at             TEXT NOT NULL,
    next_price_odds        REAL,
    next_price_observed_at TEXT
);
"""


def _append_only_triggers() -> str:
    parts = []
    for table in TABLES:
        for op in ("UPDATE", "DELETE"):
            parts.append(
                f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{op.lower()} "
                f"BEFORE {op} ON {table} BEGIN "
                f"SELECT RAISE(ABORT, 'spelai: {table} är append-only'); END;")
    return "\n".join(parts)


FULL_SCHEMA = SPELAI_SCHEMA + "\n" + _append_only_triggers()


def tables_exist(conn: sqlite3.Connection, tables=TABLES) -> bool:
    """Finns ALLA tabellerna? Läsande vägar svarar tomt annars."""
    names = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'spelai_%'")}
    return all(table in names for table in tables)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Skapa tabellerna. ENBART för migreringsskriptet och testerna."""
    conn.executescript("BEGIN IMMEDIATE;\n" + FULL_SCHEMA + "\nCOMMIT;")
