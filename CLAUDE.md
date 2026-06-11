# CLAUDE.md

This file provides guidance to a coding agent when working with code in this repository.

## Documentation

Project documentation lives in `docs/`. When creating or updating plans, ExecPlans, or design docs, save them there. Reference existing docs in `docs/` for context on project phases and milestones.

Every document should be self-sufficient: the reader should never need to hunt for context. Explain concepts inline. When a concept is already defined in another checked-in document, you may reference it by file path and section rather than repeating it — but the reference must be precise enough that the reader can find it immediately (e.g., "see `docs/PLANS.md` § Milestones"), not vague ("see the architecture doc").

## ExecPlans

When writing complex features or significant refactors, use an ExecPlan (as described in `docs/PLANS.md`) from design to implementation. ExecPlans are the persistence layer for cross-session development — they carry forward all context, decisions, and progress so that a fresh session can continue the work without loss.

## Project Overview

`infobot` — a scheduled info-gathering bot: fetch (arXiv/RSS/Hacker News/Reddit) → dedup against SQLite → Claude summarize/categorize → post to Discord (Slack-ready) via incoming webhooks. Runs unattended every 2 hours on GitHub Actions. Full design history and decisions: `docs/plans/2026-06-11-info-gathering-bot.md`.

## Architecture

- **Two-repo split**: this repo (public) holds code only; private `Taka499/info-gathering-state` holds the live workflow, Actions secrets, and `seen.db` (committed back after each run). `.github/workflows/run.yml.sample` here is a non-executing reference — edit the live copy in the state repo to change CI behavior.
- **Deploying code = merge `develop` → `main` and push**; the cron checks out `main` of this repo on every run.
- Pipeline modules under `src/infobot/`: `config` (sources.yaml) → `fetchers/` → `store` (dedup; records ids at filter time so crashes never re-post) → `summarize` (Claude, fails open to raw excerpts) → `post` (webhooks resolved from `{DISCORD,SLACK}_WEBHOOK_<CATEGORY>` env vars; missing var = platform off).
- Reddit must be fetched via its RSS endpoint — the JSON API returns 403 to all anonymous clients. RSS hrefs arrive HTML-escaped; entry bodies carry the external URL in the `[link]` anchor.

## Setup and Development

- `uv sync` to install; run with `uv run python -m infobot --dry-run --no-llm` (add `--db`/`--config` to override paths).
- Local secrets in gitignored `.env` (strictly `KEY=VALUE` — a malformed line makes uv's `--env-file` echo the value into the terminal). `main()` loads it via python-dotenv; pytest does not, so use `uv run --env-file .env pytest` for the live-API test.
- `state/seen.db` is untracked working state; deleting rows from it is the way to force a re-post for testing.

## Build and Test

- `uv run pytest` — unit tests use checked-in fixtures and `httpx.MockTransport`; no network. The one live-API test auto-skips without `ANTHROPIC_API_KEY`.
- Before coding against any third-party endpoint, probe it with a 10-line `uv run python -c` script — every external API in this project (Reddit, arXiv redirects, archive-sized feeds) behaved differently than documented.

## Code Style

- Lean dependency policy: `httpx` for all HTTP, `feedparser` for all feed parsing, no platform SDKs (webhooks are plain POSTs). Pydantic only at the LLM boundary (`messages.parse`); dataclasses elsewhere.
- Fail open, never lose items: per-source and per-batch failures log and continue; an item missing from an LLM verdict posts with its defaults.
- Never log full webhook URLs — they embed secret tokens. The `httpx` logger is pinned to WARNING in `main()` for this reason; keep it that way.

## Commit Discipline

- Follow Git-flow workflow to manage the branches
- Use small, frequent commits rather than large, infrequent ones
- Only add and commit affected files; leave untracked files as they are
- Never add coding agent attribution in commits

