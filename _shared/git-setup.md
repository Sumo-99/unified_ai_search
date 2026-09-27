# Git setup and commit conventions

Configure git before any stage writes commits.

## Local git config

```bash
git config user.name "Sumo-99"
git config user.email "sumanthssr@gmail.com"
```

Or globally (if you want this for all projects):
```bash
git config --global user.name "Sumo-99"
git config --global user.email "sumanthssr@gmail.com"
```

## Commit message format

Every commit message must end with an attribution line naming the agent that wrote it. This records who (or what) made the change.

**Format:**
```
{brief summary of changes}

{optional longer description}

Co-Authored-By: {agent name and contact}
```

**Examples:**

For Claude Haiku 4.5:
```
Implement SearchClient validation

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

For Claude Sonnet 5:
```
Add tavily adapter and fixtures

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

For Claude Opus:
```
Full contract suite and live tests passing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

For a human contributor:
```
Update provider fact sheets after API review

Co-Authored-By: Sumo-99 <sumanthssr@gmail.com>
```

## Before any stage writes to git

1. Verify git config is set to the correct user.
2. Ensure all commits include the attribution line.
3. Never commit secrets (API keys, `.env` files are in `.gitignore`).
