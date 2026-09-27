# Agent tool guidance

When implementing any stage in the pipeline, use these MCP tools as the primary research and code-processing layer. They keep raw bytes out of the conversation and preserve token budget.

## Context-mode MCP (`mcp__plugin_context-mode_context-mode__*`)

Use when working with large outputs, logs, or needing to process data.

| Task | Tool |
|---|---|
| Analyze test output, filter errors, count results | `ctx_execute(language="python", code="...")` — output printed is what enters conversation |
| Extract or process files (JSON, CSV, logs) | `ctx_execute_file(path, language, code)` — run analysis in sandbox, only return what you print |
| Run shell commands and aggregate results | `ctx_batch_execute(commands=[...], queries=[...])` — indexes each output, returns matching sections in one round trip |
| Search previous session captures or indexed files | `ctx_search(queries=[...], source="session-events")` — query per-command data without re-reading raw bytes |

## Context7 MCP (`mcp__claude_ai_Context7__*`)

Use for looking up current API documentation and library references.

| Task | Tool |
|---|---|
| Get current docs for a library or API | `query_docs` — always use this before writing code that depends on library versions; docs may have changed since training |
| Resolve library IDs for Context7's knowledge graph | `resolve_library_id` — match a library name to its documented version |

**When to use:** Before implementing any provider adapter (stage 04), load the provider's current docs via `query_docs` to verify the endpoints, field names, and response shapes against what's in `_shared/providers/<name>.md`. Mark any drift in the provider fact sheet.

## Example patterns

**Processing test output without bloating context:**
```
ctx_execute(language="python", code="""
import json
# read and filter the test report
lines = open('/path/to/report.json').readlines()
results = [json.loads(l) for l in lines if 'FAILED' in l]
print(f"Failed tests: {len(results)}")
for r in results: print(f"  {r['name']}")
""")
```

**Batch-running shell checks:**
```
ctx_batch_execute(
  commands=[
    {"label": "type check", "command": "cd /path && mypy src"},
    {"label": "lint", "command": "cd /path && ruff check src"},
    {"label": "tests", "command": "cd /path && pytest tests/"}
  ],
  queries=["failures", "warnings"]  # returns matching lines only
)
```

**Verifying provider docs haven't drifted:**
```
# Before stage 04 on a new provider:
query_docs(library="firecrawl", query="POST /v2/search endpoint request parameters and response shape")
# Compare result against _shared/providers/firecrawl.md; update if drift found
```

## Golden rule

Never load a full file, API spec, or test output into the conversation to read it. Process it in the sandbox and print only the answer. This keeps the token budget healthy and readable.
