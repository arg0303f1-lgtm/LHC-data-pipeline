-- LHC Data Pipeline - SQLite Schema
-- Stores processed collision events and trigger statistics

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL,
    run_number      INTEGER NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    num_particles   INTEGER,
    num_jets        INTEGER,
    num_muons       INTEGER,
    num_electrons   INTEGER,
    met             REAL,
    met_phi         REAL,
    sum_et          REAL,
    primary_vertices INTEGER,
    triggered       BOOLEAN DEFAULT 0,
    trigger_bits    TEXT,
    dimuon_mass     REAL,
    processed_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trigger_stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    window_start        INTEGER NOT NULL,
    window_end          INTEGER NOT NULL,
    total_events        INTEGER DEFAULT 0,
    triggered_events    INTEGER DEFAULT 0,
    single_muon_count   INTEGER DEFAULT 0,
    dimuon_z_count      INTEGER DEFAULT 0,
    multi_jet_count     INTEGER DEFAULT 0,
    high_met_count      INTEGER DEFAULT 0,
    avg_rate            REAL DEFAULT 0,
    avg_latency_ms      REAL DEFAULT 0,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_metadata (
    run_number      INTEGER PRIMARY KEY,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME,
    total_events    INTEGER DEFAULT 0,
    config_json     TEXT
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_triggered ON events(triggered);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_number);
CREATE INDEX IF NOT EXISTS idx_trigger_stats_window ON trigger_stats(window_start);
