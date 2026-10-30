# Abstrator

> Recursive abstraction research — decomposes any idea into sub-concepts, researches each through named lenses, and synthesizes structured JSON with cited sources.

## What it is

Abstrator is an **MCP server + CLI** that takes a question or topic and runs a recursive chain:

1. **Decomposition** — breaks the concept into simpler sub-concepts (via LLM)
2. **Lens-based research** — each sub-concept is researched through fixed, named perspectives (`meaning`, `theory`, `practice`, `existing_tools`…) using local SearXNG + page fetching
3. **Bottom-up integration** — synthesizes children's findings into the parent, preserving conflicts and gaps
4. **Root synthesis** — produces a final summary with cited sources, open questions, and a learning path

The output is a `Run` with a node tree, indexed sources, learning path and recommendations — all in typed JSON.

---

## Why it's different

**Named, fixed lenses.** Instead of generic search, each sub-concept is researched across explicit dimensions. This produces rich, comparable context across runs — not a list of links.

**Hard budget per run.** Configurable limits on queries, pages, LLM calls, tokens, seconds and USD — tracked in real time. When any limit is hit, the run stops and returns whatever was processed, with no surprise costs.

**Local SearXNG.** Web search with no paid API dependency and no tracking. You control the index, cache and enabled sources.

**MCP-native from the start.** The MCP server is not a wrapper added later — it's the primary interface. All tools (`abstract`, `assess_complexity`, `expand_node`, `research_concept`) are designed for use in AI conversations, returning structured JSON with real-time progress support.

**Multiple LLM providers.** Switch provider without changing code — Anthropic, Ollama, OpenRouter, OpenCode, Gemini CLI — with automatic resolution based on configured keys.

---

## Quick start

```bat
REM 1. Prepare environment (Python, uv, deps, Docker, SearXNG)
preparar.bat

REM 2. Fill in credentials
notepad .env

REM 3. Use
uv run abstrator run "microservices architecture"
uv run abstrator run "machine learning" --mode deep
uv run abstrator mcp        REM start MCP server (stdio)
```

---

## Running the MCP server

### Option 1 — Claude Code (recommended)

```bash
claude mcp add abstrator -- uv --directory "C:\Projetos\abstrator" run abstrator mcp
```

Then use it in any conversation:
```
assess_complexity("event sourcing")
abstract("event sourcing", mode="standard")
```

### Option 2 — Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "uv",
      "args": ["--directory", "C:\\Projetos\\abstrator", "run", "abstrator", "mcp"]
    }
  }
}
```

Restart Claude Desktop — the tools appear automatically.

### Option 3 — Gemini CLI

Add to `%USERPROFILE%\.gemini\settings.json`:

```json
{
  "mcpServers": {
    "abstrator": {
      "command": "uv",
      "args": ["--directory", "C:\\Projetos\\abstrator", "run", "abstrator", "mcp"]
    }
  }
}
```

### Option 4 — OpenCode

Create `opencode.json` in your project folder:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "abstrator": {
      "type": "local",
      "command": ["uv", "--directory", "C:\\Projetos\\abstrator", "run", "abstrator", "mcp"],
      "enabled": true
    }
  }
}
```

### Option 5 — Launcher BAT

Run `iniciar-abstrator-mcp.bat` — it starts Docker/SearXNG and launches the MCP server in a separate window. Keep that window open while using.

### Smoke test (verify it works)

```bash
uv run python scripts/smoke_mcp.py
```

---

## MCP tools

| Tool | Description |
|---|---|
| `assess_complexity` | Checks if a concept needs decomposition (cheap — use first) |
| `abstract` | Runs the full recursive chain, returns the Run JSON |
| `research_concept` | Researches a single concept without recursion |
| `expand_node` | Deepens a node that stopped early (e.g. MAX_DEPTH) |
| `get_run` | Retrieves a saved Run |
| `list_runs` | Lists recent Runs |
| `cancel_run` | Kill switch for a running abstract() call |

### Recommended conversation flow

```
1. assess_complexity("my topic")           → decide whether to run abstract() or research_concept()
2. abstract("my topic", mode="standard")   → full Run with tree and sources
3. expand_node(run_id, node_id)            → deepen a node that stopped at max_depth
```

---

## Installation

### Prerequisites

