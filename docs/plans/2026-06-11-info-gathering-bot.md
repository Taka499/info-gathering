# Build an automated info-gathering bot that posts categorized digests to Discord and Slack

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `docs/PLANS.md` (repository root: `/Users/ghensk/Developer/info-gathering`). ExecPlans under `docs/plans/` are tracked in git (the owner removed the directory's ignore-all `.gitignore` on 2026-06-11); commit plan updates alongside the work they describe.

## Purpose / Big Picture

After this work, the repository contains a small Python program ("infobot") that, on a schedule, gathers newly published items from sources the owner cares about — AI/LLM news and papers (arXiv, vendor blogs via RSS) and general tech news (Hacker News, Reddit) — and posts each new item, with a short Claude-written summary, into the matching topic channel on Discord (with Slack support built in and ready to switch on later; see Decision Log). It runs unattended on a GitHub Actions cron schedule with no server to maintain.

Concretely, when everything is done the owner can:

1. Run `uv run python -m infobot --dry-run` locally and see a list of items found since the last run, each with a category and a 2–3 sentence summary, printed to the terminal instead of posted.
2. Run `uv run python -m infobot` and watch those same items appear as messages in the configured Discord channels (e.g. `#ai-papers`, `#ai-news`, `#tech-news`). Slack channels join later by adding webhook env vars — no code change.
3. Run it a second time immediately and see *nothing* posted, because every item is remembered in a SQLite database and never posted twice.
4. Push the repo to GitHub, add secrets, and have the whole cycle repeat automatically every 2 hours via GitHub Actions, with the seen-items database committed back to the repo after each run so state survives between runs.

## Progress

Use timestamps to measure rates of progress. Every stopping point must be documented here.

- [x] (2026-06-11) Design settled with the owner: Python, both Discord and Slack via incoming webhooks (plain HTTP POST, no platform SDKs), sources = AI/LLM news & papers + HN/Reddit tech news, hosting = GitHub Actions cron, dedup via SQLite committed back to the repo.
- [x] (2026-06-11) This ExecPlan written.
- [x] (2026-06-11) Milestone 1: repository scaffold, git init (`main`/`develop`/`feature/scaffold`), config loader, SQLite store, RSS/arXiv fetcher, CLI that prints new items. Acceptance verified live: first run found 57 ai-papers + 1848 ai-news items; second run printed `[ai-papers] 0 new  [ai-news] 0 new  [tech-news] 0 new`. 7 pytest tests pass. `state/seen.db` seeded with 1905 rows and committed, so launch will not re-post the backlog.
- [ ] Milestone 2: Hacker News and Reddit fetchers with score thresholds.
- [ ] Milestone 3: Claude summarization + categorization with a `--no-llm` fallback.
- [ ] Milestone 4: Discord and Slack webhook posting with `--dry-run`.
- [ ] Milestone 5: GitHub Actions cron workflow with state commit-back; verified via manual `workflow_dispatch` run.
- [ ] Final: Outcomes & Retrospective written.

## Surprises & Discoveries

Document unexpected behaviors, bugs, optimizations, or insights discovered during implementation, with concise evidence.

- Observation: Some RSS feeds carry their entire archive, not just recent posts — `https://simonwillison.net/atom/everything/` alone returned ~1800 entries on the first fetch (log: `rss: fetched 1848 items` across four feeds). Unmitigated, adding any such feed later would flood the channels with its whole history.
  Resolution: Added a per-feed entry cap in `fetchers/rss.py` (`max_entries_per_feed`, default 50, newest first, configurable per source). The first-run backlog was absorbed harmlessly into `state/seen.db` (1905 rows committed), so none of it will ever post.
- Observation: Several configured feed URLs redirect (`openai.com/blog/rss.xml` → `/news/rss.xml`, arXiv `http` → `https`, blog.google moved paths). `follow_redirects=True` on the shared `httpx.Client` handles all of them; without it the bot would silently fetch nothing from those sources.
  Evidence: httpx INFO logs show 301/307 responses followed by 200s on the redirected URLs.
- Observation: arXiv cross-listing makes intra-batch dedup load-bearing, not just a safety net — 75 fetched papers across cs.AI/cs.CL/cs.LG collapsed to 57 unique because papers appear in multiple category queries with the same `arxiv:<id>`.

## Decision Log

- Decision: Python (3.12+) with `uv` for dependency management.
  Rationale: `feedparser` is by far the most battle-tested RSS/Atom parser (handles malformed feeds the JS equivalents reject); `sqlite3` is in the standard library; the whole job is a short-lived batch script, which is idiomatic Python. The owner explicitly approved Python after a comparison with TypeScript.
  Date/Author: 2026-06-11 / owner + agent.

- Decision: Post to **both** Discord and Slack, exclusively through incoming webhooks (one plain HTTP POST per message), with no `discord.py`/`slack_sdk` dependencies.
  Rationale: The owner chose "both". Webhooks make the platform abstraction ~30 lines of `httpx`; an interactive bot (slash commands, reactions) is out of scope.
  Date/Author: 2026-06-11 / owner.

- Decision: **Initial rollout targets Discord only.** The Slack rendering/posting code path is still implemented in Milestone 4 (it shares the same abstraction and is cheap to build alongside), but no Slack webhooks are created and no `SLACK_WEBHOOK_*` secrets are configured at launch. Because a missing webhook env var means "that platform/channel is off", enabling Slack later is purely operational: create the Slack app + webhooks and add the secrets — zero code changes.
  Rationale: Owner direction (2026-06-11): "the first run we will only use Discord as target."
  Date/Author: 2026-06-11 / owner.

- Decision: GitHub Actions cron (every 2 hours) as the runtime; the SQLite seen-items database is committed back to the repository after each run.
  Rationale: Zero infrastructure and free. `actions/cache` can be evicted, which would cause mass re-posting; committing the small binary DB back is ugly in diffs but durable, and only the bot ever writes it so conflicts cannot occur (enforced with a workflow `concurrency` group).
  Date/Author: 2026-06-11 / owner (hosting) + agent (state strategy).

- Decision: Summarizer model defaults to `claude-opus-4-8`, configurable via `sources.yaml` (`llm.model`).
  Rationale: Current Anthropic guidance is to default to the latest Opus and let the *owner* decide any cost downgrade. Volume here is modest (tens of items per run, batched), but if cost matters the owner can set `model: claude-haiku-4-5` in config — classification/short-summary is a task Haiku handles well. This is surfaced to the owner rather than silently decided.
  Date/Author: 2026-06-11 / agent (flagged for owner).

- Decision: One git repository initialized with Git-flow branches (`main` + `develop`, feature branches per milestone), per the repo's `CLAUDE.md` commit discipline.
  Rationale: `CLAUDE.md` mandates Git-flow, small frequent commits, only affected files, no coding-agent attribution in commit messages.
  Date/Author: 2026-06-11 / repo convention.

- Decision: Source → default category mapping, with Claude allowed to override the category and to drop low-relevance items.
  Rationale: Most sources map cleanly (arXiv → `ai-papers`, HN/Reddit → `tech-news`, vendor blogs → `ai-news`); the LLM pass is for summaries, the occasional recategorization (e.g. an AI story on HN belongs in `ai-news`), and noise filtering — not for primary routing. This keeps the `--no-llm` path fully functional.
  Date/Author: 2026-06-11 / agent.

## Outcomes & Retrospective

To be written at the end of each milestone and at completion. Compare the result against the Purpose section.

- Milestone 1 (2026-06-11): Achieved exactly what the Purpose's items 1 and 3 describe for the RSS/arXiv sources — a runnable `uv run python -m infobot --dry-run --no-llm` that prints categorized new items and prints zeros on an immediate re-run. Deviation from plan: added a `max_entries_per_feed` cap (not in the original design) after discovering archive-sized feeds; recorded in Surprises & Discoveries. Remaining toward the Purpose: HN/Reddit sources (M2), summaries (M3), actual posting (M4), and the cron (M5). Lesson: do a real network run early — both surprises (archive feeds, redirects) were invisible in fixture-based tests.

## Context and Orientation

The repository `/Users/ghensk/Developer/info-gathering` is currently almost empty: it contains only `CLAUDE.md` (project conventions: docs live in `docs/`, ExecPlans follow `docs/PLANS.md`, Git-flow commit discipline) and `docs/PLANS.md` (the ExecPlan process description). **It is not yet a git repository** — `git init` is part of Milestone 1. There is no existing code; everything below is created from scratch.

Definitions of terms used throughout:

- **RSS/Atom feed**: an XML document a website publishes listing its recent entries (title, link, date, summary). The Python library `feedparser` downloads-and-parses these into plain Python objects. arXiv's "API" is itself an Atom feed (`http://export.arxiv.org/api/query?...`), so the same code path handles both blogs and arXiv.
- **Incoming webhook**: a secret URL that Discord or Slack gives you for a specific channel. POSTing a small JSON body to that URL makes a message appear in the channel. No login, no token refresh, no SDK.
- **Seen-items store**: a SQLite file (`state/seen.db`) recording the ID of every item the bot has ever processed, so re-runs never re-post.
- **GitHub Actions cron**: GitHub will run a workflow on a schedule defined by a cron expression in `.github/workflows/run.yml`, on a fresh VM each time — which is why state must be committed back to the repo.
- **uv**: a fast Python package/environment manager. `uv sync` creates `.venv` from `pyproject.toml`/`uv.lock`; `uv run <cmd>` runs a command inside it. Install via `brew install uv` if missing.

Target repository layout (all paths repo-relative):

    pyproject.toml              project metadata + dependencies
    uv.lock                     locked dependency versions (committed)
    config/sources.yaml         sources, categories, thresholds, llm settings
    src/infobot/__init__.py
    src/infobot/__main__.py     enables `python -m infobot`
    src/infobot/config.py       loads sources.yaml + env vars into a Config object
    src/infobot/models.py       the Item dataclass shared by all stages
    src/infobot/store.py        SQLite seen-items store
    src/infobot/fetchers/__init__.py   fetch_all(config) -> list[Item]
    src/infobot/fetchers/rss.py        RSS/Atom + arXiv (feedparser)
    src/infobot/fetchers/hackernews.py Hacker News Firebase API
    src/infobot/fetchers/reddit.py     Reddit public JSON endpoints
    src/infobot/summarize.py    Claude categorize + summarize
    src/infobot/post.py         Discord + Slack webhook posting
    src/infobot/main.py         CLI orchestration (argparse)
    state/seen.db               SQLite database (committed; created on first run)
    state/.gitkeep
    tests/                      pytest tests + feed fixtures
    .github/workflows/run.yml   cron workflow
    .gitignore                  .venv/, __pycache__/, .pytest_cache/, .DS_Store

The data flow through `main.py` is: `config.load()` → `fetchers.fetch_all()` → `store.filter_new()` → `summarize.enrich()` (skipped with `--no-llm`) → `post.post_all()` (printed instead with `--dry-run`) → `store.mark_posted()`.

## Plan of Work

### Milestone 1 — Scaffold, store, RSS fetcher, printing CLI

Goal: a runnable program that fetches RSS/arXiv sources from config, dedups against SQLite, and prints new items. At the end of this milestone the bot is already useful as a terminal news digest.

Initialize git and Git-flow branches first: `git init`, create `main`, commit the existing `CLAUDE.md`, `docs/PLANS.md` and the new `.gitignore`, then `git checkout -b develop`, and do milestone work on `feature/scaffold` branched from `develop`, merging back with small commits as units of work complete.

Create `pyproject.toml`:

    [project]
    name = "infobot"
    version = "0.1.0"
    requires-python = ">=3.12"
    dependencies = [
        "feedparser>=6.0",
        "httpx>=0.27",
        "pyyaml>=6.0",
        "anthropic>=0.50",
        "pydantic>=2.0",
    ]

    [dependency-groups]
    dev = ["pytest>=8.0"]

    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

    [tool.hatch.build.targets.wheel]
    packages = ["src/infobot"]

Run `uv sync` to create the venv and `uv.lock`.

Create `config/sources.yaml`. Categories are the routing unit; every source declares its default category. The webhook env-var names are *derived* (`DISCORD_WEBHOOK_<CATEGORY>` / `SLACK_WEBHOOK_<CATEGORY>` with the category upper-cased and dashes turned to underscores), not stored in config, so the file stays secret-free:

    categories: [ai-papers, ai-news, tech-news]

    llm:
      enabled: true
      model: claude-opus-4-8     # set to claude-haiku-4-5 to cut cost
      max_items_per_call: 15

    sources:
      - kind: arxiv
        category: ai-papers
        queries: ["cat:cs.AI", "cat:cs.CL", "cat:cs.LG"]
        max_results: 25
      - kind: rss
        category: ai-news
        feeds:
          - https://openai.com/blog/rss.xml
          - https://huggingface.co/blog/feed.xml
          - https://blog.google/technology/ai/rss/
          - https://simonwillison.net/atom/everything/
      - kind: hackernews
        category: tech-news
        min_score: 100
        max_items: 100
      - kind: reddit
        category: tech-news
        subreddits: [programming, technology]
        min_score: 200
        listing: top
        timeframe: day

(The feed URLs above are starting suggestions; the owner edits this file freely. A feed that 404s must log a warning and be skipped, never crash the run.)

In `src/infobot/models.py` define the shared record:

    @dataclass
    class Item:
        id: str           # stable dedup key, e.g. "hn:42421234", "arxiv:2406.01234", or canonical URL
        url: str
        title: str
        source: str       # human label, e.g. "Hacker News", "arXiv cs.CL", feed title
        category: str     # one of config categories; default from source, may be overridden by LLM
        published: str    # ISO 8601 UTC if known, else ""
        excerpt: str = "" # raw feed summary / first paragraph, pre-LLM
        summary: str = "" # filled by summarize.enrich()

Canonicalize URLs for the `id` when no native ID exists: lowercase the host, drop the fragment and any `utm_*` query parameters.

In `src/infobot/store.py` implement `Store` over `sqlite3` with `CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT, category TEXT, first_seen_utc TEXT, posted_utc TEXT)`. Methods: `filter_new(items) -> list[Item]` (returns items whose id is absent, and inserts them with `posted_utc = NULL`), `mark_posted(items)` (sets `posted_utc` to now). Inserting at filter time, not post time, means a crash between fetch and post errs on the side of *not* re-posting — the right failure mode for a noisy bot. The DB path defaults to `state/seen.db`, overridable with `--db` for tests.

In `src/infobot/fetchers/rss.py` implement both `rss` and `arxiv` kinds with `feedparser.parse()` (arXiv URL shape: `http://export.arxiv.org/api/query?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results={n}`). Map entries to `Item`s. Fetch the bytes with `httpx` (10 s timeout, `User-Agent: infobot/0.1`) and hand them to feedparser, so network errors are catchable per-feed.

In `src/infobot/main.py` wire `argparse` with flags `--dry-run`, `--no-llm`, `--db PATH`, `--config PATH`; in this milestone every run is effectively dry (print only). `src/infobot/__main__.py` is two lines calling `main.main()`.

Tests (`uv run pytest`): `tests/test_store.py` (filter_new twice on the same items returns items then empty; mark_posted persists across reopen) and `tests/test_rss.py` (parse a small checked-in Atom fixture in `tests/fixtures/arxiv_sample.xml` via `feedparser.parse(bytes)`, assert Item fields — no network in tests).

### Milestone 2 — Hacker News and Reddit fetchers

`src/infobot/fetchers/hackernews.py`: GET `https://hacker-news.firebaseio.com/v0/topstories.json` (list of ~500 ids), take the first `max_items`, GET `https://hacker-news.firebaseio.com/v0/item/{id}.json` for each (use a single `httpx.Client` for connection reuse), keep stories with `score >= min_score` and a `url` field (skip Ask HN text posts), `id = f"hn:{id}"`. The per-item fetches are the slow part; ~100 sequential requests take ~20 s, which is acceptable in a cron job — do not add async machinery for this.

`src/infobot/fetchers/reddit.py`: GET `https://www.reddit.com/r/{sub}/{listing}.json?t={timeframe}&limit=25` with a real `User-Agent` (Reddit returns 429 to default agents), keep posts with `score >= min_score`, skip self-posts and stickies, `id = f"reddit:{post['id']}"`, `url` = the external link.

Both fetchers log-and-continue on per-source HTTP errors. Tests use checked-in JSON fixtures and a stub transport (`httpx.MockTransport`), again no network.

### Milestone 3 — Claude summarization and categorization

`src/infobot/summarize.py`. Use the official `anthropic` SDK; `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY` from the environment. Use structured outputs via `client.messages.parse` with Pydantic models so no JSON parsing is hand-rolled:

    from pydantic import BaseModel
    import anthropic

    class ItemVerdict(BaseModel):
        id: str
        category: str        # must be one of the configured categories
        summary: str         # 2-3 plain sentences
        relevant: bool       # false => drop (spam, dupes-in-spirit, low value)

    class BatchVerdict(BaseModel):
        items: list[ItemVerdict]

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=cfg.llm.model,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,   # explains categories and the relevance bar; frozen string for prompt caching
        messages=[{"role": "user", "content": render_batch(items)}],
        output_format=BatchVerdict,
    )
    verdicts = response.parsed_output

