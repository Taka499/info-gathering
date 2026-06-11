from pathlib import Path

import httpx

from infobot.config import Source
from infobot.fetchers.reddit import fetch_reddit

FIXTURE = (Path(__file__).parent / "fixtures" / "reddit_sample.xml").read_bytes()


def _handler(request: httpx.Request) -> httpx.Response:
    # Reddit blocks default user agents; the bot must always send its own.
    assert "infobot" in request.headers["user-agent"]
    return httpx.Response(200, content=FIXTURE, headers={"content-type": "application/atom+xml"})


def _source(subreddits: list[str]) -> Source:
    return Source(
        kind="reddit",
        category="tech-news",
        options={"subreddits": subreddits, "listing": "top", "timeframe": "day"},
    )


def test_reddit_keeps_external_links_and_skips_self_posts():
    client = httpx.Client(
        transport=httpx.MockTransport(_handler),
        headers={"User-Agent": "infobot/0.1"},
    )
    items = fetch_reddit(_source(["programming"]), client)
    assert [i.id for i in items] == ["reddit:t3_abc123"]
    # the href arrives HTML-escaped in the Atom body; it must be unescaped
    assert items[0].url == "https://example.com/article?a=1&b=2"
    assert items[0].source == "r/programming"
    assert items[0].published.startswith("2026-06-10")


def test_reddit_survives_a_failing_subreddit():
    def handler(request: httpx.Request) -> httpx.Response:
        if "/r/down/" in request.url.path:
            return httpx.Response(403)
        return httpx.Response(200, content=FIXTURE)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "infobot/0.1"},
    )
    items = fetch_reddit(_source(["down", "programming"]), client)
    assert [i.id for i in items] == ["reddit:t3_abc123"]
