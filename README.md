# Brix

> **[中文文档](README_zh.md)**

A modular, multi-provider AI agent with a state machine orchestrator, tool calling, and persistent memory.

## Features

- **Multi-Provider LLM** — Unified interface for OpenAI-compatible and Anthropic-compatible APIs
- **Dual Orchestrator** — Pure Python state machine + LangGraph engine, switchable via config
- **Tool Calling** — Built-in tools: calculator, weather (mock), file reader
- **Persistent Memory** — Crash-safe JSON storage with atomic writes
- **Smart Routing** — Intent classification + complexity evaluation for automatic model selection
- **Extensible Config** — Add new providers and models by editing a single YAML file

---

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/kuicao55/Brix.git
cd Brix

# Create virtual environment (Python 3.11+ required)
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Configure API Keys

```bash
# Copy the example and fill in your keys
cp .env.example .env
```

Edit `.env`:

```env
# ZenMux aggregator (one key for all models)
ZENMUX_API_KEY=your-zenmux-key-here

# MiniMax official API
MINIMAX_API_KEY=your-minimax-key-here

# Mimo official API
MIMO_API_KEY=your-mimo-key-here
```

> Keys are auto-loaded via `python-dotenv` — no need to `export` manually.

### 3. Run

```bash
# Option A: Direct
.venv/bin/python main.py

# Option B: With venv activated
python main.py
```

---

## Shell Alias (Recommended)

Add a shell alias so you can launch Brix from anywhere with a single command.

### Setup

Add this line to your shell config file:

**Zsh** (default on macOS) — edit `~/.zshrc`:
```bash
alias brix="cd ~/Applications/Brix && .venv/bin/python main.py"
```

**Bash** — edit `~/.bashrc` or `~/.bash_profile`:
```bash
alias brix="cd ~/Applications/Brix && .venv/bin/python main.py"
```

> Replace `~/Applications/Brix` with your actual project path if different.

Then reload your shell:

```bash
source ~/.zshrc   # or source ~/.bashrc
```

### Usage

```bash
# Launch Brix from anywhere
brix

# That's it — no need to activate venv or cd into the project
```

### Removing the Alias

To remove, delete the `alias brix=...` line from your shell config and reload.

---

## REPL Commands

| Command | Description |
|---------|-------------|
| `/quit` | Exit Brix |
| `/clear` | Clear conversation history |
| `/model` | Show current model |
| `/history` | Show recent messages |

---

## Configuration Guide

All configuration lives in `config/settings.yaml`. This is the single file you edit to add providers, models, and change behavior.

### Adding a New Provider

A provider is an API endpoint. Add 3 lines under `providers:`:

```yaml
providers:
  # Existing providers...

  deepseek:                              # Provider name (any unique key)
    base_url: "https://api.deepseek.com/anthropic"  # API endpoint
    api_key_env: "DEEPSEEK_API_KEY"     # Env var name for the API key
    protocol: "anthropic"               # "anthropic" or "openai"
```

Then add the API key to `.env`:

```env
DEEPSEEK_API_KEY=your-key-here
```

**Protocol guide:**
- `"anthropic"` — For APIs that use the Anthropic Messages format (e.g., Claude, MiniMax, Mimo)
- `"openai"` — For APIs that use the OpenAI Chat Completions format (e.g., GPT, DeepSeek via ZenMux)

### Adding a New Model

Add an entry under `models:`:

```yaml
models:
  # Existing models...

  - id: "deepseek/deepseek-chat"         # Format: provider/model-name
    provider: "deepseek"                  # Must match a key in providers
    purpose: ["fast_chat", "coding"]      # When to use this model
    capabilities: ["tool_calling"]        # What it can do
    max_context: 64000                    # Context window size
    cost_tier: "low"                      # "low", "medium", or "high"
```

### Model ID Format

Model IDs follow the pattern `provider/model-name`:

| Example ID | Provider | Model |
|------------|----------|-------|
| `minimax/MiniMax-M2.7` | minimax | MiniMax-M2.7 |
| `mimo/mimo-v2.5-pro` | mimo | mimo-v2.5-pro |
| `zenmux-openai/deepseek/deepseek-v4-pro` | zenmux-openai | deepseek/deepseek-v4-pro |

For aggregator platforms like ZenMux, the model name includes the vendor prefix (e.g., `deepseek/deepseek-v4-pro`).

### Model Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique model identifier (`provider/model-name`) |
| `provider` | string | Must match a key in `providers` |
| `purpose` | list | When to use: `fast_chat`, `coding`, `reasoning`, `planning`, `analysis`, `simple_qa`, `image_generation`, `video_generation` |
| `capabilities` | list | Features: `tool_calling`, `strong_reasoning`, `low_latency`, `low_cost`, `long_context`, `image_generation`, `video_generation` |
| `max_context` | int | Context window in tokens |
| `cost_tier` | string | `"low"`, `"medium"`, or `"high"` |
| `default` | bool | Set `true` to make this the default model (optional) |

### Default & Fallback Models

```yaml
routing:
  default_model: "minimax/MiniMax-M2.7"                    # Primary model
  fallback_model: "zenmux-openai/deepseek/deepseek-v4-flash"  # Used if primary fails
```

---