Process items in batches of `llm.max_items_per_call`. `render_batch` lists each item's `id`, title, source, url, and excerpt (excerpt truncated to ~800 chars). Apply verdicts by `id`; an id missing from the response keeps its defaults and is still posted (fail open on the summary, never lose an item). Wrap each API call in a try/except on `anthropic.APIError`: on failure, log and fall back to the `--no-llm` behavior for that batch (post with the source-default category and the raw excerpt as summary). `--no-llm` and `llm.enabled: false` skip this stage entirely. Do not set `temperature` (not accepted on `claude-opus-4-8`).

Test with a fake: factor the API call behind a `summarize_batch(items) -> BatchVerdict` function and unit-test the apply/fallback logic with a stubbed version; one optional integration test hits the real API only when `ANTHROPIC_API_KEY` is set (`pytest.mark.skipif`).

### Milestone 4 — Discord and Slack posting

`src/infobot/post.py`. For each category, resolve webhook URLs from the environment: `DISCORD_WEBHOOK_AI_PAPERS`, `SLACK_WEBHOOK_AI_PAPERS`, etc. A missing variable means "this platform/channel pair is off" — log once at startup, skip silently afterwards. Per the Decision Log, the initial rollout sets only the Discord variables; the Slack renderer is implemented and unit-tested in this milestone but exercised against a real workspace only when Slack is enabled later.

