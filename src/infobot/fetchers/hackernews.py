from __future__ import annotations

import logging

import httpx

from ..config import Source
from ..models import Item, epoch_to_iso

log = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


def fetch_hackernews(source: Source, client: httpx.Client) -> list[Item]:
    min_score = source.options.get("min_score", 100)
    max_items = source.options.get("max_items", 100)

    resp = client.get(f"{HN_API}/topstories.json")
    resp.raise_for_status()
    ids = resp.json()[:max_items]

    items: list[Item] = []
    for story_id in ids:
        try:
            story = client.get(f"{HN_API}/item/{story_id}.json").json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("skipping HN item %s: %s", story_id, exc)
            continue
        if not story or story.get("type") != "story":
            continue
        # No "url" means an Ask/Show HN text post; skip those along with low scores.
        if story.get("score", 0) < min_score or "url" not in story:
            continue
        items.append(
            Item(
                id=f"hn:{story_id}",
                url=story["url"],
                title=story.get("title", "(untitled)"),
                source="Hacker News",
                category=source.category,
                published=epoch_to_iso(story.get("time")),
            )
        )
    return items
