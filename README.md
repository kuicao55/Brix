# Brix

> **[中文文档](README_zh.md)**

A modular, multi-provider AI agent with a state machine orchestrator, tool calling, and persistent memory.

## Features

- **Multi-Provider LLM** — Unified interface for OpenAI-compatible and Anthropic-compatible APIs
- **Dual Orchestrator** — Pure Python state machine + LangGraph engine, switchable via config
- **Streaming Output** — Real-time token-by-token rendering with safe-boundary Markdown detection
- **Tool Calling** — Built-in tools: calculator, weather (mock), file reader
- **Persistent Memory** — Crash-safe JSON storage with atomic writes
- **Smart Routing** — Intent classification + complexity evaluation for automatic model selection
- **Rich Terminal UI** — Animated spinner, tool execution panels, styled banner, custom theme, inline response markers
- **Extensible Config** — Add new providers and models by editing a single YAML file
- **Flow Log** — Automatic data flow recording for every conversation turn, for debugging and auditing
- **Hook System** — Event-driven architecture with `HookRegistry`; core modules fire events via `hooks.fire()`, FlowLog acts as default listener, easily extensible with custom hooks

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
| `/log` | Show recent 20 flow log entries |
| `/log <N>` | View detailed info for log entry #N |

---

## Flow Log

Brix automatically records the complete data flow for every conversation turn, stored in `data/logs/brix.jsonl` (JSONL format).

### Viewing Logs

```
you> /log
Recent logs (newest first, 1-3):

  #1  2026-05-07T15:36:12 [a3f8b21c]  12500ms OK  "What's the weather in Shanghai tomorrow?"
  #2  2026-05-07T15:35:05 [49621c65]  7644ms  OK  "你好"

Use /log <number> to view details
```

### Viewing Detailed Logs

```
you> /log 1
------------------------------------------------------------
  Trace:  49621c65
  Time:   2026-05-07T15:35:05
  Input:  你好
  Model:  minimax/MiniMax-M2.7
  Status: OK
------------------------------------------------------------
  [1] memory  @15:35:05.203  0.2s
      Load history from storage, trim context window
      msgs: 0, window: 0, chars: 0

  [2] intent  @15:35:09.738  4.5s
      Call LLM to classify user intent (chat/task/tool_use)
      result: chat | via: llm | model: minimax/MiniMax-M2.7
      response: chat

  [3] complexity  @15:35:09.738  0.0s
      Evaluate request complexity based on keyword rules
      result: low

  [4] router  @15:35:09.738  0.0s
      Select best model based on intent and complexity
      model: minimax/MiniMax-M2.7

  [5] orch_plan  @15:35:12.844  3.1s
      Call LLM to generate response or decide tool calls
      response: 你好！有什么我可以帮助你的吗？

  [6] persist  @15:35:12.846  0.0s
      Save conversation to storage
      saved: 2
```

### Log Fields

Each step records:

| Field | Description |
|-------|-------------|
| `@HH:MM:SS.mmm` | Wall-clock time when the step completed |
| `X.Xs` | Actual duration of the step |
| `prompt` | Full message list sent to the LLM |
| `response` | Raw LLM response content |
| `ms` | Precise LLM call or tool execution time (ms) |

### Recorded Steps

| Step | Description |
|------|-------------|
| `memory` | Load history from storage, build context window |
| `intent` | LLM classifies user intent, records prompt and response |
| `complexity` | Rule-based request complexity evaluation |
| `router` | Select model based on intent and complexity |
| `orch_plan` | LLM generates response or decides tool calls, records full prompt |
| `tool_exec` | Execute tools and record input/output |
| `persist` | Save conversation to storage |

---

## Hook System

Brix uses an event-driven architecture via `HookRegistry`. Core modules (router, orchestrator, CLI) fire events through `hooks.fire()` instead of calling `FlowLog` directly. FlowLog acts as the default listener, automatically receiving all events.

### How It Works

```
Core modules ---(hooks.fire())---> HookRegistry ---(auto-forward)---> FlowLog.step()
                                       |
                                       +---> Custom hooks (future extensions)
```

### Registering Custom Hooks

```python
from hooks.registry import HookRegistry

hooks = HookRegistry()
hooks.bind_log(log)  # FlowLog receives all events

# Register a custom hook for specific events
hooks.register("tool_exec", lambda e: print(f"Tool called: {e.data['name']}"))
hooks.register("intent", lambda e: audit_log(e))
```

### Available Events

| Event | Trigger Location | Data Fields |
|-------|-----------------|-------------|
| `memory` | cli/app.py | `msgs`, `window`, `chars` |
| `intent` | router/intent.py | `result`, `via`, `model`, `ms` |
| `complexity` | cli/app.py | `result` |
| `router` | cli/app.py | `model`, `reason` |
| `orch_plan` | orchestrator/ | `iter`, `tools`, `ms`, `response` |
| `tool_exec` | orchestrator/ | `name`, `args`, `result`, `ms` |
| `persist` | cli/app.py | `saved` |

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
|                    Log Layer                          |
|  log/flow.py (FlowLog Collector)                     |
|  log/writer.py (JSONL File I/O)                      |
+-----------------------------------------------------+
|                   Hook Layer                          |
|  hooks/registry.py (HookRegistry + HookEvent)        |
|  Core modules fire events → FlowLog auto-receives    |
+-----------------------------------------------------+
|                 Terminal UI Layer                     |
|  cli/stream_renderer.py (Markdown stream rendering)  |
|  cli/spinner.py (Braille animation)                  |
|  cli/stage_indicator.py (unified loading spinner)    |
|  cli/tool_display.py (tool execution panels)         |
|  cli/theme.py (Rich theme)                           |
|  cli/banner.py (startup banner)                      |
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
+-- log/
|   +-- flow.py                     # FlowLog step collector
|   +-- writer.py                   # JSONL file I/O
+-- hooks/
|   +-- registry.py                 # HookRegistry + HookEvent
|   +-- __init__.py                 # Re-exports
+-- cli/
|   +-- app.py                      # REPL interface (streaming pipeline)
|   +-- display.py                  # Output formatting
|   +-- stream_renderer.py          # Safe-boundary Markdown stream renderer
|   +-- spinner.py                  # Braille dot animation spinner
|   +-- stage_indicator.py          # Unified loading spinner (update in-place)
|   +-- tool_display.py             # Tool execution status panels
|   +-- theme.py                    # Rich theme (markdown, tool, spinner styles)
|   +-- banner.py                   # Startup ASCII banner
+-- tests/
    +-- test_config.py              # Config layer tests
    +-- test_infra.py               # Infra layer tests
    +-- test_orchestrator.py        # Orchestrator tests
    +-- test_langgraph.py           # LangGraph engine tests
    +-- test_router.py              # Router tests
    +-- test_capability.py          # Tool & runner tests
    +-- test_memory.py              # Memory tests
    +-- test_cli.py                 # CLI tests
    +-- test_flow_log.py            # Flow log tests
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
| Terminal UI | Rich (Live, Markdown, Panel, Theme) |
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
