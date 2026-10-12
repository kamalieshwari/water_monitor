-- Household Water Monitor - SQLite schema

CREATE TABLE IF NOT EXISTS houses (
    house_id      INTEGER PRIMARY KEY,   -- 1-16, matches node_id
    owner_name    TEXT,
    phone_number  TEXT,
    address       TEXT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'owner'   -- 'owner' or 'municipality'
);

CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    house_id      INTEGER NOT NULL,
    pressure      REAL,
    flow          REAL,
    recorded_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (house_id) REFERENCES houses(house_id)
);

CREATE TABLE IF NOT EXISTS house_status (
    house_id               INTEGER PRIMARY KEY,
    current_status         TEXT DEFAULT 'normal',   -- normal / possible_leak / no_supply
    issue_start_time        TEXT,
    user_notified           INTEGER DEFAULT 0,
    municipality_notified   INTEGER DEFAULT 0,
    last_seen               TEXT,
    node_online              INTEGER DEFAULT 1,
    FOREIGN KEY (house_id) REFERENCES houses(house_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    house_id      INTEGER NOT NULL,
    type          TEXT,      -- 'user' or 'municipality'
    message       TEXT,
    sent_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (house_id) REFERENCES houses(house_id)
);

-- One pending login OTP per house/node (only a keyed hash of the code is stored)
CREATE TABLE IF NOT EXISTS otp_codes (
    house_id    INTEGER PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER DEFAULT 0,
    sent_at     TEXT NOT NULL,
    FOREIGN KEY (house_id) REFERENCES houses(house_id)
);

-- A mobile number identifies exactly one house
CREATE UNIQUE INDEX IF NOT EXISTS idx_houses_phone ON houses(phone_number);

-- What each simulated house is currently set to in Demo control (shared by all web workers)
CREATE TABLE IF NOT EXISTS demo_scenarios (
    house_id  INTEGER PRIMARY KEY,
    scenario  TEXT NOT NULL
);
