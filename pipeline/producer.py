"""
Kafka producer — reads JSON events from stdin or file and publishes to Kafka.
Divij Bhoj, 2026

The idea is simple: pipe the C++ event generator's stdout straight into this
script, and it'll push everything to Kafka. Gzip compression keeps the
network overhead reasonable even at high event rates.

Usage:
    ./event_generator -n 50000 | python -m pipeline.producer
    python -m pipeline.producer -f data/events.json
"""

import sys
import json
import time
import argparse
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from pipeline.config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_RAW


def create_producer(bootstrap_servers: str, retries: int = 5, delay: int = 3) -> KafkaProducer:
    """
    Create a Kafka producer with retry logic.
    Kafka sometimes takes a few seconds to become ready after docker compose up,
    so we retry a handful of times before giving up.
    """
    for attempt in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                batch_size=16384,
                linger_ms=10,
                compression_type="gzip",
            )
            print(f"Connected to Kafka at {bootstrap_servers}")
            return producer
        except NoBrokersAvailable:
            if attempt < retries - 1:
                print(f"  Kafka not ready yet, retrying in {delay}s... ({attempt+1}/{retries})")
                time.sleep(delay)
            else:
                raise


def run_producer(input_source, bootstrap_servers: str, topic: str):
    """Read JSON lines from stdin/file and publish each one to Kafka."""
    producer = create_producer(bootstrap_servers)
    count = 0
    start_time = time.time()

    try:
        for line in input_source:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                # use run_number + event_id as the Kafka key for partitioning
                key = f"{event.get('run_number', 0)}_{event.get('event_id', 0)}"
                producer.send(topic, key=key, value=event)
                count += 1

                if count % 1000 == 0:
                    producer.flush()
                    elapsed = time.time() - start_time
                    rate = count / elapsed if elapsed > 0 else 0
                    print(f"\r  Published {count:,} events ({rate:.0f} evt/s)", end="", flush=True)
            except json.JSONDecodeError:
                print(f"\n  Warning: skipping malformed JSON line", file=sys.stderr)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        producer.flush()
        producer.close()
        elapsed = time.time() - start_time
        print(f"\n  Done: {count:,} events published in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="LHC Event Kafka Producer",
        epilog="Example: ./event_generator -n 10000 | python -m pipeline.producer",
    )
    parser.add_argument("-f", "--file", help="Input JSON file (default: stdin)")
    parser.add_argument(
        "-b", "--bootstrap-servers",
        default=KAFKA_BOOTSTRAP_SERVERS,
        help=f"Kafka bootstrap servers (default: {KAFKA_BOOTSTRAP_SERVERS})",
    )
    parser.add_argument(
        "-t", "--topic",
        default=KAFKA_TOPIC_RAW,
        help=f"Kafka topic (default: {KAFKA_TOPIC_RAW})",
    )
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            run_producer(f, args.bootstrap_servers, args.topic)
    else:
        print("Reading events from stdin — pipe from event_generator...")
        run_producer(sys.stdin, args.bootstrap_servers, args.topic)


if __name__ == "__main__":
    main()
