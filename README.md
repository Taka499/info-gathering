# infobot

A self-hosted, zero-infrastructure news bot. Every 2 hours it gathers newly
published items from sources you care about — arXiv categories, RSS/Atom
feeds, Hacker News, Reddit — has Claude write a 2–3 sentence summary for each,
and posts them into matching Discord channels (Slack supported too). It runs
entirely on GitHub Actions: no server, no database service, nothing to keep
alive.

    fetch (arXiv / RSS / HN / Reddit)
      → dedup (SQLite, committed to a private git repo)
      → summarize + categorize (Claude, structured output)
      → post (Discord / Slack incoming webhooks)

Nothing is ever posted twice: every item ID is recorded in a small SQLite
database that persists between runs. The LLM stage **fails open** — if the
API errors, items are posted with their raw feed excerpts instead of being
lost.

## How it works

Two repositories share the work:

| Repo | Visibility | Contents |
|---|---|---|
| **this one** | public | the Python package, config, tests, and a non-executing workflow sample |
| `<you>/infobot-state` | private | the live GitHub Actions workflow, the Actions secrets, and `seen.db` |

The private repo's scheduled workflow checks out the public code, runs the
bot, and commits the updated `seen.db` back to itself. The split keeps the
code public while your reading history, run logs, and secrets stay private.
The live workflow is a copy of
[`.github/workflows/run.yml.sample`](.github/workflows/run.yml.sample)
(minus the sample header).

## Quick start (local)

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), an
[Anthropic API key](https://platform.claude.com/), and a Discord webhook per
category (channel → Edit Channel → Integrations → Webhooks → New Webhook).

```sh
git clone https://github.com/Taka499/info-gathering.git
cd info-gathering
uv sync
```

Create a `.env` (gitignored; strictly `KEY=VALUE`, one per line):

```sh
ANTHROPIC_API_KEY=sk-ant-...
DISCORD_WEBHOOK_AI_PAPERS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_AI_NEWS=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_TECH_NEWS=https://discord.com/api/webhooks/...
```

Then:

```sh
uv run python -m infobot --dry-run   # preview: prints what would be posted
uv run python -m infobot             # posts for real
```

The first run absorbs the current backlog of every source. To avoid a flood,
do the first run with `--dry-run` — it records the backlog as "seen" without
posting — and post for real from the second run onward. Useful flags:
`--no-llm` (skip summaries), `--db PATH`, `--config PATH`.

## Customizing topics and sources

Everything lives in [`config/sources.yaml`](config/sources.yaml). A category
is a channel; a source feeds items into a category.

### Adding a category

1. Add it to the `categories` list, e.g. `rust-news`.
2. Create a Discord webhook for the target channel and export it under the
   derived name: category upper-cased, dashes to underscores —
   `DISCORD_WEBHOOK_RUST_NEWS`. A missing variable simply turns that
   channel off; nothing else to wire up.
3. Point one or more sources at it.

Claude may also re-route an item to a better-fitting category (e.g. an AI
story fetched from a general tech source), so categories work even when
sources overlap.

### Adding sources

Four source kinds are supported:

```yaml
sources:
  # Any RSS/Atom feed. Feeds carrying their whole archive are capped to the
  # newest entries (max_entries_per_feed, default 50).
  - kind: rss
    category: rust-news
    feeds:
      - https://blog.rust-lang.org/feed.xml

  # arXiv categories (https://arxiv.org/category_taxonomy), newest first.
  - kind: arxiv
    category: ai-papers
    queries: ["cat:cs.AI", "cat:cs.RO"]
    max_results: 25

  # Hacker News front page, filtered by score. Text posts (Ask/Show HN
  # without a link) are skipped.
  - kind: hackernews
    category: tech-news
    min_score: 100
    max_items: 100

  # Subreddit listings, fetched via RSS (Reddit's JSON API blocks anonymous
  # clients). No score filter is possible -- the top-of-timeframe listing is
  # the quality filter. Self posts are skipped.
  - kind: reddit
    category: tech-news
    subreddits: [programming, rust]
    listing: top
    timeframe: day
    max_items_per_subreddit: 25
```

### Tuning the LLM stage

```yaml
llm:
  enabled: true                # false = post raw excerpts, no API cost
  model: claude-opus-4-8       # claude-haiku-4-5 cuts cost ~5x for this task
  max_items_per_call: 15
```

Once deployed, config changes take effect by merging to `main` — the next
scheduled run picks them up.

## Deploying on GitHub Actions

1. Fork or push this repo (public or private — your choice).
2. Create a **private** state repo containing:
   - `seen.db` — your local `state/seen.db` after a `--dry-run` (this seeds
     the dedup state so deployment doesn't re-post the backlog);
   - `.github/workflows/run.yml` — copy `run.yml.sample` from this repo,
     drop the sample header, and point the second `actions/checkout` at your
     code repo.
3. Add the secrets to the **state** repo (that's where the workflow runs):
   `gh secret set -f .env -R <you>/infobot-state`
4. Trigger a test run: `gh workflow run infobot -R <you>/infobot-state`,
   then check your Discord channels and confirm an `update seen-items state`
   commit appeared in the state repo.

The schedule (`17 */2 * * *`) and everything else are plain workflow YAML —
edit the live copy in the state repo. If the workflow doesn't appear after
the first push, make any edit to the workflow file and push again; brand-new
repos sometimes miss the initial registration.

### Enabling Slack

Slack support is already built in. Create a Slack app with incoming webhooks,
add `SLACK_WEBHOOK_<CATEGORY>` secrets to the state repo, and uncomment the
matching `env:` lines in the workflow. No code changes.

## Operations

- **Pause the bot** — disable the workflow in the state repo's Actions tab.
- **Force a re-post** (testing) — delete the item's row from `seen.db` and
  re-run.
- **State loss recovery** — if `seen.db` is ever lost, run locally with
  `--dry-run` once (records the current backlog without posting) and push
  the resulting DB to the state repo.
- **Costs** — GitHub Actions free tier covers the ~1 min/run easily; the
  Claude API bill depends on volume and model (a few dozen items per run is
  cents/day on Opus, less on Haiku).

## Development

```sh
uv run pytest                      # unit tests: fixtures only, no network
uv run --env-file .env pytest      # also runs the one live-API test
```

Design history, decisions, and validation steps live in
[`docs/plans/2026-06-11-info-gathering-bot.md`](docs/plans/2026-06-11-info-gathering-bot.md).
Contributions follow Git-flow (`develop` → `main`).
