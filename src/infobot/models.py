from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class Item:
    id: str           # stable dedup key, e.g. "hn:42421234", "arxiv:2406.01234v1", or canonical URL
    url: str
    title: str
    source: str       # human label, e.g. "Hacker News", "arXiv cs.CL", feed title
    category: str     # one of the configured categories
    published: str = ""  # ISO 8601 UTC if known, else ""
    excerpt: str = ""    # raw feed summary / first paragraph, pre-LLM
    summary: str = ""    # filled by summarize.enrich()


def canonical_url(url: str) -> str:
    """Normalize a URL for use as a dedup key: lowercase scheme/host, drop fragment and utm_* params."""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )
