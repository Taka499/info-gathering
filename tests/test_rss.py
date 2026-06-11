from pathlib import Path

from infobot.fetchers.rss import _entries_to_items
from infobot.models import canonical_url

FIXTURES = Path(__file__).parent / "fixtures"


def test_arxiv_atom_parsing():
    data = (FIXTURES / "arxiv_sample.xml").read_bytes()
    items = _entries_to_items(data, "arXiv cs.AI", "ai-papers", id_prefix="arxiv")
    assert len(items) == 2
    first = items[0]
    assert first.id == "arxiv:2406.01234v1"
    assert first.title == "Scaling Laws for Imaginary Systems"
    assert first.category == "ai-papers"
    assert first.url == "http://arxiv.org/abs/2406.01234v1"
    assert first.published.startswith("2026-06-10")
    assert "scaling laws" in first.excerpt.lower()


def test_rss_uses_canonical_url_id_and_feed_title():
    data = (FIXTURES / "blog_sample.xml").read_bytes()
    items = _entries_to_items(data, "", "ai-news")
    assert len(items) == 1
    assert items[0].id == "https://example.com/post-1"  # utm params stripped, host lowercased
    assert items[0].source == "Example Blog"
    assert items[0].category == "ai-news"


def test_entry_limit_caps_archive_feeds():
    data = (FIXTURES / "arxiv_sample.xml").read_bytes()
    items = _entries_to_items(data, "arXiv cs.AI", "ai-papers", id_prefix="arxiv", limit=1)
    assert len(items) == 1


def test_canonical_url_keeps_meaningful_query_params():
    assert (
        canonical_url("https://News.example.com/a?id=7&utm_campaign=x#frag")
        == "https://news.example.com/a?id=7"
    )
