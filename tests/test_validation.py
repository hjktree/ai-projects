
import pytest

from agents import (
    NewsLine,
    Pick,
    validate_picks,
    validate_summaries,
)

ARTICLES = [
    {"id": "N001", "title": "경제 기사 1"},
    {"id": "N002", "title": "경제 기사 2"},
]


def test_valid_selection():
    picks = [
        Pick(article_id="N001", score=15, reason="중요"),
        Pick(article_id="N002", score=12, reason="중요"),
    ]

    validate_picks(ARTICLES, picks, target=2)


def test_hallucinated_article_id():
    picks = [
        Pick(article_id="N999", score=15, reason="중요"),
        Pick(article_id="N002", score=12, reason="중요"),
    ]

    with pytest.raises(ValueError):
        validate_picks(ARTICLES, picks, target=2)


def test_duplicate_selection():
    picks = [
        Pick(article_id="N001", score=15, reason="중요"),
        Pick(article_id="N001", score=12, reason="중요"),
    ]

    with pytest.raises(ValueError):
        validate_picks(ARTICLES, picks, target=2)


def test_summary_missing_article():
    items = [
        NewsLine(article_id="N001", line="요약 결과")
    ]

    with pytest.raises(ValueError):
        validate_summaries(ARTICLES, items)


def test_invalid_summary_format():
    items = [
        NewsLine(article_id="N001", line="정상적인 요약"),
        NewsLine(
            article_id="N002",
            line="첫 문장\n두 번째 문장",
        ),
    ]

    with pytest.raises(ValueError):
        validate_summaries(ARTICLES, items)
