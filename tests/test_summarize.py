import os

import pytest

from infobot import summarize
from infobot.config import Config, LLMConfig
from infobot.models import Item
from infobot.summarize import BatchVerdict, ItemVerdict


def make_config(max_items_per_call: int = 15) -> Config:
    return Config(
        categories=["ai-papers", "ai-news", "tech-news"],
        llm=LLMConfig(enabled=True, max_items_per_call=max_items_per_call),
        sources=[],
    )


def make_item(i: int, category: str = "tech-news") -> Item:
    return Item(
        id=f"test:{i}",
        url=f"https://example.com/{i}",
        title=f"title {i}",
        source="test",
        category=category,
        excerpt=f"excerpt {i}",
    )


@pytest.fixture
def no_real_client(monkeypatch):
    """enrich() constructs an Anthropic client; tests must never need a key."""
    monkeypatch.setattr(summarize.anthropic, "Anthropic", lambda: object())


def test_enrich_applies_summary_category_and_relevance(no_real_client, monkeypatch):
    verdict = BatchVerdict(
        items=[
            ItemVerdict(id="test:1", category="ai-news", summary="An AI story.", relevant=True),
            ItemVerdict(id="test:2", category="tech-news", summary="Spam.", relevant=False),
            ItemVerdict(id="test:3", category="not-a-category", summary="Odd cat.", relevant=True),
        ]
    )
    monkeypatch.setattr(summarize, "_summarize_batch", lambda c, cfg, batch: verdict)

    items = [make_item(1), make_item(2), make_item(3), make_item(4)]
    kept = summarize.enrich(items, make_config())

    assert [i.id for i in kept] == ["test:1", "test:3", "test:4"]
    assert kept[0].category == "ai-news"          # recategorized
    assert kept[0].summary == "An AI story."
    assert kept[1].category == "tech-news"        # invalid category ignored
    assert kept[2].summary == ""                  # id missing from verdict: fail open


def test_enrich_fails_open_on_api_error(no_real_client, monkeypatch):
    def boom(client, cfg, batch):
        raise RuntimeError("api down")

    monkeypatch.setattr(summarize, "_summarize_batch", boom)
    items = [make_item(1), make_item(2)]
    kept = summarize.enrich(items, make_config())
    assert kept == items
    assert all(i.summary == "" for i in kept)


def test_enrich_batches_by_max_items_per_call(no_real_client, monkeypatch):
    batches = []

    def record(client, cfg, batch):
        batches.append(len(batch))
        return BatchVerdict(items=[])

    monkeypatch.setattr(summarize, "_summarize_batch", record)
    summarize.enrich([make_item(i) for i in range(7)], make_config(max_items_per_call=3))
    assert batches == [3, 3, 1]


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs real API key")
def test_enrich_against_real_api():
    items = [
        Item(
            id="live:1",
            url="https://example.com/quantum",
            title="Researchers demonstrate error-corrected logical qubit",
            source="test",
            category="tech-news",
            excerpt="A research team reports a logical qubit whose error rate is "
            "below that of its physical qubits, a long-sought threshold.",
        )
    ]
    kept = summarize.enrich(items, make_config())
    assert len(kept) == 1
    assert kept[0].summary, "expected a non-empty summary from the live API"
