from __future__ import annotations

import logging

import feedparser
import httpx

from ..config import Source
from ..models import Item, canonical_url

log = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
USER_AGENT = "infobot/0.1"


def _get(client: httpx.Client, url: str, params: dict | None = None) -> bytes | None:
    try:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as exc:
        log.warning("skipping %s: %s", url, exc)
        return None


def _entries_to_items(
    data: bytes,
    source_label: str,
    category: str,
    id_prefix: str | None = None,
    limit: int | None = None,
) -> list[Item]:
    parsed = feedparser.parse(data)
    label = source_label or parsed.feed.get("title", "feed")
    items: list[Item] = []
    for entry in parsed.entries[:limit]:
        link = entry.get("link", "")
        if not link:
            continue
        if id_prefix and entry.get("id"):
            item_id = f"{id_prefix}:{entry['id'].rsplit('/', 1)[-1]}"
        else:
            item_id = canonical_url(link)
        items.append(
            Item(
                id=item_id,
                url=link,
                title=entry.get("title", "(untitled)").strip(),
                source=label,
                category=category,
                published=entry.get("published", entry.get("updated", "")),
                excerpt=entry.get("summary", ""),
            )
        )
    return items


def fetch_rss(source: Source, client: httpx.Client) -> list[Item]:
    # Some feeds carry their entire archive (thousands of entries); cap to the
    # newest N so a newly added feed can't flood the channels.
    limit = source.options.get("max_entries_per_feed", 50)
    items: list[Item] = []
    for feed_url in source.options.get("feeds", []):
        data = _get(client, feed_url)
        if data is not None:
            items.extend(_entries_to_items(data, "", source.category, limit=limit))
    return items


def fetch_arxiv(source: Source, client: httpx.Client) -> list[Item]:
    items: list[Item] = []
    max_results = source.options.get("max_results", 25)
    for query in source.options.get("queries", []):
        data = _get(
            client,
            ARXIV_API,
            params={
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(max_results),
            },
        )
        if data is not None:
            label = f"arXiv {query.removeprefix('cat:')}"
            items.extend(_entries_to_items(data, label, source.category, id_prefix="arxiv"))
    return items
