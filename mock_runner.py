import os
import uuid
from pathlib import Path

from agents import (
    run_researcher,
    run_reviewer,
    run_summarizer,
)
from common import ROOT, log_event

TITLES = [
    "기준금리 동결",
    "은행 대출금리 조정",
    "반도체 수출 증가",
    "원달러 환율 변동",
    "소비자물가 상승률 둔화",
    "예금금리 변경",
    "국제 유가 변동",
    "제조업 생산 증가",
    "기업 투자 확대",
    "금융시장 변동성 확대",
]


def make_articles():
    return [
        {
            "id": f"MOCK{i:03d}",
            "title": f"[가상] {title}",
            "category": "경제",
            "source": "MOCK",
            "snippet": f"{title} 테스트 기사",
            "url": f"https://example.invalid/{i}",
            "published_at": "2026-10-29T08:00:00+09:00",
        }
        for i, title in enumerate(TITLES, start=1)
    ]


def run_mock_pipeline(report_dir=None):
    backend = os.getenv(
        "NEWS_AI_BACKEND", "ollama"
    ).strip().lower()

    if backend != "mock":
        raise RuntimeError(
            "NEWS_AI_BACKEND=mock required"
        )

    run_id = "mock-" + uuid.uuid4().hex[:12]

    output_dir = (
        Path(report_dir)
        if report_dir is not None
        else ROOT / "reports"
    )

    try:
        articles = make_articles()

        selected, research = run_researcher(
            articles, run_id
        )
        print("[Researcher] success")

        summaries = run_summarizer(
            selected, run_id
        )
        print("[Summarizer] success")

        review = run_reviewer(
            selected, summaries, run_id
        )

        if not review.approved or review.issues:
            raise RuntimeError(
                "Mock reviewer rejected result"
            )

        print("[Reviewer] success")

        summary_map = {
            item.article_id: item.line
            for item in summaries.items
        }

        lines = [
            "# [MOCK] 경제 뉴스 브리핑",
            "",
            "**실제 AI 뉴스 분석 결과가 아닙니다.**",
            "",
            f"Run ID: {run_id}",
            "Backend: mock",
            "",
        ]

        for i, article in enumerate(
            selected, start=1
        ):
            lines.extend([
                f"## {i}. {article['title']}",
                "",
                summary_map[article["id"]],
                "",
            ])

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        report_path = output_dir / f"{run_id}.md"

        report_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        log_event(
            run_id,
            "mock_pipeline",
            "success",
            backend="mock",
            tool="mock.runner",
            model="mock-fixture-v1",
            article_count=len(articles),
            selected_count=len(research.picks),
        )

        print(f"Report: {report_path}")

        return report_path

    except Exception as exc: 
        log_event(
            run_id,
            "mock_pipeline",
            "failed",
            backend="mock",
            tool="mock.runner",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise


if __name__ == "__main__":
    run_mock_pipeline()