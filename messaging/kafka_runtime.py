"""Local Kafka multi-worker runtime (one partition / one worker per role)."""
import base64
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agents import SummaryResult, run_researcher, run_reviewer, run_summarizer
from common import ROOT

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "127.0.0.1:9092")
PIPELINE = {
    "researcher": ("news.raw", "news.selected", "collector"),
    "summarizer": ("news.selected", "news.summarized", "researcher"),
    "reviewer": ("news.summarized", "news.reviewed", "summarizer"),
    "report": ("news.reviewed", None, "reviewer"),
}
STATE = ROOT / "tests/output/data/kafka-processed.sqlite3"
LOG_DIR = ROOT / "tests/output/logs/kafka"
REPORT_DIR = ROOT / "tests/output/reports/kafka"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(run_id, role, status, **details):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "stage": f"kafka_{role}",
        "status": status,
        **details,
    }
    with (LOG_DIR / f"{run_id}.{role}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def publish(topic, event):
    from confluent_kafka import Producer

    outcome = {"error": "not acknowledged"}

    def callback(error, _message):
        outcome["error"] = str(error) if error else None

    producer = Producer({"bootstrap.servers": BOOTSTRAP, "enable.idempotence": True})
    producer.produce(
        topic,
        key=event["run_id"].encode("utf-8"),
        value=json.dumps(event, ensure_ascii=False).encode("utf-8"),
        callback=callback,
    )
    if producer.flush(20) or outcome["error"] is not None:
        raise RuntimeError(f"Publish failed for {topic}: {outcome['error']}")


def _connect_db():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE, timeout=30)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS processed ("
        "run_id TEXT NOT NULL, role TEXT NOT NULL, payload_hash TEXT NOT NULL,"
        "PRIMARY KEY (run_id, role))"
    )
    return conn


def seen(run_id, role, payload_hash):
    with _connect_db() as conn:
        found = conn.execute(
            "SELECT payload_hash FROM processed WHERE run_id=? AND role=?",
            (run_id, role),
        ).fetchone()
    if found is None:
        return False
    if found[0] != payload_hash:
        raise ValueError("Same run_id and role with different payload")
    return True


def record_done(run_id, role, payload_hash):
    with _connect_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed VALUES (?, ?, ?)",
            (run_id, role, payload_hash),
        )


def validate(event, role):
    if not isinstance(event, dict):
        raise TypeError("Event is not a JSON object")
    run_id = event.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ValueError("Invalid run_id")
    if event.get("event_version") != 1 or event.get("stage") != PIPELINE[role][2]:
        raise ValueError("Invalid event version or stage")
    if event.get("backend") != os.getenv("NEWS_AI_BACKEND", "mock").lower():
        raise ValueError("NEWS_AI_BACKEND mismatch")
    articles = event.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("Empty or invalid articles")
    if any(not isinstance(a, dict) or not isinstance(a.get("id"), str) or not isinstance(a.get("title"), str) for a in articles):
        raise ValueError("Malformed article")
    return run_id


