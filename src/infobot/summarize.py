from __future__ import annotations

import logging

import anthropic
from pydantic import BaseModel

from .config import Config
from .models import Item

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You curate a personal tech-news digest. You receive a batch of items (id, title, \
source, default_category, url, excerpt) and return a verdict for every input id.

For each item:
- category: the best-fitting category among: {categories}. Keep the default \
unless another category clearly fits better (e.g. an AI story fetched from a \
general tech source belongs in an AI category).
- summary: 2-3 plain, factual sentences a busy reader can skim. State what is \
new or claimed, not that "this article discusses" something. If the excerpt is \
empty, summarize what the title and source imply, conservatively.
- relevant: false only for spam, pure marketing, or content-free posts. When in \
doubt, true.
"""


class ItemVerdict(BaseModel):
    id: str
    category: str
    summary: str
    relevant: bool


class BatchVerdict(BaseModel):
    items: list[ItemVerdict]


def _render_batch(items: list[Item]) -> str:
    blocks = []
    for item in items:
        blocks.append(
            "<item>\n"
            f"  id: {item.id}\n"
            f"  title: {item.title}\n"
            f"  source: {item.source}\n"
            f"  default_category: {item.category}\n"
            f"  url: {item.url}\n"
            f"  excerpt: {item.excerpt[:800]}\n"
            "</item>"
        )
    return "Items to summarize and categorize:\n\n" + "\n".join(blocks)


def _summarize_batch(
    client: anthropic.Anthropic, config: Config, items: list[Item]
) -> BatchVerdict | None:
    response = client.messages.parse(
        model=config.llm.model,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT.format(categories=", ".join(config.categories)),
        messages=[{"role": "user", "content": _render_batch(items)}],
        output_format=BatchVerdict,
    )
    return response.parsed_output


def enrich(items: list[Item], config: Config) -> list[Item]:
    """Set .summary/.category on items via Claude and drop irrelevant ones.

    Fails open: on any per-batch failure (API error, refusal, missing id in
    the response) the affected items keep their defaults — raw excerpt and
    source category — rather than being lost.
    """
    if not items:
        return items

    client = anthropic.Anthropic()
    kept: list[Item] = []
    size = config.llm.max_items_per_call
    for start in range(0, len(items), size):
        batch = items[start : start + size]
        try:
            verdict = _summarize_batch(client, config, batch)
        except Exception as exc:
            log.warning("summarization failed for batch at %d, posting raw: %s", start, exc)
            kept.extend(batch)
            continue
        if verdict is None:
            log.warning("no parsed output for batch at %d, posting raw", start)
            kept.extend(batch)
            continue
        by_id = {v.id: v for v in verdict.items}
        for item in batch:
            v = by_id.get(item.id)
            if v is None:
                kept.append(item)
                continue
            if not v.relevant:
                log.info("dropping irrelevant item %s (%s)", item.id, item.title)
                continue
            item.summary = v.summary
            if v.category in config.categories:
                item.category = v.category
            kept.append(item)
    return kept
