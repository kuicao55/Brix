# Brix

A modular, multi-provider AI agent with a state machine orchestrator, tool calling, and persistent memory.

## Features

- **Multi-Provider LLM** — Unified interface for OpenAI-compatible and Anthropic-compatible APIs
- **Dual Orchestrator** — Pure Python state machine + LangGraph engine, switchable via config
- **Tool Calling** — Built-in tools: calculator, weather (mock), file reader
- **Persistent Memory** — Crash-safe JSON storage with atomic writes
- **Smart Routing** — Intent classification + complexity evaluation for automatic model selection
- **Extensible Config** — Add new providers and models by editing a single YAML file

## Quick Start

```bash
# 1. Clone and enter the project
cd ~/Applications/Brix

# 2. Create .env with your API keys
echo "ZENMUX_API_KEY=your-key" > .env
echo "MINIMAX_API_KEY=your-key" >> .env

# 3. Run (virtual environment is already set up)
.venv/bin/python main.py
```

Or use the shell alias (already configured):

```bash
brix
```

## REPL Commands

| Command | Description |
|---------|-------------|
| `/quit` | Exit |
| `/clear` | Clear conversation history |
| `/model` | Show current model |
| `/history` | Show recent messages |

## Configuration

All configuration lives in `config/settings.yaml`.

### Adding a New Provider

Add 3 lines under `providers`:

```yaml
  deepseek:
    base_url: "https://api.deepseek.com/anthropic"
    api_key_env: "DEEPSEEK_API_KEY"
    protocol: "anthropic"    # or "openai"
```

Then add the API key to `.env`:

```
DEEPSEEK_API_KEY=your-key
```

### Adding a New Model

Add under `models`:

```yaml
  - id: "deepseek/deepseek-chat"
    provider: "deepseek"
    purpose: ["fast_chat", "coding"]
    capabilities: ["tool_calling"]
    max_context: 64000
    cost_tier: "low"
```

### Model ID Format

```
provider/model-name
```

Examples: `minimax/MiniMax-M2.7`, `mimo/mimo-v2.5-pro`, `zenmux-openai/deepseek/deepseek-v4-pro`

### Switching Orchestrator Engine

```yaml
engine: "state_machine"   # Pure Python (default)
# or
engine: "langgraph"       # LangGraph StateGraph
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      CLI Layer                       │
│                  cli/app.py (REPL)                   │
├─────────────────────────────────────────────────────┤
│                   Router Layer                       │
│  router/intent.py  router/complexity.py              │
│  router/model_router.py                              │
├─────────────────────────────────────────────────────┤
│                Orchestrator Layer                     │
│  orchestrator/state_machine.py  (Pure Python)        │
│  orchestrator/langgraph_engine.py (LangGraph)        │
├─────────────────────────────────────────────────────┤
│                  Capability Layer                     │
│  capability/runner.py (ToolRunner)                   │
│  capability/tools/calculator.py                      │
│  capability/tools/weather.py                         │
│  capability/tools/file_read.py                       │
├─────────────────────────────────────────────────────┤
│                   Infra Layer                        │
│  infra/llm_client.py (Unified LLM Client)            │
│  infra/providers/openai_compat.py                    │
│  infra/providers/anthropic_compat.py                 │
├─────────────────────────────────────────────────────┤
│                   Config Layer                       │
│  config/loader.py  config/model_registry.py          │
│  config/settings.yaml                                │
├─────────────────────────────────────────────────────┤
│                   Memory Layer                       │
│  memory/storage.py (Atomic JSON)                     │
│  memory/strategy.py (Context Window)                 │
└─────────────────────────────────────────────────────┘
```

### Data Flow

```
User Input
    │
    ▼
Intent Classification (chat / task / tool_use)
    │
    ▼
Complexity Evaluation (low / medium / high)
    │
    ▼
Model Selection (based on intent + complexity + config)
    │
    ▼
Orchestrator Loop
    │
    ├──► LLM Call ──► Tool Calls? ──► Execute Tools ──► Review ──┐
    │                                                            │
    └────────────────────────────────────────────────────────────┘
    │
    ▼
Response + Memory Persist
```

## Project Structure

```
brix/
├── main.py                          # Entry point
├── pyproject.toml                   # Project config & dependencies
├── config/
│   ├── settings.yaml                # Provider & model configuration
│   ├── loader.py                    # YAML config loader
│   └── model_registry.py           # Model lookup by id/purpose
├── infra/
│   ├── llm_client.py               # Unified LLM client
│   └── providers/
│       ├── openai_compat.py        # OpenAI-compatible adapter
│       └── anthropic_compat.py     # Anthropic-compatible adapter
├── router/
│   ├── intent.py                   # Intent classification
│   ├── complexity.py               # Complexity evaluation
│   └── model_router.py             # Model selection logic
├── orchestrator/
│   ├── engine.py                   # OrchestratorEngine protocol
│   ├── states.py                   # State enum
│   ├── state_machine.py            # Pure Python state machine
│   └── langgraph_engine.py         # LangGraph-based engine
├── capability/
│   ├── base.py                     # Tool abstract base class
│   ├── runner.py                   # ToolRunner registry
│   └── tools/
│       ├── calculator.py           # Math expression evaluator
│       ├── weather.py              # Mock weather lookup
│       └── file_read.py            # Local file reader
├── memory/
│   ├── storage.py                  # Atomic JSON persistence
│   └── strategy.py                 # Context window management
├── cli/
│   ├── app.py                      # REPL interface
│   └── display.py                  # Output formatting
└── tests/
    ├── test_config.py              # Config layer tests
    ├── test_infra.py               # Infra layer tests
    ├── test_orchestrator.py        # Orchestrator tests
    ├── test_langgraph.py           # LangGraph engine tests
    ├── test_router.py              # Router tests
    ├── test_capability.py          # Tool & runner tests
    ├── test_memory.py              # Memory tests
    └── test_cli.py                 # CLI tests
```

## Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests (74 tests)
python -m pytest tests/ -v

# Run specific module
python -m pytest tests/test_orchestrator.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

## Tech Stack

- **Python 3.11+**
- **asyncio** — Async event loop
- **prompt_toolkit** — Interactive REPL
- **PyYAML** — Configuration parsing
- **httpx** — HTTP client
- **openai** — OpenAI-compatible provider
- **anthropic** — Anthropic-compatible provider
- **langgraph** — Graph-based orchestrator engine
- **pytest + pytest-asyncio** — Testing

## License

Private project.