Discord: POST `{"embeds": [{"title": ..., "url": ..., "description": summary, "footer": {"text": source}}]}` with up to 10 embeds per request (Discord's cap). Title truncated to 256 chars, description to 2048. On HTTP 429 read `retry_after` from the JSON body, sleep, retry once.

Slack: POST `{"text": digest}` where digest is mrkdwn lines `*<{url}|{title}>* ({source})\n{summary}`, batched ~10 items per message. Slack webhooks answer literal body `ok` on success.

`--dry-run` prints exactly what would be posted (category, platform, rendered text) and skips both the POSTs and `mark_posted`, so a dry run is repeatable. Only after a successful post on at least one platform is the item marked posted.

### Milestone 5 — GitHub Actions cron

`.github/workflows/run.yml`:

    name: infobot
    on:
      schedule:
        - cron: "17 */2 * * *"   # every 2 hours; off-the-hour to dodge GH's cron rush
      workflow_dispatch: {}
    concurrency:
      group: infobot-run
      cancel-in-progress: false
    permissions:
      contents: write
    jobs:
      run:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: astral-sh/setup-uv@v5
          - run: uv sync --frozen
          - run: uv run python -m infobot
            env:
              ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
              DISCORD_WEBHOOK_AI_PAPERS: ${{ secrets.DISCORD_WEBHOOK_AI_PAPERS }}
              DISCORD_WEBHOOK_AI_NEWS: ${{ secrets.DISCORD_WEBHOOK_AI_NEWS }}
              DISCORD_WEBHOOK_TECH_NEWS: ${{ secrets.DISCORD_WEBHOOK_TECH_NEWS }}
              # Slack is off at launch. To enable later: create Slack webhooks,
              # add the secrets, and uncomment — no code changes needed.
              # SLACK_WEBHOOK_AI_PAPERS: ${{ secrets.SLACK_WEBHOOK_AI_PAPERS }}
              # SLACK_WEBHOOK_AI_NEWS: ${{ secrets.SLACK_WEBHOOK_AI_NEWS }}
              # SLACK_WEBHOOK_TECH_NEWS: ${{ secrets.SLACK_WEBHOOK_TECH_NEWS }}
          - name: Commit state
            run: |
              git config user.name "infobot"
              git config user.email "infobot@users.noreply.github.com"
              git add state/seen.db
              git diff --cached --quiet || git commit -m "chore: update seen-items state"
              git push

Note the cron job runs against the default branch — once the project is live, merge `develop` → `main` so the workflow and code are on `main`, and the state commits land there. Scheduled workflows on free GitHub are disabled after 60 days of repo inactivity; the state commits themselves count as activity, so this self-sustains.

## Concrete Steps

All commands run from the repository root `/Users/ghensk/Developer/info-gathering`.

Milestone 1 setup:

    git init -b main
    printf '.venv/\n__pycache__/\n.pytest_cache/\n.DS_Store\n' > .gitignore
    git add CLAUDE.md docs/PLANS.md .gitignore && git commit -m "chore: repo scaffold"
    git checkout -b develop
    git checkout -b feature/scaffold
    uv sync          # after writing pyproject.toml

Local run and the dedup proof (expected transcript shape):

    $ uv run python -m infobot --dry-run --no-llm
    [ai-papers] 25 new  [ai-news] 7 new  [tech-news] 31 new
    [dry-run] discord/#ai-papers: "Scaling Laws for ..." (arXiv cs.LG) ...
    ...
    $ uv run python -m infobot --dry-run --no-llm
    [ai-papers] 0 new  [ai-news] 0 new  [tech-news] 0 new

(Exact counts vary with the news; the second-run zeros are the invariant. Note `--dry-run` skips `mark_posted` but `filter_new` already recorded the ids — that is what makes the second run empty, and it is intended.)

Tests at every milestone:

    uv run pytest
    # expect: all passed; milestone 1 adds test_store.py + test_rss.py,
    # milestone 2 adds test_hackernews.py + test_reddit.py,
    # milestone 3 adds test_summarize.py, milestone 4 adds test_post.py

Webhook setup (owner, manual, once): Discord — channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL, per channel. Export locally as the env var names above to test for real; add as repository secrets on GitHub for CI. Slack (deferred until the owner enables it): create a Slack app → Incoming Webhooks → Activate → Add New Webhook to Workspace per channel, then add the `SLACK_WEBHOOK_*` secrets and uncomment them in the workflow.

Milestone 5 verification: push to GitHub, add the secrets, then trigger once by hand:

    gh workflow run infobot
    gh run watch

then confirm messages appeared in the channels and a `chore: update seen-items state` commit landed.

## Validation and Acceptance

Acceptance is behavioral, per milestone:

1. After Milestone 1: the two-consecutive-runs transcript above — first run prints items, second prints zeros across the board; `uv run pytest` passes; deleting `state/seen.db` and re-running prints items again (idempotent rebuild).
2. After Milestone 2: HN and Reddit items appear with scores honored — temporarily set `min_score: 10000` in config and confirm those sources yield 0 items, then restore.
3. After Milestone 3: with `ANTHROPIC_API_KEY` exported, `--dry-run` output shows 2–3 sentence summaries instead of raw excerpts, and at least occasionally a recategorized item (an AI story fetched by the HN source printed under `[ai-news]`). With the key unset and `--no-llm`, the run still completes.
4. After Milestone 4: running without `--dry-run` makes the messages appear in the real Discord channels; an immediate re-run posts nothing. The Slack renderer is covered by unit tests only at this stage (no real Slack workspace is wired up); its live acceptance happens whenever Slack is enabled later.
5. After Milestone 5: `gh workflow run infobot` completes green; channels receive messages; the state commit appears; the next scheduled run posts only newer items.

## Idempotence and Recovery

Every stage is safe to re-run. `CREATE TABLE IF NOT EXISTS` makes store init idempotent; the primary-key dedup makes fetching idempotent; marking items seen at *filter* time means a crash mid-run can at worst **skip** items (acceptable) but never double-post. If the bot ever posts garbage, stop the cron (disable the workflow in the GitHub UI), fix, and re-enable — no cleanup needed beyond deleting bad messages by hand. If `state/seen.db` is lost or deleted, the next run re-posts whatever currently sits in the feeds (a one-time burst of roughly one feed-page per source, bounded by `max_results`/`max_items`), then converges; to avoid the burst after a state loss, run once locally with `--dry-run` (which records ids without posting) and commit the DB. The workflow's `concurrency` group prevents overlapping runs racing on the state push; if a push still fails because the owner pushed a commit mid-run, the workflow fails visibly and the next scheduled run simply re-fetches — no corruption.

## Artifacts and Notes

Key external endpoints, collected so no future session has to rediscover them:

    arXiv Atom API : http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=25
    HN top stories : https://hacker-news.firebaseio.com/v0/topstories.json
    HN item        : https://hacker-news.firebaseio.com/v0/item/{id}.json
    Reddit listing : https://www.reddit.com/r/{sub}/top.json?t=day&limit=25   (needs a custom User-Agent)
    Discord webhook: POST {url} {"embeds": [...]}        (max 10 embeds/request, 30 req/min/webhook)
    Slack webhook  : POST {url} {"text": "..."}          (returns body "ok")

Anthropic specifics: dependency `anthropic`; client `anthropic.Anthropic()` reads `ANTHROPIC_API_KEY`; structured output via `client.messages.parse(..., output_format=PydanticModel)` and `response.parsed_output`; model id strings are exactly `claude-opus-4-8` / `claude-haiku-4-5` (no date suffixes); do not pass `temperature`/`top_p` (removed on current Opus models); `thinking={"type": "adaptive"}` is the recommended thinking setting.

## Interfaces and Dependencies

Libraries: `feedparser` (RSS/Atom/arXiv parsing), `httpx` (all HTTP), `pyyaml` (config), `anthropic` + `pydantic` (summaries), `pytest` (dev). Nothing else; specifically no `discord.py`, no `slack_sdk`, no async framework.

Stable internal interfaces that must exist at the end (signatures the milestones build toward):

    # src/infobot/config.py
    def load(path: str = "config/sources.yaml") -> Config            # Config carries .categories, .llm, .sources

    # src/infobot/store.py
    class Store:
        def __init__(self, db_path: str = "state/seen.db") -> None
        def filter_new(self, items: list[Item]) -> list[Item]
        def mark_posted(self, items: list[Item]) -> None

    # src/infobot/fetchers/__init__.py
    def fetch_all(config: Config) -> list[Item]                      # dispatches on source.kind, never raises

    # src/infobot/summarize.py
    def enrich(items: list[Item], config: Config) -> list[Item]      # returns kept items with .summary/.category set

    # src/infobot/post.py
    def post_all(items: list[Item], config: Config, dry_run: bool) -> list[Item]   # returns successfully posted items

    # src/infobot/main.py
    def main(argv: list[str] | None = None) -> int                   # the CLI entry point

---

Revision notes:

- 2026-06-11: Initial version, written after the design conversation with the owner.
- 2026-06-11: ExecPlans are now git-tracked — the owner removed `docs/plans/.gitignore` so plan files persist in history; updated the header note accordingly.
- 2026-06-11: Scoped the initial rollout to Discord only, per owner direction ("the first run we will only use Discord as target"). The Slack code path is still built in Milestone 4 behind the same env-var-driven abstraction, but no Slack webhooks/secrets are configured at launch; the workflow's Slack env lines are commented out. Updated Purpose, Decision Log, Milestone 4, the workflow YAML, the webhook setup steps, and Validation item 4 accordingly. Also clarified in conversation (no plan change needed — already specified): the SQLite seen-items DB is hosted in the git repository itself as `state/seen.db`, committed back after each Actions run.
