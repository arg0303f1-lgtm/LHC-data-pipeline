"""
Configuration for the LHC Data Streaming Pipeline.
Divij Bhoj, 2026

All tuneable parameters in one place — override via environment
variables if needed (e.g. in Docker or CI).
"""

import os

# ── Kafka ────────────────────────────────────────────────────
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC_RAW         = "lhc-raw-events"
KAFKA_TOPIC_TRIGGERED   = "lhc-triggered-events"
KAFKA_TOPIC_STATS       = "lhc-statistics"
KAFKA_CONSUMER_GROUP    = "lhc-processor"

# ── Database ─────────────────────────────────────────────────
DATABASE_PATH = os.getenv("LHC_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "lhc_events.db"
))

# ── Trigger Thresholds ───────────────────────────────────────
TRIGGER_MUON_PT_MIN       = 25.0    # GeV
TRIGGER_DIMUON_MASS_LOW   = 75.0    # GeV
TRIGGER_DIMUON_MASS_HIGH  = 105.0   # GeV
TRIGGER_JET_PT_MIN        = 50.0    # GeV
TRIGGER_MULTI_JET_COUNT   = 4
TRIGGER_MET_MIN           = 50.0    # GeV

# ── Dashboard ────────────────────────────────────────────────
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
STATS_UPDATE_INTERVAL = 1.0  # seconds
