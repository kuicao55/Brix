# Brix

> **[中文文档](README_zh.md)**

A modular, multi-provider AI agent with a state machine orchestrator, tool calling, and persistent memory.

## Features

- **Multi-Provider LLM** — Unified interface for OpenAI-compatible and Anthropic-compatible APIs
- **Dual Orchestrator** — Pure TypeScript state machine + LangGraph engine, switchable via config
- **Streaming Output** — Real-time token-by-token rendering with safe-boundary Markdown detection
- **Tool Calling** — Built-in tools: calculator, weather, file reader, file writer, file editor
- **Memory System v2** — Session-isolated conversations, agent personality (soul.md), user profile (user.md), auto-onboarding
- **Persistent Storage** — Crash-safe atomic writes with proper-lockfile
- **Smart Routing** — Intent classification + complexity evaluation for automatic model selection
- **Rich Terminal UI** — Thinking spinner during LLM gap, tool execution panels, content indentation with compact paragraph spacing, styled banner, custom theme, inline response markers
- **Slash Autocomplete** — Type `/` to see command suggestions with fuzzy matching; Tab to accept, Up/Down to navigate
- **Extensible Config** — Add new providers and models by editing a single YAML file
- **Flow Log** — Automatic data flow recording for every conversation turn, for debugging and auditing
- **Hook System** — Event-driven architecture with `HookRegistry`; core modules fire events via `hooks.fire()`, FlowLog acts as default listener, easily extensible with custom hooks

---

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/kuicao55/Brix.git
cd Brix

# Install dependencies (Bun 1.3+ required)
bun install
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

> Keys are auto-loaded via `dotenv` — no need to `export` manually.

### 3. Run

```bash
# Development mode
bun run src/entrypoints/cli.ts

# Or using npm script
bun run dev
```

---

## Shell Alias (Recommended)

Add a shell alias so you can launch Brix from anywhere with a single command.

### Setup

Add this line to your shell config file:

**Zsh** (default on macOS) — edit `~/.zshrc`:
```bash
alias brix="cd ~/Applications/Brix && bun run src/entrypoints/cli.ts"
```

**Bash** — edit `~/.bashrc` or `~/.bash_profile`:
```bash
alias brix="cd ~/Applications/Brix && bun run src/entrypoints/cli.ts"
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

# That's it — no need to cd into the project
```

### Removing the Alias

To remove, delete the `alias brix=...` line from your shell config and reload.

---

## REPL Commands

| Command | Description |
|---------|-------------|
| `/help` | List all available commands |
| `/quit` | Save session and exit (also `/exit`) |
| `/clear` | Clear current session and start fresh |
| `/resume` | Browse and resume previous sessions (interactive TUI with pagination) |
| `/history` | Show current session messages |
| `/soul` | Show agent personality (soul.md) |
| `/user` | Show user profile (user.md) |
| `/model` | Show current model |
| `/log` | Interactive log viewer (arrow keys to select) |

Type `/` to trigger autocomplete — fuzzy matching filters commands as you type. Tab accepts, Up/Down navigates, Escape dismisses.

---

## Flow Log

Brix automatically records the complete data flow for every conversation turn, stored in `log/data/brix.jsonl` (JSONL format).

### Viewing Logs

Type `/log` to open an interactive log viewer. Use arrow keys to navigate, Enter to view details:

```
you> /log
Select a log entry (arrow keys + Enter):
> #1  2026-05-07T15:36:12 [a3f8b21c]  12500ms OK  "What's the weather in Shanghai?"
  #2  2026-05-07T15:35:05 [49621c65]  7644ms  OK  "你好"
```

After selecting an entry, detailed info is displayed:

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

```typescript
import { HookRegistry } from '../hooks/registry.js'

const hooks = new HookRegistry()
hooks.bindLog(log)  // FlowLog receives all events

// Register a custom hook for specific events
hooks.register('tool_exec', (e) => console.log(`Tool called: ${e.data['name']}`))
hooks.register('intent', (e) => auditLog(e))
```

### Available Events

