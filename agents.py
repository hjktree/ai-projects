
import hashlib
import json
import os
import time

from ollama import Client
from pydantic import BaseModel, Field

from common import ROOT, log_event

MODEL = os.getenv(
    "NEWS_MODEL", "qwen3:4b-instruct"
)
PROMPT_VERSION = "v1.0"

client = Client(
    host="http://localhost:11434",
    timeout=300,
)


# ---------- AI 응답 데이터 구조 ----------

class Pick(BaseModel):
    article_id: str
    score: int = Field(ge=0, le=15)
    reason: str


class ResearchResult(BaseModel):
    picks: list[Pick]


class NewsLine(BaseModel):
    article_id: str
    line: str


class SummaryResult(BaseModel):
    items: list[NewsLine]


class ReviewResult(BaseModel):
    approved: bool
    issues: list[str]


# ---------- 공통 AI 호출 ----------

def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def call_ai(role, schema, payload, run_id):
    prompt_path = ROOT / "prompts" / f"{role}.txt"

    system_prompt = prompt_path.read_text(
        encoding="utf-8-sig"
    )
    user_input = json.dumps(
        payload, ensure_ascii=False
    )

    started = time.perf_counter()

    try:
        response = client.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_input,
                },
            ],
            format=schema.model_json_schema(),
            options={"temperature": 0},
            keep_alive="5m",
        )

        output = response.message.content

        result = schema.model_validate_json(output)

        log_event(
            run_id,
            role,
            "success",
            tool="ollama.chat",
            model=MODEL,
            prompt_version=PROMPT_VERSION,
            prompt_hash=sha256(system_prompt),
            input_hash=sha256(user_input),
            output_hash=sha256(output),
            duration_ms=round(
                (time.perf_counter() - started) * 1000
            ),
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
        )

        return result

    except Exception as exc:
        log_event(
            run_id,
            role,
            "failed",
            tool="ollama.chat",
            model=MODEL,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        raise


# ---------- Python 결과 검증 ----------

def validate_picks(articles, picks, target):
    valid_ids = {a["id"] for a in articles}
    selected_ids = [p.article_id for p in picks]

    if len(selected_ids) != target:
        raise ValueError("선정 기사 수가 잘못되었습니다.")

    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("AI가 중복 기사를 선정했습니다.")

    if not set(selected_ids).issubset(valid_ids):
        raise ValueError("존재하지 않는 기사 ID가 포함됐습니다.")


def validate_summaries(articles, items):
    expected_ids = {a["id"] for a in articles}
    actual_ids = [item.article_id for item in items]

    if (
        len(actual_ids) != len(expected_ids)
        or set(actual_ids) != expected_ids
    ):
        raise ValueError("요약 기사 ID가 일치하지 않습니다.")

    for item in items:
        line = item.line.strip()

        if (
            not line
            or "\n" in line
            or len(line) > 250
        ):
            raise ValueError("요약 형식이 잘못되었습니다.")


# ---------- 역할별 AI ----------

def run_researcher(articles, run_id):
    target = min(5, len(articles))

    result = call_ai(
        "researcher",
        ResearchResult,
        {
            "target": target,
            "articles": articles,
        },
        run_id,
    )

    validate_picks(articles, result.picks, target)

    article_map = {a["id"]: a for a in articles}

    selected = [
        article_map[p.article_id]
        for p in result.picks
    ]

    return selected, result


def run_summarizer(selected, run_id):
    result = call_ai(
        "summarizer",
        SummaryResult,
        {"articles": selected},
        run_id,
    )

    validate_summaries(selected, result.items)

    return result


def run_reviewer(selected, summaries, run_id):
    result = call_ai(
        "reviewer",
        ReviewResult,
        {
            "original_articles": selected,
            "summaries": summaries.model_dump(),
        },
        run_id,
    )

    return result
