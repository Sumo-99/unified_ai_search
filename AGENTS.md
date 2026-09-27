# unified-ai-search

A sync Python SDK that gives one `search` / `extract` interface over You.com, Exa, Parallel, Tavily and Firecrawl, built as Strategy + Adapter (no dependency injection).

Built on ICM: folders carry sequencing, hierarchy carries context, files carry state. If something needs explaining, it goes in that folder's CONTEXT.md.

## Where things live

| Folder | What it holds |
|---|---|
| `stages/` | the build pipeline, in execution order |
| `_shared/` | factory: signed-off design, schemas, conventions, per-provider API facts |
| `_templates/` | blank starters: new provider facts are a copy, not a blank page |
| `src/unified_ai_search/` | product: the SDK code |
| `tests/` | product: `contract/` (all providers), `providers/` (per adapter), `live/` (opt-in) |

## Route by what just happened

| If | Go to | Then stop at |
|---|---|---|
| starting the build | `stages/01_scaffold/CONTEXT.md` | human runs the checks in its Human check |
| a stage's output approved | next numbered stage's CONTEXT.md | human reads its `output/report.md` |
| asked for status | scan `stages/*/output/` | report which stages have a report |
| adding a provider | `_templates/provider-facts.md`, then `stages/04_adapters/CONTEXT.md` | human reads the adapter report |
| asked what the SDK does or why | `_shared/design.md` | answer, link the section |
| provider facts, prices, or endpoints changed | `_shared/providers/<name>.md` | update it first, then the code |
| working on an implementation stage | `_shared/agent-tools.md` | use those tools per the guide |
| before committing code | `_shared/git-setup.md` | configure git, ensure attribution lines |

## Rules that never bend

- Nothing moves to the next stage until a person has read the last stage's report.
- TDD: a failing test exists before the code that satisfies it.
- One home per fact. Design lives in `_shared/`; code and stage files link to it, never restate it.
- Provider facts come from docs, not live calls. Anything unverified stays marked `UNVERIFIED` until a `live` test settles it.
- Secrets are never logged, committed or written to a report.
