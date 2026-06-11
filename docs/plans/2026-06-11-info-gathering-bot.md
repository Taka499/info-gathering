# Build an automated info-gathering bot that posts categorized digests to Discord and Slack

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `docs/PLANS.md` (repository root: `/Users/ghensk/Developer/info-gathering`). ExecPlans under `docs/plans/` are tracked in git (the owner removed the directory's ignore-all `.gitignore` on 2026-06-11); commit plan updates alongside the work they describe.

## Purpose / Big Picture

After this work, the repository contains a small Python program ("infobot") that, on a schedule, gathers newly published items from sources the owner cares about — AI/LLM news and papers (arXiv, vendor blogs via RSS) and general tech news (Hacker News, Reddit) — and posts each new item, with a short Claude-written summary, into the matching topic channel on Discord (with Slack support built in and ready to switch on later; see Decision Log). It runs unattended on a GitHub Actions cron schedule with no server to maintain.

Concretely, when everything is done the owner can:

1. Run `uv run python -m infobot --dry-run` locally and see a list of items found since the last run, each with a category and a 2–3 sentence summary, printed to the terminal instead of posted.
2. Run `uv run python -m infobot` and watch those same items appear as messages in the configured Discord channels (e.g. `#ai-papers`, `#ai-news`, `#tech-news`). Slack channels join later by adding webhook env vars — no code change.
3. Run it a second time immediately and see *nothing* posted, because every item is remembered in a SQLite database and never posted twice.
4. Push the code to a **public** GitHub repo (`Taka499/info-gathering`) and the seen-items database plus the cron workflow to a small **private** repo (`Taka499/info-gathering-state`); the private repo's Action runs every 2 hours, checks out the public code, runs the bot, and commits `seen.db` back to itself — so the code is public while the reading history, run logs, and secrets stay private.

## Progress

Use timestamps to measure rates of progress. Every stopping point must be documented here.

- [x] (2026-06-11) Design settled with the owner: Python, both Discord and Slack via incoming webhooks (plain HTTP POST, no platform SDKs), sources = AI/LLM news & papers + HN/Reddit tech news, hosting = GitHub Actions cron, dedup via SQLite committed back to the repo.
- [x] (2026-06-11) This ExecPlan written.
- [x] (2026-06-11) Milestone 1: repository scaffold, git init (`main`/`develop`/`feature/scaffold`), config loader, SQLite store, RSS/arXiv fetcher, CLI that prints new items. Acceptance verified live: first run found 57 ai-papers + 1848 ai-news items; second run printed `[ai-papers] 0 new  [ai-news] 0 new  [tech-news] 0 new`. 7 pytest tests pass. `state/seen.db` seeded with 1905 rows and committed, so launch will not re-post the backlog.
- [x] (2026-06-11) Milestone 2: Hacker News and Reddit fetchers. HN works as planned (Firebase API, score >= 100, 50 items found live). Reddit's JSON API turned out to be blocked for anonymous clients — rewrote the fetcher against Reddit's RSS endpoint instead (see Decision Log + Surprises). Live acceptance: 29 Reddit items fetched, immediate re-run printed all zeros. 11 pytest tests pass.
- [x] (2026-06-11) Milestone 3: Claude summarization + categorization with a `--no-llm` fallback. Live acceptance: `--dry-run` printed 4 new items each with a 2-3 sentence Claude summary (model `claude-opus-4-8` via `messages.parse`). Local secret handling added: `python-dotenv`, `.env` (gitignored). 15 pytest tests pass (incl. one live-API test, skipped without a key).
- [x] (2026-06-11) Milestone 4: Discord and Slack webhook posting with `--dry-run`. `post.py` with Discord embeds + Slack mrkdwn renderers, env-var webhook resolution, 10-item batching, single 429 retry, `mark_posted` only after a successful post; 20 unit tests pass. Live acceptance complete: owner created the three Discord webhooks; the bot posted 1 tech-news, 2 ai-papers, and 2 ai-news items into the matching channels (routing verified by deliberately forgetting 4 seen items), and the immediate re-run posted 0. Slack remains off per the Discord-first decision.
- [x] (2026-06-11) Milestone 5: GitHub Actions cron via the two-repo layout. Public `Taka499/info-gathering` (code, history purged of `state/`) + private `Taka499/info-gathering-state` (live workflow, secrets, `seen.db`). Manual `workflow_dispatch` run 27346493881 completed green; the run committed `update seen-items state` back to the state repo. The cron (`17 */2 * * *`) is now live.
- [x] (2026-06-11) Final: Outcomes & Retrospective written.

## Surprises & Discoveries

Document unexpected behaviors, bugs, optimizations, or insights discovered during implementation, with concise evidence.

- Observation: Some RSS feeds carry their entire archive, not just recent posts — `https://simonwillison.net/atom/everything/` alone returned ~1800 entries on the first fetch (log: `rss: fetched 1848 items` across four feeds). Unmitigated, adding any such feed later would flood the channels with its whole history.
  Resolution: Added a per-feed entry cap in `fetchers/rss.py` (`max_entries_per_feed`, default 50, newest first, configurable per source). The first-run backlog was absorbed harmlessly into `state/seen.db` (1905 rows committed), so none of it will ever post.
- Observation: Several configured feed URLs redirect (`openai.com/blog/rss.xml` → `/news/rss.xml`, arXiv `http` → `https`, blog.google moved paths). `follow_redirects=True` on the shared `httpx.Client` handles all of them; without it the bot would silently fetch nothing from those sources.
  Evidence: httpx INFO logs show 301/307 responses followed by 200s on the redirected URLs.
- Observation: arXiv cross-listing makes intra-batch dedup load-bearing, not just a safety net — 75 fetched papers across cs.AI/cs.CL/cs.LG collapsed to 57 unique because papers appear in multiple category queries with the same `arxiv:<id>`.
- Observation: Reddit's public JSON API (`/r/{sub}/top.json`) returns `403 Blocked` to anonymous clients regardless of User-Agent (tested: bot UA, descriptive `platform:app:version` UA, full browser UA, and `old.reddit.com` — all 403). The RSS endpoint of the same listing (`/r/{sub}/top/.rss?t=day`) returns 200.
  Evidence: probe run 2026-06-11 — `www json, browser UA -> 403`, `www rss, infobot UA -> 200 application/atom+xml`.
- Observation: Reddit RSS entry bodies HTML-escape hrefs, so naive extraction yields URLs containing literal `&amp;`. Fixed with `html.unescape()`; regression-tested via the fixture.
- Observation: `uv run --env-file .env` echoes the offending line verbatim when the env file fails to parse — which printed part of the API key into terminal output when `.env` initially held a bare key without `ANTHROPIC_API_KEY=`. python-dotenv's parse warnings, by contrast, name only the line number. Lesson: keep `.env` strictly `KEY=VALUE`, and prefer the app's own `load_dotenv()` path over `--env-file`.
- Observation: httpx logs full request URLs at INFO level, and Discord/Slack webhook URLs embed their secret token in the URL path — a future CI-log leak once posting starts. Pre-empted in M3 by setting the `httpx` logger to WARNING in `main()`.
- Observation: After `gh repo create --push` on a brand-new repo, the workflow file existed on the default branch and Actions was enabled (`enabled: true`), yet `GET /actions/workflows` stayed `total_count: 0` for many minutes — the initial push apparently raced the Actions app installation, so the push event never registered the workflow. An empty commit did NOT fix it; a commit that *modifies the workflow file itself* did, immediately.
  Evidence: `gh workflow list` empty → touch `run.yml` + push → `infobot active .github/workflows/run.yml` within seconds.

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

- Decision: GitHub Actions cron (every 2 hours) as the runtime; the SQLite seen-items database is committed back to a git repository after each run.
  Rationale: Zero infrastructure and free. `actions/cache` can be evicted, which would cause mass re-posting; committing the small binary DB back is ugly in diffs but durable, and only the bot ever writes it so conflicts cannot occur (enforced with a workflow `concurrency` group).
  Date/Author: 2026-06-11 / owner (hosting) + agent (state strategy).

- Decision: **Two-repository split — public code, private state.** The code lives in public `Taka499/info-gathering` with `state/` untracked and only a non-executing `.github/workflows/run.yml.sample`. The live workflow, the Actions secrets, and `seen.db` live in private `Taka499/info-gathering-state`; its scheduled job checks out itself (state at root) plus the public code repo (under `code/`), runs `uv run python -m infobot --db "$GITHUB_WORKSPACE/seen.db"` from `code/`, and commits `seen.db` back to itself. Because today's code-repo history already contained `seen.db` blobs, that history is purged of `state/` before publishing.
  Rationale: Owner direction (2026-06-11): "keep the seen-item history and bot activity private, while make source code public." Running the cron in the private repo (instead of merely keeping state there) also keeps Actions run logs and schedule private — on public repos, workflow logs are publicly visible. Owner additionally asked to keep a sample workflow file in the public repo for reference (`run.yml.sample`; the `.sample` suffix prevents Actions from executing it).
  Date/Author: 2026-06-11 / owner.

- Decision: Summarizer model defaults to `claude-opus-4-8`, configurable via `sources.yaml` (`llm.model`).
  Rationale: Current Anthropic guidance is to default to the latest Opus and let the *owner* decide any cost downgrade. Volume here is modest (tens of items per run, batched), but if cost matters the owner can set `model: claude-haiku-4-5` in config — classification/short-summary is a task Haiku handles well. This is surfaced to the owner rather than silently decided.
  Date/Author: 2026-06-11 / agent (flagged for owner).

- Decision: One git repository initialized with Git-flow branches (`main` + `develop`, feature branches per milestone), per the repo's `CLAUDE.md` commit discipline.
  Rationale: `CLAUDE.md` mandates Git-flow, small frequent commits, only affected files, no coding-agent attribution in commit messages.
  Date/Author: 2026-06-11 / repo convention.

- Decision: Fetch Reddit via its RSS endpoint instead of the JSON API, dropping the `min_score` filter for Reddit (RSS carries no scores; the `top?t=day` listing itself is the quality filter, capped by `max_items_per_subreddit`).
  Rationale: Reddit's JSON API returns `403 Blocked` to all anonymous clients (verified with multiple User-Agents); the alternative — registering a Reddit OAuth app — adds owner setup burden for little gain. The plan's `fetchers/reddit.py` description and `config/sources.yaml` shape changed accordingly.
  Date/Author: 2026-06-11 / agent (forced by Reddit API behavior).

- Decision: Local secrets live in a gitignored `.env` file (format strictly `KEY=VALUE`), loaded by `python-dotenv` inside `main()`; CI provides the same variables as real env vars from GitHub Actions secrets, where `load_dotenv()` is a harmless no-op.
  Rationale: Owner created `.env` and asked for dotenv support (2026-06-11); keeps local runs and CI symmetric with zero code branching.
  Date/Author: 2026-06-11 / owner.

- Decision: Source → default category mapping, with Claude allowed to override the category and to drop low-relevance items.
  Rationale: Most sources map cleanly (arXiv → `ai-papers`, HN/Reddit → `tech-news`, vendor blogs → `ai-news`); the LLM pass is for summaries, the occasional recategorization (e.g. an AI story on HN belongs in `ai-news`), and noise filtering — not for primary routing. This keeps the `--no-llm` path fully functional.
  Date/Author: 2026-06-11 / agent.

## Outcomes & Retrospective

To be written at the end of each milestone and at completion. Compare the result against the Purpose section.

- Project completion (2026-06-11): All four Purpose items hold. The bot runs every 2 hours on GitHub Actions from the private state repo, posts Claude-summarized items to the three Discord channels, never re-posts, and the public code repo carries no bot activity. Built design-to-production in a single day across 5 milestones. What changed versus the original plan: Reddit JSON → RSS (403s), single repo → public-code/private-state split (owner's privacy requirement, decided at deployment time), per-feed entry caps (archive feeds), Slack deferred (owner's Discord-first call). What remains for the future: enabling Slack (create webhooks + secrets + uncomment env lines), tuning sources/categories in `config/sources.yaml`, and possibly downgrading `llm.model` to `claude-haiku-4-5` if cost matters. Biggest transferable lessons: (1) every third-party integration surprised us in some way — probe endpoints with tiny scripts before coding against documentation or assumption; (2) secrets leak through tooling side channels (parse warnings, request logs), not just through committed files; (3) deployment-time requirements (privacy split) can restructure milestones late — the layered Git-flow + ExecPlan discipline made that pivot cheap.
- Milestone 4 (2026-06-11): The Purpose's items 2 and 3 are real for Discord — running without `--dry-run` delivers embeds into the right channels and re-runs are silent. Useful testing trick worth remembering: to exercise a posting path when no genuinely new items exist, `DELETE` a few rows from `state/seen.db` and re-run; the items re-post harmlessly and the category routing gets a live check.
- Milestone 3 (2026-06-11): The Purpose's item 1 is now fully real — `--dry-run` prints categorized items with Claude-written summaries. `messages.parse` + Pydantic worked exactly as planned (no JSON handling code at all); the milestone's surprises were all operational, not API-related: a malformed `.env` leaking a key fragment via uv's parse warning, and the discovery that httpx INFO logging would leak webhook URLs in M4 (pre-empted now). Summaries of excerpt-less items (HN/Reddit give titles only) are appropriately hedged ("likely explores...") per the system prompt's conservative-summarization instruction — acceptable, revisit only if the owner finds them weak.
- Milestone 2 (2026-06-11): All four source kinds now work end-to-end in the printing CLI. The one real deviation was Reddit: the planned JSON API path was dead on arrival (403 for anonymous clients), and the milestone's main work became the RSS-based rewrite — including extracting external URLs from HTML-escaped entry bodies. Score filtering survives only for HN; for Reddit, the curated `top?t=day` listing replaces it. Lesson repeated from M1: assumptions about third-party APIs only die on contact with the real service; the probe-first approach (test endpoints with a 10-line script before rewriting the fetcher) was cheap and decisive.
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

`src/infobot/fetchers/reddit.py` (revised after the 403 discovery — see Decision Log): GET `https://www.reddit.com/r/{sub}/{listing}/.rss?t={timeframe}` with a real `User-Agent`, parse with `feedparser`. Each entry's `link` is the comments page; the external URL is the HTML-escaped href of the `[link]` anchor in the entry body (`html.unescape` it). Skip entries whose `[link]` href equals the comments URL (self posts). `id = f"reddit:{entry.id}"` (e.g. `reddit:t3_abc123`). No score filtering is possible via RSS — the top-of-timeframe listing is the quality filter, capped by `max_items_per_subreddit` (default 25).

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

### Milestone 5 — GitHub Actions cron (two-repository layout)

Two repositories (see Decision Log):

1. **Public code repo** `Taka499/info-gathering` — everything in this working tree except `state/` (untracked) and the live workflow. `.github/workflows/run.yml.sample` documents the workflow without executing (Actions only runs `*.yml`/`*.yaml`). The code-repo git history must be purged of the previously committed `state/` blobs before the repo is made public (`git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch state' -- --all`, since the repo is one day old and local-only).
2. **Private state repo** `Taka499/info-gathering-state` — contains `seen.db` (seeded from the local DB), a short README, and the live `.github/workflows/run.yml`. Its content is exactly the public repo's `run.yml.sample` minus the sample header: cron `17 */2 * * *`, `workflow_dispatch`, `concurrency: infobot-run`, `permissions: contents: write`; checkout self (state at root) + `repository: Taka499/info-gathering` into `path: code`; `uv sync --frozen` and `uv run python -m infobot --db "$GITHUB_WORKSPACE/seen.db"` with `working-directory: code`; final step commits and pushes `seen.db` to the state repo itself.

Secrets (`ANTHROPIC_API_KEY`, `DISCORD_WEBHOOK_*`) are configured on the **state** repo, where the workflow runs (`gh secret set -f .env -R Taka499/info-gathering-state`). The public checkout of the code repo needs no token. The cron checks out the code repo's default branch (`main`), so deploying code means merging `develop` → `main` and pushing. Scheduled workflows on free GitHub are disabled after 60 days of repo inactivity; the state commits land in the state repo and count as its activity, so the schedule self-sustains.

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

Milestone 5 verification: create both repos, push, add the secrets to the state repo, then trigger once by hand:

    gh repo create Taka499/info-gathering --public --source . --push        # after history purge, main + develop
    gh repo create Taka499/info-gathering-state --private --source <state-dir> --push
    gh secret set -f .env -R Taka499/info-gathering-state
    gh workflow run infobot -R Taka499/info-gathering-state
    gh run watch -R Taka499/info-gathering-state

then confirm messages appeared in the Discord channels and an `update seen-items state` commit landed in the state repo.

## Validation and Acceptance

Acceptance is behavioral, per milestone:

1. After Milestone 1: the two-consecutive-runs transcript above — first run prints items, second prints zeros across the board; `uv run pytest` passes; deleting `state/seen.db` and re-running prints items again (idempotent rebuild).
2. After Milestone 2: HN items appear with the score threshold honored (HN only — Reddit's RSS path has no scores); Reddit items appear from the configured subreddits with external URLs, not comments-page URLs. Verified live 2026-06-11: 50 HN + 29 Reddit items on first run, zeros on re-run.
3. After Milestone 3: with `ANTHROPIC_API_KEY` exported, `--dry-run` output shows 2–3 sentence summaries instead of raw excerpts, and at least occasionally a recategorized item (an AI story fetched by the HN source printed under `[ai-news]`). With the key unset and `--no-llm`, the run still completes.
4. After Milestone 4: running without `--dry-run` makes the messages appear in the real Discord channels; an immediate re-run posts nothing. The Slack renderer is covered by unit tests only at this stage (no real Slack workspace is wired up); its live acceptance happens whenever Slack is enabled later.
5. After Milestone 5: `gh workflow run infobot -R Taka499/info-gathering-state` completes green; channels receive messages; the state commit appears in the state repo; the next scheduled run posts only newer items. The public repo shows no Actions activity and no `state/` directory anywhere in its history.

## Idempotence and Recovery

Every stage is safe to re-run. `CREATE TABLE IF NOT EXISTS` makes store init idempotent; the primary-key dedup makes fetching idempotent; marking items seen at *filter* time means a crash mid-run can at worst **skip** items (acceptable) but never double-post. If the bot ever posts garbage, stop the cron (disable the workflow in the GitHub UI), fix, and re-enable — no cleanup needed beyond deleting bad messages by hand. If the seen-items DB is lost or deleted, the next run re-posts whatever currently sits in the feeds (a one-time burst of roughly one feed-page per source, bounded by `max_results`/`max_items`), then converges; to avoid the burst after a state loss, run once locally with `--dry-run` (which records ids without posting) and push the resulting `seen.db` to the state repo. The workflow's `concurrency` group prevents overlapping runs racing on the state push; if a push still fails because the owner pushed a commit mid-run, the workflow fails visibly and the next scheduled run simply re-fetches — no corruption.

## Artifacts and Notes

Key external endpoints, collected so no future session has to rediscover them:

    arXiv Atom API : http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=25
    HN top stories : https://hacker-news.firebaseio.com/v0/topstories.json
    HN item        : https://hacker-news.firebaseio.com/v0/item/{id}.json
    Reddit listing : https://www.reddit.com/r/{sub}/top/.rss?t=day   (RSS only; the .json API 403s anonymous clients)
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
- 2026-06-11: Restructured Milestone 5 into a two-repository layout (public code repo + private state repo holding `seen.db`, the live workflow, and the secrets), per owner direction that the source should be public while reading history and bot activity stay private. The owner also asked to keep a reference copy of the workflow in the public repo — added as non-executing `.github/workflows/run.yml.sample`. Updated Purpose item 4, Decision Log, the Milestone 5 section, Concrete Steps, and Validation item 5. The code repo's local history gets purged of `state/` blobs before publishing.
- 2026-06-11: ExecPlans are now git-tracked — the owner removed `docs/plans/.gitignore` so plan files persist in history; updated the header note accordingly.
- 2026-06-11: Scoped the initial rollout to Discord only, per owner direction ("the first run we will only use Discord as target"). The Slack code path is still built in Milestone 4 behind the same env-var-driven abstraction, but no Slack webhooks/secrets are configured at launch; the workflow's Slack env lines are commented out. Updated Purpose, Decision Log, Milestone 4, the workflow YAML, the webhook setup steps, and Validation item 4 accordingly. Also clarified in conversation (no plan change needed — already specified): the SQLite seen-items DB is hosted in the git repository itself as `state/seen.db`, committed back after each Actions run.
