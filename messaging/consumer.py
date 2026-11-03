import json
import uuid

from confluent_kafka import Consumer

consumer = Consumer(
    {
        "bootstrap.servers": "127.0.0.1:9092",
        "group.id": f"ai-news-test-{uuid.uuid4().hex[:8]}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
)

try:
    consumer.subscribe(["news.raw"])

    message = consumer.poll(timeout=15)

    if message is None:
        raise TimeoutError("No Kafka message received")

    if message.error():
        raise RuntimeError(str(message.error()))

    event = json.loads(message.value().decode("utf-8"))

    if "run_id" not in event or "stage" not in event:
        raise ValueError("Invalid Kafka event")

    print("[Consumer] success")
    print(json.dumps(event, ensure_ascii=False, indent=2))

    consumer.commit(message=message, asynchronous=False)

finally:
    consumer.close()