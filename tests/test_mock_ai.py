import json

import pytest

from agents import (
    ResearchResult,
    ReviewResult,
    SummaryResult,
    validate_picks,
    validate_summaries,
)
from mock_ai import get_mock_response
from mock_runner import make_articles


def test_researcher():
    articles = make_articles()

    output = get_mock_response(
        "researcher",
        {"target": 5, "articles": articles},
    )

    result = ResearchResult.model_validate_json(
        output
    )

    validate_picks(articles, result.picks, 5)

    assert len(result.picks) == 5


def test_summarizer():
    articles = make_articles()[:5]

    output = get_mock_response(
        "summarizer",
        {"articles": articles},
    )

    result = SummaryResult.model_validate_json(
        output
    )

    validate_summaries(articles, result.items)

    assert len(result.items) == 5


def test_reviewer():
    articles = make_articles()[:5]

    summary_output = get_mock_response(
        "summarizer",
        {"articles": articles},
    )

    summaries = json.loads(summary_output)

    output = get_mock_response(
        "reviewer",
        {
            "original_articles": articles,
            "summaries": summaries,
        },
    )

    result = ReviewResult.model_validate_json(
        output
    )

    assert result.approved is True
    assert result.issues == []


def test_unknown_role():
    with pytest.raises(ValueError):
        get_mock_response("unknown", {})


def test_invalid_reviewer_input():
    articles = make_articles()[:5]

    output = get_mock_response(
        "reviewer",
        {
            "original_articles": articles,
            "summaries": {"items": []},
        },
    )

    result = ReviewResult.model_validate_json(
        output
    )

    assert result.approved is False
    assert result.issues