
import calendar
import hashlib
import re
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
from bs4 import BeautifulSoup

from common import log_event

FEEDS = {
    "경제": "https://www.newsis.com/RSS/economy.xml",
    "금융": "https://www.newsis.com/RSS/bank.xml",
}


def clean_html(value):
    return BeautifulSoup(
        value or "", "html.parser"
    ).get_text(" ", strip=True)


def collect_news(run_id, limit=20):
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    collected = []
    seen_urls = set()
    seen_titles = set()

    with httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "PersonalNewsBriefBot/1.0"},
    ) as client:

        for category, url in FEEDS.items():
            try:
                response = client.get(url)
                response.raise_for_status()

                feed = feedparser.parse(response.content)

                if not feed.entries:
                    raise ValueError("RSS entries가 없습니다.")

                log_event(
                    run_id, "collector", "success",
                    tool="httpx.get",
                    category=category,
                    http_status=response.status_code,
                    entry_count=len(feed.entries),
                )

                for entry in feed.entries:
                    time_data = (
                        entry.get("published_parsed")
                        or entry.get("updated_parsed")
                    )

                    if not time_data:
                        continue

                    published = datetime.fromtimestamp(
                        calendar.timegm(time_data),
                        tz=UTC,
                    )

                    if published < cutoff:
                        continue

                    title = clean_html(entry.get("title", ""))
                    link = entry.get("link", "").strip()
                    summary = clean_html(
                        entry.get("summary", "")
                    )[:200]

                    if not title or not link or not summary:
                        continue

                    if not link.startswith(("http://", "https://")):
                        continue

                    normalized_title = re.sub(
                        r"\W+", "", title.lower()
                    )

                    if (
                        link in seen_urls
                        or normalized_title in seen_titles
                    ):
                        continue

                    seen_urls.add(link)
                    seen_titles.add(normalized_title)

                    collected.append({
                        "id": hashlib.sha256(
                            link.encode("utf-8")
                        ).hexdigest()[:12],
                        "category": category,
                        "source": "뉴시스",
                        "title": title,
                        "snippet": summary,
                        "url": link,
                        "published_at": published.isoformat(),
                    })

            except Exception as exc:  # noqa: BLE001
                log_event(
                    run_id,
                    "collector",
                    "failed",
                    tool="httpx.get",
                    category=category,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

    collected.sort(
        key=lambda x: x["published_at"],
        reverse=True,
    )

    if not collected:
        raise RuntimeError(
            "최근 24시간 내 수집 가능한 경제 뉴스가 없습니다."
        )

    return collected[:limit]
