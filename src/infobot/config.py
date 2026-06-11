from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = "claude-opus-4-8"
    max_items_per_call: int = 15


@dataclass
class Source:
    kind: str
    category: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    categories: list[str]
    llm: LLMConfig
    sources: list[Source]


def load(path: str = "config/sources.yaml") -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    sources = []
    for entry in raw.get("sources", []):
        entry = dict(entry)
        kind = entry.pop("kind")
        category = entry.pop("category")
        sources.append(Source(kind=kind, category=category, options=entry))

    return Config(
        categories=list(raw["categories"]),
        llm=LLMConfig(**raw.get("llm", {})),
        sources=sources,
    )
