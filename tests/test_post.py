import httpx

from infobot import post
from infobot.config import Config, LLMConfig
from infobot.models import Item


def make_config() -> Config:
    return Config(
        categories=["ai-news", "tech-news"],
        llm=LLMConfig(),
        sources=[],
    )


def make_item(i: int, category: str = "tech-news") -> Item:
    return Item(
        id=f"test:{i}",
        url=f"https://example.com/{i}",
        title=f"title {i}",
        source="test",
        category=category,
        summary=f"summary {i}",
    )


def test_discord_payload_shape_and_truncation():
    item = make_item(1)
    item.title = "x" * 300
    payload = post._discord_payload([item])
    embed = payload["embeds"][0]
    assert len(embed["title"]) == 256
    assert embed["url"] == "https://example.com/1"
    assert embed["description"] == "summary 1"
    assert embed["footer"]["text"] == "test"


def test_slack_payload_uses_mrkdwn_links():
    payload = post._slack_payload([make_item(1)])
    assert payload["text"] == "*<https://example.com/1|title 1>* (test)\nsummary 1"


def test_post_all_routes_batches_and_reports_posted(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_TECH_NEWS", "https://hooks.test/discord/tech")
    monkeypatch.setenv("SLACK_WEBHOOK_TECH_NEWS", "https://hooks.test/slack/tech")
    monkeypatch.delenv("DISCORD_WEBHOOK_AI_NEWS", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_AI_NEWS", raising=False)

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    items = [make_item(i) for i in range(12)] + [make_item(99, category="ai-news")]

    posted = post.post_all(items, make_config(), dry_run=False, client=client)

    # 12 tech-news items = 2 batches (10+2) per platform; ai-news has no webhook
    assert len(requests) == 4
    assert {str(r.url) for r in requests} == {
        "https://hooks.test/discord/tech",
        "https://hooks.test/slack/tech",
    }
    assert {i.id for i in posted} == {f"test:{i}" for i in range(12)}


def test_post_all_excludes_failed_webhooks(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_TECH_NEWS", "https://hooks.test/discord/tech")
    monkeypatch.delenv("SLACK_WEBHOOK_TECH_NEWS", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_AI_NEWS", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_AI_NEWS", raising=False)

    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    posted = post.post_all([make_item(1)], make_config(), dry_run=False, client=client)
    assert posted == []


def test_post_all_retries_once_on_429(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_TECH_NEWS", "https://hooks.test/discord/tech")
    monkeypatch.delenv("SLACK_WEBHOOK_TECH_NEWS", raising=False)
    monkeypatch.setattr(post.time, "sleep", lambda s: None)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"retry_after": 0.01})
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    posted = post.post_all([make_item(1)], make_config(), dry_run=False, client=client)
    assert calls["n"] == 2
    assert [i.id for i in posted] == ["test:1"]


def test_dry_run_posts_nothing(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run must not make HTTP calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    posted = post.post_all([make_item(1)], make_config(), dry_run=True, client=client)
    assert posted == []
    out = capsys.readouterr().out
    assert "[dry-run] discord/#tech-news" in out
    assert "[dry-run] slack/#tech-news" in out
    assert "title 1" in out
