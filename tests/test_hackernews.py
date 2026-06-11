import httpx

from infobot.config import Source
from infobot.fetchers.hackernews import fetch_hackernews

STORIES = {
    1: {"id": 1, "type": "story", "score": 250, "title": "Big story",
        "url": "https://example.com/big", "time": 1780000000},
    2: {"id": 2, "type": "story", "score": 50, "title": "Small story",
        "url": "https://example.com/small", "time": 1780000000},
    3: {"id": 3, "type": "story", "score": 300, "title": "Ask HN: text post, no url",
        "time": 1780000000},
    4: {"id": 4, "type": "job", "score": 500, "title": "A job ad",
        "url": "https://example.com/job", "time": 1780000000},
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v0/topstories.json":
        return httpx.Response(200, json=list(STORIES))
    story_id = int(request.url.path.rsplit("/", 1)[-1].removesuffix(".json"))
    return httpx.Response(200, json=STORIES[story_id])


def test_hackernews_keeps_only_high_score_link_stories():
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    source = Source(
        kind="hackernews",
        category="tech-news",
        options={"min_score": 100, "max_items": 10},
    )
    items = fetch_hackernews(source, client)
    assert [i.id for i in items] == ["hn:1"]
    assert items[0].source == "Hacker News"
    assert items[0].url == "https://example.com/big"
    assert items[0].published.startswith("2026-")


def test_hackernews_respects_max_items():
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    source = Source(
        kind="hackernews",
        category="tech-news",
        options={"min_score": 0, "max_items": 1},
    )
    items = fetch_hackernews(source, client)
    assert [i.id for i in items] == ["hn:1"]
