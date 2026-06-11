from __future__ import annotations

import logging
import os
import time

import httpx

from .config import Config
from .models import Item

log = logging.getLogger(__name__)

# Discord allows at most 10 embeds per webhook request; reuse the same batch
# size for Slack digests to keep messages skimmable.
_BATCH = 10


def _env_name(platform: str, category: str) -> str:
    return f"{platform.upper()}_WEBHOOK_{category.upper().replace('-', '_')}"


def _webhooks(platform: str, categories: list[str]) -> dict[str, str]:
    """Resolve category -> webhook URL from the environment. Missing = off."""
    hooks: dict[str, str] = {}
    for category in categories:
        url = os.environ.get(_env_name(platform, category))
        if url:
            hooks[category] = url
        else:
            log.info(
                "%s not set; %s/%s posting is off",
                _env_name(platform, category), platform, category,
            )
    return hooks


def _discord_payload(items: list[Item]) -> dict:
    return {
        "embeds": [
            {
                "title": item.title[:256],
                "url": item.url,
                "description": item.summary[:2048],
                "footer": {"text": item.source},
            }
            for item in items
        ]
    }


def _slack_payload(items: list[Item]) -> dict:
    lines = [
        f"*<{item.url}|{item.title}>* ({item.source})\n{item.summary}".rstrip()
        for item in items
    ]
    return {"text": "\n\n".join(lines)}


_RENDERERS = {"discord": _discord_payload, "slack": _slack_payload}


def _post(client: httpx.Client, platform: str, webhook_url: str, payload: dict) -> bool:
    for attempt in (1, 2):
        try:
            resp = client.post(webhook_url, json=payload)
        except httpx.HTTPError as exc:
            log.warning("%s post failed: %s", platform, exc)
            return False
        if resp.status_code == 429 and attempt == 1:
            # Discord puts retry_after (seconds) in the JSON body; Slack uses
            # the Retry-After header.
            try:
                delay = float(resp.json().get("retry_after", 1.0))
            except ValueError:
                delay = float(resp.headers.get("retry-after", 1))
            log.info("%s rate limited; retrying in %.1fs", platform, delay)
            time.sleep(delay)
            continue
        if resp.is_success:
            return True
        log.warning("%s post failed: HTTP %d", platform, resp.status_code)
        return False
    return False


def post_all(
    items: list[Item],
    config: Config,
    dry_run: bool,
    client: httpx.Client | None = None,
) -> list[Item]:
    """Post items to every configured platform/category webhook.

    Returns the items that were successfully posted on at least one platform
    (only those get marked posted in the store). In dry-run mode, prints what
    would go where -- for every platform, configured or not -- and posts nothing.
    """
    by_category: dict[str, list[Item]] = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)

    hooks = {} if dry_run else {p: _webhooks(p, config.categories) for p in _RENDERERS}

    posted: set[str] = set()
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=10.0)
    try:
        for platform in _RENDERERS:
            for category, cat_items in by_category.items():
                if dry_run:
                    print(f"[dry-run] {platform}/#{category}: {len(cat_items)} item(s)")
                    for item in cat_items:
                        print(f"  - {item.title} ({item.source}) {item.url}")
                    continue
                webhook_url = hooks[platform].get(category)
                if webhook_url is None:
                    continue
                for start in range(0, len(cat_items), _BATCH):
                    batch = cat_items[start : start + _BATCH]
                    payload = _RENDERERS[platform](batch)
                    if _post(client, platform, webhook_url, payload):
                        posted.update(item.id for item in batch)
    finally:
        if own_client:
            client.close()
    return [item for item in items if item.id in posted]
