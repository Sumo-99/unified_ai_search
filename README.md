# unified-ai-search

A synchronous Python SDK providing one `search` / `extract` interface over
You.com, Exa, Parallel, Tavily, and Firecrawl.

**Status: pre-release, under development.**

## Table of contents

- [Roadmap](#roadmap)
- [Install](#install)
- [Usage](#usage)
- [Examples](#examples)
- [Development](#development)

## Roadmap

| Stage | Scope | Status |
|---|---|---|
| 01_scaffold | Typed package and development tooling | Approved |
| 02_core | Core contracts and models | Approved |
| **03_client** | **Client orchestration** | **Current stage — awaiting human review** |
| 04_adapters | Provider adapters | Pending |
| 05_hardening | Verification and public documentation | Pending |

## Install

Installation instructions will be added in stage 05.

## Usage

Usage documentation will be added in stage 05.

## Examples

Examples will be added in stage 05.

## Development

This repository uses the ICM file system design for efficient agentic development
and human control: folders carry sequencing, hierarchy carries context, and files
carry state. Human review gates separate each implementation stage.

Start with [AGENTS.md](AGENTS.md) and the [build pipeline](CONTEXT.md).

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy src
```

Tests marked `live` are excluded by default. Run them explicitly with
`uv run pytest -m live` once they are implemented and credentials are configured.
