
import agents
import mock_runner


def test_mock_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "NEWS_AI_BACKEND", "mock"
    )

    events = []

    def capture_event(*args, **kwargs):
        events.append((args, kwargs))

    monkeypatch.setattr(
        agents, "log_event", capture_event
    )

    monkeypatch.setattr(
        mock_runner, "log_event", capture_event
    )

    def forbidden_chat(*args, **kwargs):
        raise AssertionError(
            "Ollama must not be called"
        )

    monkeypatch.setattr(
        agents.client, "chat", forbidden_chat
    )

    report = mock_runner.run_mock_pipeline(
        report_dir=tmp_path
    )

    # 보고서 파일 확인
    assert report.exists()
    assert report.name.startswith("mock-")
    assert report.suffix == ".md"

    content = report.read_text(
        encoding="utf-8"
    )

    # 보고서 내용 확인
    assert "[MOCK]" in content
    assert "[가상] 기준금리 동결" in content
    assert "실제 AI 뉴스 분석 결과가 아닙니다" in content

    # 역할별 실행 성공 확인
    stages = {
        args[1]
        for args, _ in events
        if args[2] == "success"
    }

    assert {
        "researcher",
        "summarizer",
        "reviewer",
        "mock_pipeline",
    }.issubset(stages)

    # Prompt 및 Tool Logging 확인
    for args, kwargs in events:
        if args[1] in {
            "researcher",
            "summarizer",
            "reviewer",
        }:
            assert kwargs["backend"] == "mock"
            assert kwargs["tool"] == "mock.fixture"
            assert kwargs["prompt_hash"]
            assert kwargs["input_hash"]
            assert kwargs["output_hash"]


def test_mock_requires_backend(monkeypatch):
    monkeypatch.setenv(
        "NEWS_AI_BACKEND", "ollama"
    )

    try:
        mock_runner.run_mock_pipeline()
    except RuntimeError as exc:
        assert "NEWS_AI_BACKEND=mock" in str(exc)
    else:
        raise AssertionError(
            "Ollama mode must be rejected"
        )
