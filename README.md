# Brix

> **[中文文档](README_zh.md)**

A modular, multi-provider AI agent with a state machine orchestrator, tool calling, and persistent memory.

## Features

- **Multi-Provider LLM** — Unified interface for OpenAI-compatible and Anthropic-compatible APIs
- **Dual Orchestrator** — Pure Python state machine + LangGraph engine, switchable via config
- **Streaming Output** — Real-time token-by-token rendering with safe-boundary Markdown detection
- **Tool Calling** — Built-in tools: calculator, weather, file reader, file writer, file editor
- **Memory System v2** — Session-isolated conversations, agent personality (soul.md), user profile (user.md), auto-onboarding
- **Persistent Storage** — Crash-safe atomic writes with fcntl locking
- **Side Layer** — Background task system with 7 async tasks: session title generation, tool result summarization, user preference detection, history search, voice cleanup, context compression, session summary
- **Rich Terminal UI** — Thinking spinner during LLM gap, tool execution panels, content indentation with compact paragraph spacing, styled banner, custom theme, inline response markers
- **Slash Autocomplete** — Type `/` to see command suggestions with fuzzy matching; Tab to accept, Up/Down to navigate
- **Voice Interaction** — STT + TTS with independent control, pluggable Protocol architecture
  - STT: Local faster-whisper / Online Qwen-ASR Realtime (switchable via config)
  - TTS: CosyVoice v3 Flash, streaming synthesis + multi-level playback fallback (PyAudio / afplay / system TTS)
  - Continuous conversation, echo cancellation, real-time transcription display
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

# 阿里云 DashScope
ALI_API_KEY=your-ali-key-here

# DeepSeek official API
DEEPSEEK_API_KEY=your-deepseek-key-here
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
| `/help` | List all available commands |
| `/quit` | Save session and exit (also `/exit`) |
| `/clear` | Clear current session and start fresh |
| `/resume` | Browse and resume previous sessions (interactive TUI with pagination) |
| `/history` | Show current session messages |
| `/soul` | Show agent personality (soul.md) |
| `/user` | Show user profile (user.md) |
| `/model` | View or switch main model (interactive arrow-key selector, or `/model <id>` direct switch) |
| `/log` | Interactive log viewer (arrow keys to select) |
| `/voice` | Toggle voice mode (supports `--input-only`, `--output-only`, `--continuous`) |

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
| `orch_plan` | LLM generates response or decides tool calls, records full prompt |
| `tool_exec` | Execute tools and record input/output |
| `persist` | Save conversation to storage |

---

## Hook System

Brix uses an event-driven architecture via `HookRegistry`. Core modules (orchestrator, CLI, side tasks) fire events through `hooks.fire()` instead of calling `FlowLog` directly. FlowLog acts as the default listener, automatically receiving all events.

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
    base_url: "https://api.deepseek.com"  # API endpoint
    api_key_env: "DEEPSEEK_API_KEY"     # Env var name for the API key
    protocol: "openai"                  # "anthropic" or "openai"
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
| `deepseek/deepseek-v4-pro` | deepseek | deepseek-v4-pro |
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

## Voice Interaction

Brix supports voice input (STT) and voice output (TTS), independently controllable.

### Usage

```bash
# Toggle voice mode in REPL
/voice

# STT only (no TTS playback)
/voice --input-only

# TTS only (no microphone)
/voice --output-only

# Continuous conversation (auto-resume after TTS)
/voice --continuous
```

### Configuration

```yaml
voice:
  enabled: true
  input_enabled: true
  output_enabled: true

  # STT — local or online
  stt_provider: "online"  # local = faster-whisper / online = Qwen-ASR Realtime

  # Local STT (faster-whisper)
  stt_model: "small"
  stt_language: "zh"

  # Online STT (Qwen-ASR Realtime via WebSocket, no SDK required)
  stt_online_model: "qwen3-asr-flash-realtime"
  stt_online_api_key_env: "ALI_API_KEY"

  # TTS — CosyVoice v3 Flash
  tts_model: "cosyvoice-v3-flash"
  tts_voice: "loongeric_v3"
  tts_api_key_env: "ALI_API_KEY"
  tts_cooldown_ms: 800
```

### Install Voice Dependencies

```bash
pip install -e ".[voice]"
```

### Architecture

Voice module interacts with CLI via `VoiceRuntime` Protocol, fully pluggable:

- **STT Pipeline**: Microphone → VAD → STT (local/online) → LLM Cleanup → text callback
- **TTS Pipeline**: LLM response → text cleanup → CosyVoice synthesis → audio playback
- **Echo Cancellation**: VAD paused during TTS playback, resumes after cooldown
- **Fallback**: PyAudio → afplay → macOS system TTS

---

## Side Layer (Background Tasks)

Brix runs 7 background tasks via `SideTaskManager`, powered by a dedicated lightweight model (`side.model` in config). These tasks run as fire-and-forget async coroutines — they don't block the main conversation flow.

### Built-in Tasks

| Task | Trigger | Description |
|------|---------|-------------|
| `session_title` | After first response | Auto-generate session title from conversation |
| `tool_summary` | After tool execution | Summarize tool results for context compression |
| `pref_detection` | Every N user messages | Detect and persist user preferences |
| `history_search` | On user input | Search past conversations for relevant context |
| `voice_cleanup` | Voice input | LLM-based cleanup of STT transcriptions |
| `context_compress` | Message threshold reached | Compress conversation when it gets too long |
| `session_summary` | Idle timeout | Generate session summary after inactivity |

### Configuration

```yaml
side:
  enabled: true
  model: "ali/qwen3.6-flash"           # Dedicated lightweight model

  tasks:
    session_title:
      enabled: true
    tool_summary:
      enabled: true
    pref_detection:
      enabled: true
      interval: 5                       # Check every N user messages
    history_search:
      enabled: true
      top_k: 3
    voice_cleanup:
      enabled: true
    context_compress:
      enabled: true
      message_threshold: 50
    session_summary:
      enabled: true
      idle_threshold_minutes: 5
```

---

```
+-----------------------------------------------------+
|                      CLI Layer                       |
|                  cli/app.py (REPL)                   |
+-----------------------------------------------------+
|                    Side Layer                         |
|  side/manager.py (SideTaskManager)                   |
|  side/tasks/ (7 background tasks)                    |
|    session_title, tool_summary, pref_detection,      |
|    history_search, voice_cleanup,                    |
|    context_compress, session_summary                 |
+-----------------------------------------------------+
|                Orchestrator Layer                     |
|  orchestrator/state_machine.py  (Pure Python)        |
|  orchestrator/langgraph_engine.py (LangGraph)        |
+-----------------------------------------------------+
|                  Capability Layer                     |
|  capability/runner.py (ToolRunner)                   |
|  capability/basics/ (reusable agent features)        |
|    sessions.py, memory_files.py, logs.py, commands.py|
|  capability/tools/calculator.py                      |
|  capability/tools/weather.py                         |
|  capability/tools/file_read.py                       |
|  capability/tools/file_write.py                      |
|  capability/tools/file_edit.py                       |
+-----------------------------------------------------+
|                   Voice Layer                        |
|  capability/voice/protocol.py (VoiceRuntime Protocol)|
|  capability/voice/runtime.py (VoiceRuntimeImpl)      |
|  capability/voice/pipeline/ (SimpleVoicePipeline)    |
|  capability/voice/processors/ (VAD, STT, TTS, etc.)  |
|  capability/voice/transport/ (Microphone, Speaker)   |
|  capability/voice/tts/ (CosyVoice TTS Client)       |
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
|  memory/__init__.py (MemoryProvider Protocol)        |
|  memory/provider.py (BrixMemoryProvider)             |
|  memory/session.py (Session CRUD + locking)          |
|  memory/soul.py (Agent personality)                  |
|  memory/user.py (User profile)                       |
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
|  cli/completer.py (slash command autocomplete)       |
|  cli/paginated_selector.py (generic TUI selector)    |
|  cli/display.py (history rendering)                  |
|  cli/theme.py (Rich theme)                           |
|  cli/banner.py (startup banner)                      |
+-----------------------------------------------------+
```

### Data Flow