def write_report(event):
    directory = Path(os.getenv("KAFKA_REPORT_DIR", str(REPORT_DIR)))
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{event['run_id']}.md"
    if destination.exists():
        return destination

    summaries = SummaryResult.model_validate(event["summaries"])
    article_by_id = {a["id"]: a for a in event["articles"]}
    if set(article_by_id) != {i.article_id for i in summaries.items}:
        raise ValueError("Summary/article IDs do not match")

    title = "# [MOCK] Kafka 경제 뉴스 브리핑" if event["backend"] == "mock" else "# Kafka 경제 뉴스 브리핑"
    lines = [title, "", f"Run ID: {event['run_id']}", f"Backend: {event['backend']}", ""]
    if event["backend"] == "mock":
        lines.extend(["**가상 데이터로 생성한 테스트 결과입니다.**", ""])
    for no, item in enumerate(summaries.items, 1):
        article = article_by_id[item.article_id]
        lines.extend([f"## {no}. {article['title']}", "", item.line, ""])
        if article.get("url"):
            lines.extend([f"원문: {article['url']}", ""])

    # Avoid partially written reports; one report worker is assumed.
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text("\n".join(lines), encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def process(role, event):
    run_id = validate(event, role)
    if event["backend"] == "mock" and os.getenv("KAFKA_TEST_FAIL_ROLE") == role:
        raise RuntimeError("Injected failure for testing")

    if role == "researcher":
        selected, _result = run_researcher(event["articles"], run_id)
        return {**event, "stage": role, "articles": selected}
    if role == "summarizer":
        summary = run_summarizer(event["articles"], run_id)
        return {**event, "stage": role, "summaries": summary.model_dump()}
    if role == "reviewer":
        summary = SummaryResult.model_validate(event["summaries"])
        reviewed = run_reviewer(event["articles"], summary, run_id)
        if not reviewed.approved or reviewed.issues:
            raise ValueError(f"Review not approved: {reviewed.issues}")
        return {**event, "stage": role, "review": reviewed.model_dump()}
    if role == "report":
        if event.get("review", {}).get("approved") is not True:
            raise ValueError("Report blocked: review not approved")
        output = write_report(event)
        print(f"[Report] {output}", flush=True)
        return None
    raise ValueError(f"Unknown role {role}")


def commit_message(consumer, message):
    parts = consumer.commit(message=message, asynchronous=False)
    if not parts or any(p.error is not None for p in parts):
        raise RuntimeError("Kafka offset commit failed")


def run(role, once=False):
    from confluent_kafka import Consumer

    in_topic, out_topic, _ = PIPELINE[role]
    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": f"ai-news-lab-{role}-v2",
        "enable.auto.commit": False,
        "auto.offset.reset": "latest",
        "max.poll.interval.ms": 1800000,
    })

    def on_assign(_consumer, parts):
        print(f"[{role}] ready: {[(p.topic, p.partition) for p in parts]}", flush=True)

    consumer.subscribe([in_topic], on_assign=on_assign)
    idle_start = time.monotonic()
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                if once and time.monotonic() - idle_start > 60:
                    raise TimeoutError(f"No message for {role} in 60 seconds")
                continue
            idle_start = time.monotonic()
            if msg.error():
                raise RuntimeError(str(msg.error()))

            raw = msg.value() or b""
            payload_hash = digest(raw)
            run_id = "invalid-" + payload_hash[:12]
            started = time.monotonic()
            try:
                event = json.loads(raw)
                if (
                    isinstance(event, dict) 
                    and isinstance(event.get("run_id"), str)
                    and re.fullmatch(r"[A-Za-z0-9_-]{1,80}",
                 event["run_id"])
                 ):
                        run_id = event["run_id"]
            except (ValueError, UnicodeDecodeError):
                event = None

            try:
                if seen(run_id, role, payload_hash):
                    audit(run_id, role, "skipped", reason="already_processed")
                    commit_message(consumer, msg)
                    if once:
                        return
                    continue
            except (ValueError, sqlite3.Error) as exc:
                audit(run_id, role, "state_error", error=str(exc)[:200])
                raise

            success = False
            for attempt in range(1, 4):
                try:
                    result = process(role, event)
                    if out_topic:
                        publish(out_topic, result)
                    if event["backend"] == "mock" and os.getenv("KAFKA_TEST_CRASH_AFTER_PUBLISH") == role:
                        os._exit(77)  # test-only intentional crash
                    record_done(run_id, role, payload_hash)
                    audit(run_id, role, "success", attempt=attempt,
                          duration_ms=round((time.monotonic() - started) * 1000))
                    print(f"[{role}] success {run_id}", flush=True)
                    success = True
                    break
                except Exception as exc:  # noqa: BLE001 - isolate each failed message
                    audit(run_id, role, "attempt_failed", attempt=attempt,
                          error_type=type(exc).__name__, error=str(exc)[:200])
                    if attempt < 3:
                        time.sleep(attempt)
            if not success:
                failure = {
                    "event_version": 1,
                    "run_id": run_id,
                    "stage": role,
                    "source_topic": in_topic,
                    "error": "failed after 3 attempts; inspect audit log",
                    "payload_hash": payload_hash,
                    "original_payload_b64": base64.b64encode(raw).decode("ascii"),
                }
                publish("news.failed", failure)
                audit(run_id, role, "dlq_published", payload_hash=payload_hash)
                print(f"[{role}] sent to DLQ {run_id}", flush=True)
            # A failed commit must NOT re-run the stage or send it to DLQ.
            # On restart, the processed table suppresses duplicate work.
            commit_message(consumer, msg)
            if once:
                return
    except KeyboardInterrupt:
        print(f"[{role}] stopped", flush=True)
    finally:
        consumer.close()