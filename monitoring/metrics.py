
"""Pushgateway metrics for the local Kafka news pipeline."""

import os
import time

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway


def _set(registry, name, description, value):
    Gauge(name, description, registry=registry).set(value)


def _push(registry, job, grouping_key):
    gateway = os.getenv(
        "NEWS_PUSHGATEWAY_URL",
        "127.0.0.1:9091",
    )
    push_to_gateway(
        gateway,
        job=job,
        registry=registry,
        grouping_key=grouping_key,
        timeout=2,
    )


def push_worker_metrics(
    *,
    role,
    backend,
    success,
    worker_seconds,
    process_seconds=None,
    articles_collected=None,
    articles_selected=None,
):
    registry = CollectorRegistry()

    _set(
        registry,
        "news_worker_success",
        "Last committed worker result: 1=success, 0=DLQ",
        int(success),
    )

    _set(
        registry,
        "news_worker_duration_seconds",
        "Last worker processing duration including retries",
        worker_seconds,
    )

    _set(
        registry,
        "news_worker_last_finished_timestamp_seconds",
        "Last committed worker finish time",
        time.time(),
    )

    if role in {"researcher", "summarizer", "reviewer"} and process_seconds is not None:
        _set(
            registry,
            "news_ai_request_duration_seconds",
            "Last AI role process() duration in seconds",
            process_seconds,
        )

    if role == "researcher" and success:
        if articles_collected is not None:
            _set(
                registry,
                "news_articles_collected",
                "Articles entering the researcher worker",
                articles_collected,
            )

        if articles_selected is not None:
            _set(
                registry,
                "news_articles_selected",
                "Articles selected by the researcher",
                articles_selected,
            )

    _push(
        registry,
        job="ai_news_worker",
        grouping_key={"role": role, "backend": backend},
    )


def push_pipeline_metrics(*, backend, success):
    registry = CollectorRegistry()

    _set(
        registry,
        "news_job_success",
        "Last pipeline result: 1=report success, 0=DLQ",
        int(success),
    )

    _set(
        registry,
        "news_job_last_finished_timestamp_seconds",
        "Last pipeline success or DLQ failure time",
        time.time(),
    )

    _push(
        registry,
        job="ai_news_pipeline_status",
        grouping_key={"backend": backend},
    )

    if success:
        success_registry = CollectorRegistry()

        _set(
            success_registry,
            "news_last_success_timestamp_seconds",
            "Last successfully committed report time",
            time.time(),
        )

        _push(
            success_registry,
            job="ai_news_pipeline_last_success",
            grouping_key={"backend": backend},
        )
