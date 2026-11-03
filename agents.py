import hashlib
import json
import os
import time

from ollama import Client
from pydantic import BaseModel, Field

from common import ROOT, log_event

# ---------- AI 실행 환경 설정 ----------

MODEL = os.getenv(
    "NEWS_MODEL",
    "qwen3:4b-instruct",
)

PROMPT_VERSION = "v1.0"
MOCK_MODEL = "mock-fixture-v1"

# 기본값은 기존 실제 Ollama 모델
# Mock AI 사용 시 NEWS_AI_BACKEND=mock 지정

client = Client(
    host=os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    ),
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


# ---------- 공통 유틸리티 ----------

def sha256(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


# ---------- 공통 AI 호출 ----------

def call_ai(role, schema, payload, run_id):

    # 1. AI 실행 방식 선택
    backend = os.getenv(
        "NEWS_AI_BACKEND",
        "ollama",
    ).strip().lower()

    if backend == "ollama":
        tool_name = "ollama.chat"
        model_name = MODEL

    elif backend == "mock":
        tool_name = "mock.fixture"
        model_name = MOCK_MODEL

    else:
        tool_name = "ai.backend"
        model_name = "unknown"

    started = time.perf_counter()

    prompt_hash = None
    input_hash = None

    try:
        # 2. 지원하는 실행 방식인지 확인
        if backend not in {"ollama", "mock"}:
            raise ValueError(
                f"지원하지 않는 AI backend: {backend}"
            )

        # 3. 역할별 프롬프트 읽기
        prompt_path = (
            ROOT / "prompts" / f"{role}.txt"
        )

        system_prompt = prompt_path.read_text(
            encoding="utf-8-sig"
        )

        # 4. 입력 데이터 JSON 직렬화
        user_input = json.dumps(
            payload,
            ensure_ascii=False,
        )

        # 5. 재현성을 위한 해시 계산
        prompt_hash = sha256(system_prompt)
        input_hash = sha256(user_input)

        input_tokens = None
        output_tokens = None

        # 6-A. 기존 실제 Ollama 실행
        if backend == "ollama":

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
                options={
                    "temperature": 0, "num_ctx": 8192,
                }, 
                keep_alive="5m",
            )

            output = response.message.content

            input_tokens = response.prompt_eval_count
            output_tokens = response.eval_count

        # 6-B. Mock AI 실행
        elif backend == "mock":

            # 다음 Phase에서 mock_ai.py 생성
            # Mock 모드에서만 불러오므로 기존
            # Ollama 실행에는 영향을 주지 않음
            from mock_ai import get_mock_response

            output = get_mock_response(
                role,
                payload,
            )

        # 7. AI 출력은 JSON 문자열이어야 함
        if not isinstance(output, str):
            raise TypeError(
                "AI 출력은 JSON 문자열이어야 합니다."
            )

        # 8. 기존 Pydantic 검증 유지
        result = schema.model_validate_json(
            output
        )

        # 9. 실행 시간 계산
        duration_ms = round(
            (time.perf_counter() - started) * 1000
        )

        # 10. 성공 로그 기록
        log_event(
            run_id,
            role,
            "success",
            backend=backend,
            tool=tool_name,
            model=model_name,
            prompt_version=PROMPT_VERSION,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            output_hash=sha256(output),
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        return result

    # 11. 실패 로그 기록 후 예외 전달
    except Exception as exc:

        duration_ms = round(
            (time.perf_counter() - started) * 1000
        )

        log_event(
            run_id,
            role,
            "failed",
            backend=backend,
            tool=tool_name,
            model=model_name,
            prompt_version=PROMPT_VERSION,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )

        raise


# ---------- Python 결과 검증 ----------

def validate_picks(articles, picks, target):

    valid_ids = {
        article["id"] for article in articles
    }

    selected_ids = [
        pick.article_id for pick in picks
    ]

    if len(selected_ids) != target:
        raise ValueError(
            "선정 기사 수가 잘못되었습니다."
        )

    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError(
            "AI가 중복 기사를 선정했습니다."
        )

    if not set(selected_ids).issubset(valid_ids):
        raise ValueError(
            "존재하지 않는 기사 ID가 포함됐습니다."
        )


def validate_summaries(articles, items):

    expected_ids = {
        article["id"] for article in articles
    }

    actual_ids = [
        item.article_id for item in items
    ]

    if (
        len(actual_ids) != len(expected_ids)
        or set(actual_ids) != expected_ids
    ):
        raise ValueError(
            "요약 기사 ID가 일치하지 않습니다."
        )

    for item in items:

        line = item.line.strip()

        if (
            not line
            or "\n" in line
            or len(line) > 250
        ):
            raise ValueError(
                "요약 형식이 잘못되었습니다."
            )


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

    validate_picks(
        articles,
        result.picks,
        target,
    )

    article_map = {
        article["id"]: article
        for article in articles
    }

    selected = [
        article_map[pick.article_id]
        for pick in result.picks
    ]

    return selected, result


def run_summarizer(selected, run_id):

    result = call_ai(
        "summarizer",
        SummaryResult,
        {
            "articles": selected,
        },
        run_id,
    )

    validate_summaries(
        selected,
        result.items,
    )

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