```
User Input
    |
    v
Side Layer (fire-and-forget tasks)
    +---> history_search (context retrieval)
    +---> pref_detection (every N turns)
    |
    v
Orchestrator Loop
    |
    +---> LLM Call ---> Tool Calls? ---> Execute Tools ---> Review --+
    |                                                                |
    +----------------------------------------------------------------+
    |
    v
Side Layer (post-response tasks)
    +---> tool_summary (tool result summarization)
    +---> session_title (auto-generate title)
    +---> context_compress (when threshold reached)
    +---> session_summary (on idle)
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
+-- side/
|   +-- manager.py                  # SideTaskManager (background task coordinator)
|   +-- base.py                     # SideTask abstract base class
|   +-- tasks/                      # 7 background tasks
|       +-- session_title.py        # Auto-generate session title
|       +-- tool_summary.py         # Summarize tool results
|       +-- pref_detection.py       # Detect user preferences
|       +-- history_search.py       # Search conversation history
|       +-- voice_cleanup.py        # LLM cleanup for voice input
|       +-- context_compress.py     # Compress long conversations
|       +-- session_summary.py      # Summarize session on idle
+-- orchestrator/
|   +-- engine.py                   # OrchestratorEngine protocol
|   +-- states.py                   # State enum
|   +-- state_machine.py            # Pure Python state machine
|   +-- langgraph_engine.py         # LangGraph-based engine
+-- capability/
|   +-- base.py                     # Tool abstract base class
|   +-- runner.py                   # ToolRunner registry
|   +-- basics/                     # Reusable agent features (UI-independent)
|   |   +-- sessions.py             # Session list, resume, prefix match
|   |   +-- memory_files.py         # Soul & user file loaders
|   |   +-- logs.py                 # Log retrieval & formatting
|   |   +-- commands.py             # Command registry for /help & autocomplete
|   +-- tools/
|       +-- calculator.py           # Math expression evaluator
|       +-- weather.py              # Mock weather lookup
|       +-- file_read.py            # Local file reader
|       +-- file_write.py           # File writer (memory/data/ sandboxed)
|       +-- file_edit.py            # File editor (memory/data/ sandboxed)
|   +-- voice/                      # Voice module
|       +-- protocol.py             # VoiceRuntime Protocol
|       +-- runtime.py              # VoiceRuntimeImpl (lifecycle)
|       +-- config.py               # VoiceConfig dataclass
|       +-- pipeline/               # Voice processing pipeline
|       +-- processors/             # VAD, STT (local + online), TTS, cleanup
|       +-- transport/              # Microphone, speaker
|       +-- tts/                    # CosyVoice TTS client
+-- memory/
|   +-- __init__.py                 # MemoryProvider Protocol + factory
|   +-- provider.py                 # BrixMemoryProvider implementation
|   +-- session.py                  # Session manager (UUID, locking)
|   +-- soul.py                     # Agent personality (soul.md)
|   +-- user.py                     # User profile (user.md)
|   +-- storage.py                  # Atomic JSON persistence
|   +-- strategy.py                 # Context window management
|   +-- data/                       # Runtime data (gitignored)
+-- log/
|   +-- flow.py                     # FlowLog step collector
|   +-- writer.py                   # JSONL file I/O
+-- hooks/
|   +-- registry.py                 # HookRegistry + HookEvent
|   +-- __init__.py                 # Re-exports
+-- cli/
|   +-- app.py                      # REPL interface (streaming pipeline)
|   +-- completer.py                # Slash command autocomplete (prompt_toolkit)
|   +-- paginated_selector.py       # Generic paginated TUI selector
|   +-- display.py                  # Output formatting & history rendering
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
    +-- test_capability.py          # Tool & runner tests
    +-- test_file_tools.py          # File tool tests
    +-- test_memory.py              # Memory tests
    +-- test_memory_v2.py           # Memory v2 protocol & provider tests
    +-- test_basics.py              # capability/basics module tests
    +-- test_cli.py                 # CLI tests
    +-- test_completer.py           # Slash command autocomplete tests
    +-- test_paginated_selector.py  # Paginated TUI selector tests
    +-- test_flow_log.py            # Flow log tests
    +-- test_stream_renderer.py     # Stream renderer tests
    +-- test_tool_display.py        # Tool display panel tests
    +-- side/                       # Side layer tests
        +-- test_manager.py         # SideTaskManager tests
        +-- test_tasks.py           # Individual task tests
        +-- test_side_cli_integration.py  # CLI integration tests
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
| Speech-to-Text | faster-whisper (local) / Qwen-ASR Realtime (online, WebSocket) |
| Text-to-Speech | CosyVoice v3 Flash (DashScope WebSocket) |
| Voice Activity Detection | Silero VAD |
| Audio I/O | PyAudio |
| Env Loading | python-dotenv |
| Testing | pytest + pytest-asyncio |

---

## License

Private project.
