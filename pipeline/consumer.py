"""
Kafka consumer — processes events, applies triggers, writes to SQLite.
Divij Bhoj, 2026

This is where the actual "physics" happens in the pipeline. Events
come in from Kafka, we run trigger logic on each one, and store the
results + some running statistics in SQLite. The dashboard reads
from the same database to show what's going on in real time.

Usage:
    python -m pipeline.consumer
    python -m pipeline.consumer --db data/lhc_events.db
"""

import json
import time
import sqlite3
import signal
import argparse
import os
from collections import defaultdict, deque
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from pipeline.trigger import apply_triggers
from pipeline.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TOPIC_RAW,
    KAFKA_CONSUMER_GROUP,
    DATABASE_PATH,
)

_running = True


def _signal_handler(sig, frame):
    global _running
    _running = False
    print("\n  Shutting down consumer...")


signal.signal(signal.SIGINT, _signal_handler)


class EventProcessor:
    """
    Handles the heavy lifting: runs triggers on each event, keeps
    track of statistics in memory, and periodically flushes to SQLite.
    """

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self._init_db()

        # in-memory counters for real-time stats
        # (reading these from SQLite every second would be too slow)
        self.stats = {
            "total_events": 0,
            "triggered_events": 0,
            "events_by_type": defaultdict(int),
            "triggers_fired": defaultdict(int),
            "recent_rates": deque(maxlen=60),       # events per second, last 60s
            "dimuon_masses": deque(maxlen=1000),     # for the mass histogram
            "met_values": deque(maxlen=1000),
            "processing_latency_ms": deque(maxlen=100),
            "start_time": time.time(),
        }
        self._sec_count = 0
        self._last_sec = int(time.time())

    def _init_db(self):
        """Set up the SQLite tables. If the schema file exists, use it;
        otherwise fall back to an inline definition."""
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "database", "schema.sql",
        )
        try:
            with open(schema_path) as f:
                self.conn.executescript(f.read())
        except FileNotFoundError:
            # inline fallback so the consumer works standalone too
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER, run_number INTEGER, timestamp_ms INTEGER,
                    event_type TEXT, num_particles INTEGER, num_jets INTEGER,
                    num_muons INTEGER, num_electrons INTEGER, met REAL,
                    met_phi REAL, sum_et REAL, primary_vertices INTEGER,
                    triggered BOOLEAN DEFAULT 0, trigger_bits TEXT,
                    dimuon_mass REAL, processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS trigger_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    window_start INTEGER, window_end INTEGER,
                    total_events INTEGER DEFAULT 0, triggered_events INTEGER DEFAULT 0,
                    single_muon_count INTEGER DEFAULT 0, dimuon_z_count INTEGER DEFAULT 0,
                    multi_jet_count INTEGER DEFAULT 0, high_met_count INTEGER DEFAULT 0,
                    avg_rate REAL DEFAULT 0, avg_latency_ms REAL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
        self.conn.commit()

    def process_event(self, event_data: dict) -> dict:
        """Run triggers on one event, update stats, write to DB."""
        t0 = time.time()
        trigger_results = apply_triggers(event_data)

        # update in-memory counters
        self.stats["total_events"] += 1
        self.stats["events_by_type"][event_data.get("event_type", "unknown")] += 1

        if trigger_results["any_trigger"]:
            self.stats["triggered_events"] += 1

        for name in ["single_muon", "dimuon_z", "multi_jet", "high_met"]:
            if trigger_results[name]:
                self.stats["triggers_fired"][name] += 1

        if trigger_results["dimuon_mass"] is not None:
            self.stats["dimuon_masses"].append(trigger_results["dimuon_mass"])

        self.stats["met_values"].append(event_data.get("met", 0))

        # track per-second event rate
        now_sec = int(time.time())
        if now_sec != self._last_sec:
            self.stats["recent_rates"].append(self._sec_count)
            self._sec_count = 0
            self._last_sec = now_sec
        self._sec_count += 1

        # insert into SQLite
        self.conn.execute(
            """INSERT INTO events
               (event_id, run_number, timestamp_ms, event_type, num_particles,
                num_jets, num_muons, num_electrons, met, met_phi, sum_et,
                primary_vertices, triggered, trigger_bits, dimuon_mass)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_data.get("event_id"),
                event_data.get("run_number"),
                event_data.get("timestamp_ms"),
                event_data.get("event_type"),
                event_data.get("num_particles"),
                event_data.get("num_jets"),
                event_data.get("num_muons"),
                event_data.get("num_electrons"),
                event_data.get("met"),
                event_data.get("met_phi"),
                event_data.get("sum_et"),
                event_data.get("primary_vertices"),
                trigger_results["any_trigger"],
                json.dumps({k: v for k, v in trigger_results.items()
                            if k not in ("dimuon_mass", "leading_muon_pt", "leading_jet_pt")}),
                trigger_results["dimuon_mass"],
            ),
        )

        # commit in batches of 100 to avoid hammering the disk
        if self.stats["total_events"] % 100 == 0:
            self.conn.commit()

        latency_ms = (time.time() - t0) * 1000
        self.stats["processing_latency_ms"].append(latency_ms)
        return trigger_results

    def get_stats_snapshot(self) -> dict:
        """Build a summary dict for the dashboard to display."""
        elapsed = time.time() - self.stats["start_time"]
        total = self.stats["total_events"]
        avg_rate = total / elapsed if elapsed > 0 else 0

        latencies = list(self.stats["processing_latency_ms"])
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        trigger_eff = {}
        if total > 0:
            for name, count in self.stats["triggers_fired"].items():
                trigger_eff[name] = round(count / total * 100, 2)

        return {
            "total_events": total,
            "triggered_events": self.stats["triggered_events"],
            "overall_trigger_rate": round(self.stats["triggered_events"] / total * 100, 2) if total > 0 else 0,
            "avg_event_rate": round(avg_rate, 1),
            "recent_rates": list(self.stats["recent_rates"]),
            "events_by_type": dict(self.stats["events_by_type"]),
            "trigger_efficiency": trigger_eff,
            "triggers_fired": dict(self.stats["triggers_fired"]),
            "dimuon_masses": list(self.stats["dimuon_masses"])[-200:],
            "met_values": list(self.stats["met_values"])[-200:],
            "avg_latency_ms": round(avg_latency, 3),
            "uptime_seconds": round(elapsed, 1),
        }

    def flush(self):
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()


def create_consumer(bootstrap_servers: str, topic: str, group: str,
                    retries: int = 5, delay: int = 3) -> KafkaConsumer:
    """Connect to Kafka with retry logic (same idea as the producer)."""
    for attempt in range(retries):
        try:
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=bootstrap_servers,
                group_id=group,
                auto_offset_reset="latest",
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                consumer_timeout_ms=1000,
            )
            print(f"Connected to Kafka, consuming from '{topic}'")
            return consumer
        except NoBrokersAvailable:
            if attempt < retries - 1:
                print(f"  Kafka not ready yet, retrying in {delay}s... ({attempt+1}/{retries})")
                time.sleep(delay)
            else:
                raise


def run_consumer(bootstrap_servers: str, topic: str, group: str, db_path: str):
    """Main consumer loop — polls Kafka, processes events, prints progress."""
    processor = EventProcessor(db_path)
    consumer = create_consumer(bootstrap_servers, topic, group)

    print(f"  Database: {db_path}")
    print(f"  Waiting for events...\n")

    count = 0
    start = time.time()

    while _running:
        try:
            messages = consumer.poll(timeout_ms=500)
            for tp, records in messages.items():
                for record in records:
                    processor.process_event(record.value)
                    count += 1

                    if count % 500 == 0:
                        elapsed = time.time() - start
                        rate = count / elapsed if elapsed > 0 else 0
                        stats = processor.get_stats_snapshot()
                        print(
                            f"\r  Processed: {count:,} | "
                            f"Rate: {rate:.0f} evt/s | "
                            f"Triggered: {stats['overall_trigger_rate']:.1f}% | "
                            f"Latency: {stats['avg_latency_ms']:.2f}ms",
                            end="", flush=True,
                        )
        except Exception as e:
            print(f"\n  Error: {e}", flush=True)
            time.sleep(1)

    processor.flush()
    processor.close()
    consumer.close()
    elapsed = time.time() - start
    print(f"\n  Done: {count:,} events processed in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="LHC Event Stream Processor")
    parser.add_argument("-b", "--bootstrap-servers", default=KAFKA_BOOTSTRAP_SERVERS)
    parser.add_argument("-t", "--topic", default=KAFKA_TOPIC_RAW)
    parser.add_argument("-g", "--group", default=KAFKA_CONSUMER_GROUP)
    parser.add_argument("--db", default=DATABASE_PATH)
    args = parser.parse_args()
    run_consumer(args.bootstrap_servers, args.topic, args.group, args.db)


if __name__ == "__main__":
    main()
