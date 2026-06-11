from __future__ import annotations

import logging

import httpx

from ..config import Config
from ..models import Item
from . import hackernews, reddit, rss

log = logging.getLogger(__name__)

_DISPATCH = {
    "rss": rss.fetch_rss,
    "arxiv": rss.fetch_arxiv,
    "hackernews": hackernews.fetch_hackernews,
    "reddit": reddit.fetch_reddit,
}


def fetch_all(config: Config) -> list[Item]:
    """Fetch every configured source. Per-source failures are logged, never raised."""
    items: list[Item] = []
    with httpx.Client(
        timeout=10.0,
        headers={"User-Agent": rss.USER_AGENT},
        follow_redirects=True,
    ) as client:
        for source in config.sources:
            fetch = _DISPATCH.get(source.kind)
            if fetch is None:
                log.warning("unknown source kind %r, skipping", source.kind)
                continue
            try:
                fetched = fetch(source, client)
            except Exception:
                log.exception("source %r failed, continuing", source.kind)
                continue
            log.info("%s: fetched %d items", source.kind, len(fetched))
            items.extend(fetched)
    return items
