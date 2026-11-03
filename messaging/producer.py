import json
import uuid

from confluent_kafka import Producer

run_id = f"test-{uuid.uuid4().hex[:8]}"

producer = Producer(
    {"bootstrap.servers": "127.0.0.1:9092"}
)

event = {
    "event_version": 1,
    "run_id": run_id,
    "stage": "collector",
    "article_count": 2,
    "status": "completed",
}

delivery = {"ok": False, "error": None}


def on_delivery(err, msg):
    if err is not None:
        delivery["error"] = str(err)
    else:
        delivery["ok"] = True


producer.produce(
    topic="news.raw",
    key=run_id,
    value=json.dumps(
        event,
        ensure_ascii=False,
    ).encode("utf-8"),
    callback=on_delivery,
)

remaining = producer.flush(timeout=10)

if remaining or not delivery["ok"]:
    raise RuntimeError(
        f"Kafka delivery failed: {delivery['error']}"
    )

print(f"[Producer] success run_id={run_id}")