## Switching the Orchestrator Layer

Brix has two orchestrator engines that control how the agent processes requests:

| Engine | Description | Best For |
|--------|-------------|----------|
| `state_machine` | Pure Python state machine. No extra dependencies. | Default, lightweight, fast |
| `langgraph` | LangGraph StateGraph with visual workflow. Requires `langgraph`. | Complex multi-step tasks, debugging |

### How to Switch

Edit `config/settings.yaml`, change the `engine` field:

```yaml
engine: "state_machine"   # Pure Python (default)
```

or:

```yaml
engine: "langgraph"       # LangGraph StateGraph
```

Save the file — the change takes effect on next launch.

### Installing LangGraph

If you want to use the `langgraph` engine, install it:

```bash
pip install langgraph
```

If LangGraph is not installed and you set `engine: "langgraph"`, Brix will automatically fall back to `state_machine` with a warning.

### When to Use Which?

- **`state_machine`** — Recommended for most users. Simple, fast, no extra dependencies.
- **`langgraph`** — Use when you need graph-based orchestration with explicit state transitions. Better for debugging complex multi-tool workflows.

---

## Architecture

```
+-----------------------------------------------------+
|                      CLI Layer                       |
|                  cli/app.py (REPL)                   |
+-----------------------------------------------------+
|                   Router Layer                       |
|  router/intent.py  router/complexity.py              |
|  router/model_router.py                              |
+-----------------------------------------------------+
|                Orchestrator Layer                     |
|  orchestrator/state_machine.py  (Pure Python)        |
|  orchestrator/langgraph_engine.py (LangGraph)        |
+-----------------------------------------------------+
|                  Capability Layer                     |
|  capability/runner.py (ToolRunner)                   |
|  capability/tools/calculator.py                      |
|  capability/tools/weather.py                         |
|  capability/tools/file_read.py                       |
+-----------------------------------------------------+
|                   Infra Layer                        |
|  infra/llm_client.py (Unified LLM Client)            |
|  infra/providers/openai_compat.py                    |
|  infra/providers/anthropic_compat.py                 |
+-----------------------------------------------------+
|                   Config Layer                       |
|  config/loader.py  config/model_registry.py          |
|  config/settings.yaml                                |
+-----------------------------------------------------+
|                   Memory Layer                       |
|  memory/storage.py (Atomic JSON)                     |
|  memory/strategy.py (Context Window)                 |
+-----------------------------------------------------+
```

### Data Flow

```
User Input
    |
    v
Intent Classification (chat / task / tool_use)
    |
    v
Complexity Evaluation (low / medium / high)
    |
    v
Model Selection (based on intent + complexity + config)
    |
    v
Orchestrator Loop
    |
    +---> LLM Call ---> Tool Calls? ---> Execute Tools ---> Review --+
    |                                                                |
    +----------------------------------------------------------------+
    |
    v
Response + Memory Persist
```

---

## Project Structure

```
brix/
+-- main.py                          # Entry point
+-- pyproject.toml                   # Project config & dependencies
+-- config/
|   +-- settings.yaml                # Provider & model configuration
|   +-- loader.py                    # YAML config loader
|   +-- model_registry.py           # Model lookup by id/purpose
+-- infra/
|   +-- llm_client.py               # Unified LLM client
|   +-- providers/
|       +-- openai_compat.py        # OpenAI-compatible adapter
|       +-- anthropic_compat.py     # Anthropic-compatible adapter
+-- router/
|   +-- intent.py                   # Intent classification
|   +-- complexity.py               # Complexity evaluation
|   +-- model_router.py             # Model selection logic
+-- orchestrator/
|   +-- engine.py                   # OrchestratorEngine protocol
|   +-- states.py                   # State enum
|   +-- state_machine.py            # Pure Python state machine
|   +-- langgraph_engine.py         # LangGraph-based engine
+-- capability/
|   +-- base.py                     # Tool abstract base class
|   +-- runner.py                   # ToolRunner registry
|   +-- tools/
|       +-- calculator.py           # Math expression evaluator
|       +-- weather.py              # Mock weather lookup
|       +-- file_read.py            # Local file reader
+-- memory/
|   +-- storage.py                  # Atomic JSON persistence
|   +-- strategy.py                 # Context window management
+-- cli/
|   +-- app.py                      # REPL interface
|   +-- display.py                  # Output formatting
+-- tests/
    +-- test_config.py              # Config layer tests
    +-- test_infra.py               # Infra layer tests
    +-- test_orchestrator.py        # Orchestrator tests
    +-- test_langgraph.py           # LangGraph engine tests
    +-- test_router.py              # Router tests
    +-- test_capability.py          # Tool & runner tests
    +-- test_memory.py              # Memory tests
    +-- test_cli.py                 # CLI tests
```

---

## Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
python -m pytest tests/ -v

# Run specific module
python -m pytest tests/test_orchestrator.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Async | asyncio |
| REPL | prompt_toolkit |
| Config | PyYAML |
| HTTP | httpx |
| LLM (OpenAI) | openai SDK |
| LLM (Anthropic) | anthropic SDK |
| Orchestrator | langgraph (optional) |
| Env Loading | python-dotenv |
| Testing | pytest + pytest-asyncio |

---

## License

Private project.
