
import json
import sys
from datetime import datetime, timedelta, timezone

from agents import (
    MODEL,
    run_researcher,
    run_reviewer,
    run_summarizer,
)
from collector import collect_news
from common import ROOT, log_event

KST = timezone(timedelta(hours=9))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_report(selected, summaries, now):
    article_map = {a["id"]: a for a in selected}

    lines = [
        f"# 경제 뉴스 브리핑 — {now:%Y-%m-%d}",
        "",
        "최근 24시간 RSS 자료를 기준으로 작성했습니다.",
        "기사 전문이 아닌 RSS 제공 요약에 근거합니다.",
        "",
        "## 주요 뉴스",
        "",
    ]

    for index, item in enumerate(summaries.items, 1):
        article = article_map[item.article_id]

        lines.append(
            f"{index}. {item.line} "
            f"— [원문]({article['url']})"
        )

    lines += [
        "",
        "## 수집 정보",
        "",
    ]

    for article in selected:
        lines.append(
            f"- {article['title']} "
            f"({article['source']}, "
            f"{article['published_at']})"
        )

    return "\n".join(lines) + "\n"


def main():
    now = datetime.now(KST)

    run_id = now.strftime("%Y%m%d-%H%M%S")
    report_path = (
        ROOT / "reports" /
        f"{now:%Y-%m-%d}.md"
    )

    collect_only = "--collect-only" in sys.argv

    if report_path.exists() and not collect_only:
        print("오늘 보고서가 이미 존재합니다.")
        log_event(
            run_id, "pipeline", "skipped",
            reason="report_exists",
        )
        return

    log_event(
        run_id, "pipeline", "started",
        model=MODEL,
    )

    try:
        # 1. RSS 뉴스 수집
        articles = collect_news(run_id, limit=10)

        save_json(
            ROOT / "data" / f"{run_id}_articles.json",
            articles,
        )

        print(f"수집된 기사: {len(articles)}개")

        if collect_only:
            for article in articles[:5]:
                print(
                    article["title"],
                    article["url"],
                    sep="\n",
                )
                print()
            return

        # 2. Researcher AI
        selected, research = run_researcher(
            articles, run_id
        )
        print(f"AI 선정 기사: {len(selected)}개")

        # 3. Summarizer AI
        summaries = run_summarizer(
            selected, run_id
        )

        # 4. Reviewer AI
        review = run_reviewer(
            selected, summaries, run_id
        )

        # 5. 결과 추적 자료 저장
        trace = {
            "run_id": run_id,
            "model": MODEL,
            "selected_articles": selected,
            "research": research.model_dump(),
            "summaries": summaries.model_dump(),
            "review": review.model_dump(),
        }

        save_json(
            ROOT / "data" / f"{run_id}_trace.json",
            trace,
        )

        # 6. AI 검토 결과 확인
        if not review.approved or review.issues:
            raise RuntimeError(
                "Reviewer 검토 실패: "
                + "; ".join(review.issues)
            )

        # 7. 최종 브리핑 저장
        report = build_report(
            selected, summaries, now
        )

        report_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        report_path.write_text(
            report, encoding="utf-8"
        )

        log_event(
            run_id, "pipeline", "success",
            report=str(report_path),
            selected_count=len(selected),
        )

        print("최종 보고서 생성 완료")
        print(report_path)

    except Exception as exc:
        log_event(
            run_id, "pipeline", "failed",
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        raise


if __name__ == "__main__":
    main()
