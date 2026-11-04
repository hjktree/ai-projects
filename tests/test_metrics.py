
from prometheus_client import generate_latest

from messaging import kafka_runtime
from monitoring import metrics


def test_worker_metrics(monkeypatch):
    calls = []

    def fake_push(gateway, job, registry, grouping_key, timeout):
        calls.append({
            "job": job,
            "grouping_key": grouping_key,
            "body": generate_latest(registry).decode(),
        })

    monkeypatch.setattr(metrics, "push_to_gateway", fake_push)

    metrics.push_worker_metrics(
        role="researcher",
        backend="mock",
        success=True,
        worker_seconds=2.0,
        process_seconds=1.5,
        articles_collected=20,
        articles_selected=5,
    )

    assert len(calls) == 1
    assert calls[0]["job"] == "ai_news_worker"
    assert calls[0]["grouping_key"]["role"] == "researcher"
    assert "news_worker_success 1.0" in calls[0]["body"]
    assert "news_ai_request_duration_seconds 1.5" in calls[0]["body"]
    assert "news_articles_collected 20.0" in calls[0]["body"]


def test_pipeline_success_metrics(monkeypatch):
    calls = []

    def fake_push(gateway, job, registry, grouping_key, timeout):
        calls.append({
            "job": job,
            "body": generate_latest(registry).decode(),
        })

    monkeypatch.setattr(metrics, "push_to_gateway", fake_push)

    metrics.push_pipeline_metrics(
        backend="mock",
        success=True,
    )

    assert len(calls) == 2
    assert "news_job_success 1.0" in calls[0]["body"]
    assert "news_last_success_timestamp_seconds" in calls[1]["body"]


def test_pipeline_failure_keeps_last_success(monkeypatch):
    calls = []

    def fake_push(gateway, job, registry, grouping_key, timeout):
        calls.append(job)

    monkeypatch.setattr(metrics, "push_to_gateway", fake_push)

    metrics.push_pipeline_metrics(
        backend="mock",
        success=False,
    )

    assert calls == ["ai_news_pipeline_status"]


def test_metrics_failure_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWS_METRICS_ENABLED", "1")
    monkeypatch.setattr(kafka_runtime, "LOG_DIR", tmp_path)

    def broken_push(*args, **kwargs):
        raise ConnectionError("Pushgateway unavailable")

    monkeypatch.setattr(metrics, "push_to_gateway", broken_push)

    kafka_runtime.metrics_hook(
        run_id="metrics-test-001",
        role="report",
        event={"backend": "mock", "articles": []},
        success=True,
        worker_seconds=1.0,
        process_seconds=0.5,
        selected_count=None,
    )

    log_file = tmp_path / "metrics-test-001.report.jsonl"
    assert log_file.exists()
    assert "metrics_failed" in log_file.read_text(encoding="utf-8")
