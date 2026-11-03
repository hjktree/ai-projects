"""Inspect and optionally replay one failed message from news.failed."""
import argparse
import base64
import json
import time
import uuid

from messaging.kafka_runtime import BOOTSTRAP, PIPELINE, publish, validate


def main():
    from confluent_kafka import Consumer

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": f"ai-news-dlq-inspect-{uuid.uuid4().hex[:10]}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe(["news.failed"])
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            msg = consumer.poll(1)
            if msg is None:
                continue
            if msg.error():
                raise RuntimeError(str(msg.error()))
            failed = json.loads(msg.value())
            if failed.get("run_id") != args.run_id:
                continue
            role = failed["stage"]
            source = failed["source_topic"]
            if role not in PIPELINE or source != PIPELINE[role][0]:
                raise ValueError("Invalid DLQ stage or source topic")
            raw = base64.b64decode(failed["original_payload_b64"], validate=True)
            original = json.loads(raw)
            validate(original, role)
            print(f"DLQ found: run_id={args.run_id}, role={role}, topic={source}")
            if args.send:
                publish(source, original)
                print("Replay published; check workers and logs")
            else:
                print("Preview only. Add --send to actually replay")
            return
        raise TimeoutError("Run ID not found in DLQ within 45 seconds")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()