| Tool | Min version | Purpose |
|---|---|---|
| Python | 3.12 | runtime |
| [uv](https://docs.astral.sh/uv/) | any | package manager |
| Docker Desktop | any | local SearXNG |
| API key or Ollama | — | LLM |

```bash
uv sync
cp .env.example .env   # edit with your keys
docker compose up -d
uv run abstrator doctor
```

---

## Environment variables (`.env`)

```env
# Provider: opencode_zen | anthropic | ollama | openrouter | gemini_cli | fake
ABSTRATOR_LLM_PROVIDER=auto   # auto-detects from available keys

# OpenCode
OPENCODE_API_KEY=sk-...
ABSTRATOR_LLM_MODEL=claude-sonnet-5

# Anthropic (direct — prompt caching enabled)
ANTHROPIC_API_KEY=sk-ant-...

# Ollama (local, zero cost)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2.5:14b

# OpenRouter (hundreds of models, one key)
OPENROUTER_API_KEY=sk-or-...

# SearXNG
SEARXNG_URL=http://localhost:8080
```

### Auto-resolution order (`auto`)

1. `opencode_zen` — if `OPENCODE_API_KEY` is set
2. `anthropic` — if `ANTHROPIC_API_KEY` is set
3. `openrouter` — if `OPENROUTER_API_KEY` is set
4. `gemini_cli` — fallback (no key needed, uses `gemini` binary)

---

## Search modes

| Mode | Depth | Fanout | Lenses | Budget scale |
|---|---|---|---|---|
| `quick` | 2 | 3 | meaning, practice, existing_tools | 0.35× |
| `standard` | 3 | 4 | all integration lenses | 1.0× |
| `deep` | 5 | 5 | all | 2.5× |

---

## Available lenses

| Lens | What it researches |
|---|---|
| `meaning` | Precise definition, concept boundaries |
| `analogy` | Analogies from other domains (with where they break) |
| `theory` | Theoretical framework, state of the art |
| `practice` | Real step-by-step, costs, decisions |
| `best_practices` | Practitioner rules + the typical error each prevents |
| `expert_views` | Positions of recognized researchers and authors |
| `advanced_methods` | Sophisticated approaches with criteria for use |
| `existing_tools` | Tools, libs, services with URLs |

---

## LLM providers

| Provider | Key needed | Notes |
|---|---|---|
| `opencode_zen` | `OPENCODE_API_KEY` | Default. OpenAI-compatible gateway |
| `anthropic` | `ANTHROPIC_API_KEY` + `uv add anthropic` | Native prompt caching — reduces cost up to 90% on long runs |
| `ollama` | none | Local models, zero token cost |
| `openrouter` | `OPENROUTER_API_KEY` | Hundreds of models, one key |
| `gemini_cli` | none | Delegates to `gemini` binary |
| `fake` | none | Deterministic, no network — tests only |

---

## Budget limits

Hard limits — when any is reached the run stops and returns partial results:

| Variable | Default | Limits |
|---|---|---|
| `ABSTRATOR_BUDGET_MAX_QUERIES` | 60 | web searches |
| `ABSTRATOR_BUDGET_MAX_PAGES` | 120 | pages downloaded |
| `ABSTRATOR_BUDGET_MAX_LLM_CALLS` | 80 | LLM calls |
| `ABSTRATOR_BUDGET_MAX_TOKENS` | 400 000 | total tokens |
| `ABSTRATOR_BUDGET_MAX_SECONDS` | 900 | total time |
| `ABSTRATOR_BUDGET_MAX_USD` | 2.0 | estimated cost in USD |

Modes scale budget proportionally: `quick` = 0.35×, `standard` = 1×, `deep` = 2.5×.

---

## CLI reference

```
abstrator run <query>                      Run full research
abstrator run <query> --mode quick|standard|deep
abstrator run <query> --lenses meaning,practice,existing_tools
abstrator expand <run_id> <node_id>        Deepen a specific node
abstrator runs                             List saved runs
abstrator get <run_id>                     Show run JSON
abstrator improve                          Meta-mode: abstracts the project itself
abstrator eval <run_id>                    Offline quality evaluation
abstrator mcp                              Start MCP server (stdio)
abstrator doctor                           Health check
abstrator schema                           Export JSON Schema
```

---

## Tests

```bash
uv run pytest              # all tests
uv run pytest -x           # stop on first failure
uv run pytest tests/test_orchestrator.py
```

---

## Architecture

```
CLI (typer)  /  MCP (MCPServer)
        └── Orchestrator
                ├── assess_complexity  (LLM)
                ├── decompose          (LLM → SubConcept[])
                ├── ResearchEngine
                │     ├── SearxngClient  (local web search)
                │     ├── Fetcher        (download + trafilatura)
                │     └── LLMRunner      (per-lens analysis)
                ├── integrate          (LLM bottom-up)
                └── synthesize_root    (LLM final synthesis)

Store : runs/<run_id>/result.json + report.md + audit.jsonl
Cache : data/abstrator.sqlite3  (search, page, concept, llm — configurable TTL)
```

---

## Contributing

1. Fork + branch from `main`
2. `uv sync` to install dev deps
3. Write tests before implementing (TDD London School)
4. `uv run pytest` — all tests must pass
5. Open PR with problem description and solution

---

## Documentation

- [README em Português](docs/README.ptbr.md)
