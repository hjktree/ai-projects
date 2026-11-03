"""Publish one news batch to Kafka, without modifying the original runner."""
import argparse
import os
import uuid

from messaging.kafka_runtime import audit, publish


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("mock", "ollama"), default="mock")
    parser.add_argument("--run-id")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 5:
        raise ValueError("--repeat must be 1..5")
    run_id = args.run_id or "kafka-" + uuid.uuid4().hex[:12]
    os.environ["NEWS_AI_BACKEND"] = args.backend

    if args.backend == "mock":
        from mock_runner import make_articles
        articles = make_articles()
    else:
        from collector import collect_news
        # Match this invocation with the actual collector.py before live use.
        articles = collect_news(run_id, limit=20)
    if not isinstance(articles, list) or not articles:
        raise RuntimeError("Collector did not return a nonempty list")

    event = {"event_version": 1, "run_id": run_id,
             "stage": "collector", "backend": args.backend, "articles": articles}
    for _ in range(args.repeat):
        publish("news.raw", event)
    audit(run_id, "collector", "success", backend=args.backend,
          article_count=len(articles), repeated=args.repeat)
    print(f"[collector] published {run_id} ({len(articles)} articles)")


if __name__ == "__main__":
    main()