| Event | Trigger Location | Data Fields |
|-------|-----------------|-------------|
| `memory` | cli/app.ts | `msgs`, `window`, `chars` |
| `intent` | router/intent.ts | `result`, `via`, `model`, `ms` |
| `complexity` | cli/app.ts | `result` |
| `router` | cli/app.ts | `model`, `reason` |
| `orch_plan` | orchestrator/ | `iter`, `tools`, `ms`, `response` |
| `tool_exec` | orchestrator/ | `name`, `args`, `result`, `ms` |
| `persist` | cli/app.ts | `saved` |

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

Brix has a state machine orchestrator that controls how the agent processes requests:

| Engine | Description | Best For |
|--------|-------------|----------|
| `state_machine` | TypeScript state machine. No extra dependencies. | Default, lightweight, fast |

### How to Switch

Edit `config/settings.yaml`, change the `engine` field:

```yaml
engine: "state_machine"   # TypeScript (default)
```

Save the file — the change takes effect on next launch.

---

## Architecture

```
+-----------------------------------------------------+
|                      CLI Layer                       |
|              src/cli/app.ts (REPL)                   |
+-----------------------------------------------------+
|                   Router Layer                       |
|  src/router/intent.ts  src/router/complexity.ts      |
|  src/router/model-router.ts                          |
+-----------------------------------------------------+
|                Orchestrator Layer                     |
|  src/orchestrator/state-machine.ts (TypeScript)      |
+-----------------------------------------------------+
|                  Capability Layer                     |
|  src/capability/runner.ts (ToolRunner)               |
|  src/capability/basics/ (reusable agent features)    |
|    sessions.ts, memory-files.ts, logs.ts, commands.ts|
|  src/capability/tools/calculator.ts                  |
|  src/capability/tools/weather.ts                     |
|  src/capability/tools/file-read.ts                   |
|  src/capability/tools/file-write.ts                  |
|  src/capability/tools/file-edit.ts                   |
+-----------------------------------------------------+
|                   Infra Layer                        |
|  src/infra/llm-client.ts (Unified LLM Client)       |
|  src/infra/providers/openai-compat.ts                |
|  src/infra/providers/anthropic-compat.ts             |
+-----------------------------------------------------+
|                   Config Layer                       |
|  src/config/loader.ts  src/config/model-registry.ts  |
|  config/settings.yaml                                |
+-----------------------------------------------------+
|                   Memory Layer                       |
|  src/memory/types.ts (MemoryProvider interface)      |
|  src/memory/provider.ts (BrixMemoryProvider)         |
|  src/memory/session.ts (Session CRUD + locking)      |
|  src/memory/soul.ts (Agent personality)              |
|  src/memory/user.ts (User profile)                   |
|  src/memory/storage.ts (Atomic JSON)                 |
|  src/memory/strategy.ts (Context Window)             |
+-----------------------------------------------------+
|                    Log Layer                          |
|  src/log/flow.ts (FlowLog Collector)                 |
|  src/log/writer.ts (JSONL File I/O)                  |
+-----------------------------------------------------+
|                   Hook Layer                          |
|  src/hooks/registry.ts (HookRegistry + HookEvent)    |
|  Core modules fire events → FlowLog auto-receives    |
+-----------------------------------------------------+
|                 Terminal UI Layer                     |
|  src/cli/stream-renderer.ts (Markdown stream)        |
|  src/cli/spinner.ts (Braille animation)              |
|  src/cli/stage-indicator.ts (loading spinner)        |
|  src/cli/tool-display.ts (tool execution panels)     |
|  src/cli/completer.ts (slash command autocomplete)   |
|  src/cli/paginated-selector.ts (generic TUI selector)|
|  src/cli/display.ts (history rendering)              |
|  src/cli/theme.ts (chalk theme)                      |
|  src/cli/banner.ts (startup banner)                  |
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
+-- src/
|   +-- entrypoints/
|   |   +-- cli.ts                   # Entry point (REPL startup)
|   +-- types.ts                     # Shared TypeScript types
|   +-- config/
|   |   +-- loader.ts                # YAML config loader
|   |   +-- model-registry.ts        # Model lookup by id/purpose
|   +-- infra/
|   |   +-- llm-client.ts            # Unified LLM client
|   |   +-- providers/
|   |       +-- openai-compat.ts     # OpenAI-compatible adapter
|   |       +-- anthropic-compat.ts  # Anthropic-compatible adapter
|   +-- router/
|   |   +-- intent.ts                # Intent classification
|   |   +-- complexity.ts            # Complexity evaluation
|   |   +-- model-router.ts          # Model selection logic
|   +-- orchestrator/
|   |   +-- engine.ts                # OrchestratorEngine interface
|   |   +-- states.ts                # State enum
|   |   +-- state-machine.ts         # TypeScript state machine
|   +-- capability/
|   |   +-- runner.ts                # ToolRunner registry
|   |   +-- basics/                  # Reusable agent features (UI-independent)
|   |   |   +-- sessions.ts          # Session list, resume, prefix match
|   |   |   +-- memory-files.ts      # Soul & user file loaders
|   |   |   +-- logs.ts              # Log retrieval & formatting
|   |   |   +-- commands.ts          # Command registry for /help & autocomplete
|   |   +-- tools/
|   |       +-- calculator.ts        # Math expression evaluator
|   |       +-- weather.ts           # Mock weather lookup
|   |       +-- file-read.ts         # Local file reader
|   |       +-- file-write.ts        # File writer (memory/data/ sandboxed)
|   |       +-- file-edit.ts         # File editor (memory/data/ sandboxed)
|   +-- memory/
|   |   +-- types.ts                 # MemoryProvider interface
|   |   +-- provider.ts              # BrixMemoryProvider implementation
|   |   +-- session.ts               # Session manager (UUID, locking)
|   |   +-- soul.ts                  # Agent personality (soul.md)
|   |   +-- user.ts                  # User profile (user.md)
|   |   +-- storage.ts               # Atomic JSON persistence
|   |   +-- strategy.ts              # Context window management
|   |   +-- data/                    # Runtime data (gitignored)
|   +-- log/
|   |   +-- flow.ts                  # FlowLog step collector
|   |   +-- writer.ts                # JSONL file I/O
|   +-- hooks/
|   |   +-- registry.ts              # HookRegistry + HookEvent
|   +-- cli/
|       +-- app.ts                   # REPL interface (streaming pipeline)
|       +-- completer.ts             # Slash command autocomplete
|       +-- paginated-selector.ts    # Generic paginated TUI selector
|       +-- display.ts               # Output formatting & history rendering
|       +-- stream-renderer.ts       # Safe-boundary Markdown stream renderer
|       +-- spinner.ts               # Braille dot animation spinner
|       +-- stage-indicator.ts       # Unified loading spinner (update in-place)
|       +-- tool-display.ts          # Tool execution status panels
|       +-- theme.ts                 # chalk theme (markdown, tool, spinner styles)
|       +-- banner.ts                # Startup ASCII banner
+-- tests/
|   +-- cli-entrypoint.test.ts       # CLI entrypoint tests
|   +-- router.test.ts               # Router tests
|   +-- orchestrator.test.ts         # Orchestrator tests
|   +-- capability.test.ts           # Tool & runner tests
|   +-- infra.test.ts                # Infra layer tests
|   +-- memory.test.ts               # Memory tests
|   +-- config.test.ts               # Config tests
+-- config/
|   +-- settings.yaml                # Provider & model configuration
+-- package.json                     # Project config & dependencies
+-- tsconfig.json                    # TypeScript configuration
```

---

## Testing

```bash
# Run all tests
bun test

# Run with type checking
bun run typecheck

# Run specific test file
bun test tests/router.test.ts
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | TypeScript (strict mode) |
| Runtime | Bun 1.3+ |
| REPL | readline (Node built-in) |
| Terminal UI | chalk + custom components |
| Config | js-yaml |
| LLM (OpenAI) | openai SDK |
| LLM (Anthropic) | @anthropic-ai/sdk |
| Env Loading | dotenv |
| Testing | bun:test |

---

## License

Private project.
