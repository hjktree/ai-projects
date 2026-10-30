import json


def get_mock_response(role, payload):
    if role == "researcher":
        articles = payload["articles"]
        target = payload["target"]

        if not 0 < target <= len(articles):
            raise ValueError("Invalid research target")

        result = {
            "picks": [
                {
                    "article_id": article["id"],
                    "score": 15 - index,
                    "reason": "Mock 뉴스 선정 테스트",
                }
                for index, article in enumerate(
                    articles[:target]
                )
            ]
        }

    elif role == "summarizer":
        result = {
            "items": [
                {
                    "article_id": article["id"],
                    "line": (
                        "[MOCK] "
                        + article["title"].replace("\n", " ")
                    )[:250],
                }
                for article in payload["articles"]
            ]
        }

    elif role == "reviewer":
        articles = payload["original_articles"]
        summaries = payload["summaries"]["items"]

        expected_ids = [
            article["id"] for article in articles
        ]

        actual_ids = [
            item["article_id"] for item in summaries
        ]

        valid = (
            len(actual_ids) == len(expected_ids)
            and actual_ids == expected_ids
            and all(
                item["line"].strip()
                for item in summaries
            )
        )

        result = {
            "approved": valid,
            "issues": [] if valid else [
                "기사와 요약 데이터가 일치하지 않습니다."
            ],
        }

    else:
        raise ValueError(
            f"Unsupported AI role: {role}"
        )

    return json.dumps(
        result,
        ensure_ascii=False,
    )