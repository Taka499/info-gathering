from __future__ import annotations

import html
import logging
import re

import feedparser
import httpx

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

# Reddit's JSON API returns "403 Blocked" to anonymous clients (any User-Agent),
# but the RSS/Atom endpoint of the same listings remains open. RSS entries carry
# no scores, so the top-of-timeframe listing itself is the quality filter here.
REDDIT_RSS = "https://www.reddit.com/r/{sub}/{listing}/.rss"

# Each entry's HTML body contains '<a href="EXTERNAL_URL">[link]</a>'; for self
# posts that href is the comments page itself.
_LINK_RE = re.compile(r'<a href="([^"]+)">\s*\[link\]')


def fetch_reddit(source: Source, client: httpx.Client) -> list[Item]:
    listing = source.options.get("listing", "top")
    timeframe = source.options.get("timeframe", "day")
    max_items = source.options.get("max_items_per_subreddit", 25)

    items: list[Item] = []
    for sub in source.options.get("subreddits", []):
        try:
            resp = client.get(
                REDDIT_RSS.format(sub=sub, listing=listing),
                params={"t": timeframe},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("skipping r/%s: %s", sub, exc)
            continue
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries[:max_items]:
            comments_url = entry.get("link", "")
            content = entry.get("content", [{}])[0].get("value", entry.get("summary", ""))
            match = _LINK_RE.search(content)
            if not match:
                continue
            url = html.unescape(match.group(1))  # hrefs arrive HTML-escaped ("&amp;")
            if url == comments_url:
                continue  # self post
            items.append(
                Item(
                    id=f"reddit:{entry.get('id', comments_url)}",
                    url=url,
                    title=entry.get("title", "(untitled)"),
                    source=f"r/{sub}",
                    category=source.category,
                    published=entry.get("updated", ""),
                )
            )
    return items
