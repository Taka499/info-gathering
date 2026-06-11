from __future__ import annotations

import argparse
import logging
from collections import Counter

from dotenv import load_dotenv

from . import config as config_mod
from . import fetchers, summarize
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="infobot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be posted instead of posting; do not mark items posted",
    )
    parser.add_argument("--no-llm", action="store_true", help="skip Claude summarization")
    parser.add_argument("--db", default="state/seen.db")
    parser.add_argument("--config", default="config/sources.yaml")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO; webhook URLs embed their secret
    # token in the path, so those logs must never reach CI output.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()  # local runs read ANTHROPIC_API_KEY/webhooks from .env; CI uses real env vars

    cfg = config_mod.load(args.config)
    store = Store(args.db)

    items = fetchers.fetch_all(cfg)
    new_items = store.filter_new(items)

    counts = Counter(item.category for item in new_items)
    print("  ".join(f"[{cat}] {counts.get(cat, 0)} new" for cat in cfg.categories))

    if not (args.no_llm or not cfg.llm.enabled):
        new_items = summarize.enrich(new_items, cfg)

    # Milestone 4 adds posting here. Until then every run prints the new
    # items, regardless of --dry-run.
    for item in new_items:
        print(f"[{item.category}] {item.title!r} ({item.source}) {item.url}")
        if item.summary:
            print(f"    {item.summary}")

    store.close()
    return 0
