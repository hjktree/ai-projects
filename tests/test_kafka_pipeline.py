from types import SimpleNamespace

import pytest

import agents
from messaging import kafka_runtime as runtime
from mock_runner import make_articles


@pytest.fixture
def event(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWS_AI_BACKEND", "mock")
    monkeypatch.setattr(runtime, "STATE", tmp_path / "state.sqlite3")
    monkeypatch.setattr(runtime, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setenv("KAFKA_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(agents, "log_event", lambda *a, **kw: None)
    return {"event_version": 1, "run_id": "unit-kafka-001",
            "stage": "collector", "backend": "mock", "articles": make_articles()}


def test_pipeline_without_kafka(event, tmp_path):
    for role in ("researcher", "summarizer", "reviewer"):
        event = runtime.process(role, event)
        assert event["stage"] == role
    runtime.process("report", event)
    path = tmp_path / "reports" / "unit-kafka-001.md"
    assert path.exists()
    assert "[MOCK]" in path.read_text(encoding="utf-8")


def test_reviewer_rejects(event, monkeypatch):
    event = runtime.process("researcher", event)
    event = runtime.process("summarizer", event)
    monkeypatch.setattr(runtime, "run_reviewer", lambda *args: SimpleNamespace(
        approved=False, issues=["test rejection"],
    ))
    with pytest.raises(ValueError, match="not approved"):
        runtime.process("reviewer", event)


def test_duplicate_and_conflicting_payload(event):
    sha = runtime.digest(b"original")
    assert not runtime.seen(event["run_id"], "researcher", sha)
    runtime.record_done(event["run_id"], "researcher", sha)
    assert runtime.seen(event["run_id"], "researcher", sha)
    with pytest.raises(ValueError, match="different payload"):
        runtime.seen(event["run_id"], "researcher", runtime.digest(b"different"))


def test_invalid_event(event):
    event["stage"] = "wrong"
    with pytest.raises(ValueError, match="version or stage"):
        runtime.process("researcher", event)


def test_mock_injected_failure(event, monkeypatch):
    monkeypatch.setenv("KAFKA_TEST_FAIL_ROLE", "researcher")
    with pytest.raises(RuntimeError, match="Injected"):
        runtime.process("researcher", event)