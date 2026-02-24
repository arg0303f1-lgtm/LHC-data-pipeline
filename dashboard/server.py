"""
Dashboard server — serves the real-time monitoring UI and provides stats API.

Reads from the EventProcessor's SQLite database and pushes updates via SocketIO.

Usage:
    python -m dashboard.server
    python -m dashboard.server --db data/lhc_events.db --port 5000
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import threading
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO

# Add parent dir so we can import pipeline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.config import DATABASE_PATH, DASHBOARD_HOST, DASHBOARD_PORT

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.config["SECRET_KEY"] = "lhc-pipeline-dashboard"
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = DATABASE_PATH


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Return current processing statistics."""
    try:
        conn = get_db()
        cur = conn.cursor()

        # Total counts
        cur.execute("SELECT COUNT(*) FROM events")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM events WHERE triggered = 1")
        triggered = cur.fetchone()[0]

        # By event type
        cur.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type")
        by_type = {row[0]: row[1] for row in cur.fetchall()}

        # Trigger breakdown
        trigger_counts = {"single_muon": 0, "dimuon_z": 0, "multi_jet": 0, "high_met": 0}
        cur.execute("SELECT trigger_bits FROM events WHERE triggered = 1 ORDER BY id DESC LIMIT 5000")
        for row in cur.fetchall():
            try:
                bits = json.loads(row[0])
                for k in trigger_counts:
                    if bits.get(k):
                        trigger_counts[k] += 1
            except (json.JSONDecodeError, TypeError):
                pass

        # Recent dimuon masses
        cur.execute(
            "SELECT dimuon_mass FROM events WHERE dimuon_mass IS NOT NULL "
            "ORDER BY id DESC LIMIT 200"
        )
        dimuon_masses = [row[0] for row in cur.fetchall()]

        # Recent MET values
        cur.execute("SELECT met FROM events ORDER BY id DESC LIMIT 200")
        met_values = [row[0] for row in cur.fetchall()]

        # Recent event rate (events in last 30 seconds)
        now_ms = int(time.time() * 1000)
        rates = []
        for i in range(30):
            t0 = now_ms - (i + 1) * 1000
            t1 = now_ms - i * 1000
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp_ms BETWEEN ? AND ?",
                (t0, t1),
            )
            rates.append(cur.fetchone()[0])
        rates.reverse()

        conn.close()

        return jsonify({
            "total_events": total,
            "triggered_events": triggered,
            "overall_trigger_rate": round(triggered / total * 100, 2) if total > 0 else 0,
            "events_by_type": by_type,
            "trigger_counts": trigger_counts,
            "dimuon_masses": dimuon_masses,
            "met_values": met_values,
            "recent_rates": rates,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def health():
    try:
        conn = get_db()
        conn.execute("SELECT 1")
        conn.close()
        return jsonify({"status": "ok", "database": DB_PATH})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def background_push():
    """Periodically push stats to connected WebSocket clients."""
    while True:
        socketio.sleep(2)
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM events")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM events WHERE triggered = 1")
            triggered = cur.fetchone()[0]

            cur.execute(
                "SELECT dimuon_mass FROM events WHERE dimuon_mass IS NOT NULL "
                "ORDER BY id DESC LIMIT 50"
            )
            masses = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT met FROM events ORDER BY id DESC LIMIT 50")
            mets = [row[0] for row in cur.fetchall()]

            now_ms = int(time.time() * 1000)
            cur.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp_ms > ?",
                (now_ms - 2000,),
            )
            recent = cur.fetchone()[0]

            conn.close()

            socketio.emit("stats_update", {
                "total_events": total,
                "triggered_events": triggered,
                "trigger_rate": round(triggered / total * 100, 2) if total > 0 else 0,
                "event_rate": recent / 2.0,
                "recent_masses": masses,
                "recent_mets": mets,
            })
        except Exception:
            pass


@socketio.on("connect")
def on_connect():
    print("  Dashboard client connected")


def main():
    global DB_PATH
    parser = argparse.ArgumentParser(description="LHC Pipeline Dashboard")
    parser.add_argument("--db", default=DATABASE_PATH)
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT)
    parser.add_argument("--host", default=DASHBOARD_HOST)
    args = parser.parse_args()
    DB_PATH = args.db

    print(f"╔══════════════════════════════════════════╗")
    print(f"║   LHC Data Pipeline — Dashboard          ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║  URL:  http://localhost:{args.port}             ║")
    print(f"║  DB:   {os.path.basename(args.db):33s}║")
    print(f"╚══════════════════════════════════════════╝")

    socketio.start_background_task(background_push)
    socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    main()
