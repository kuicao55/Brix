# Phase 1 — Experience Upgrade Design

**Date:** 2026-05-07
**Status:** Draft

## Goal

Transform Brix from a "functional but bare" CLI agent into a polished daily assistant with streaming output, real-time feedback, accurate context management, and resilient LLM calls.

## Architecture

Phase 1 adds three new dependencies (`rich`, `tiktoken`, `tenacity`) and introduces 8 improvements across 4 independent groups. The streaming core (Group A) is the critical path — it requires changes to the LLM provider layer, orchestrator protocol, and CLI display. Groups B-D are independent and can be built in any order.

### Dependency Graph

```
Group A: Streaming Core ───────────────────────────────┐
  2.1  流式输出 + Markdown渲染  [P0, 2-3天]             │
  11.5 Spinner                  [P0, 1天]               │
  11.4 Markdown主题              [P1, 1天, depends on 2.1]
                                                        │
Group B: LLM Resilience ─────── independent             │
  2.3  LLM重试 (tenacity)       [P0, 1天]               │
                                                        │
Group C: Context Accuracy ───── independent             │
  2.2  Token计数 (tiktoken)     [P0, 1天]               │
                                                        │
Group D: UI Polish ───────────── depends on A           │
  11.6 工具状态面板              [P1, 1-2天, needs Spinner]
  11.7 启动Banner                [P1, 0.5天]            │
  3.3  层级化配置                [P1, 1天]              │
```

### Build Order

1. **B + C** — Quick wins, no dependencies (~2 days)
2. **D.2 + D.3** — Banner + Config, standalone (~1.5 days)
3. **A** — Streaming core, the big piece (~4-5 days)
4. **D.1** — Tool display, depends on Spinner from A (~1-2 days)

### New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `rich` | `>=13.0` | Terminal UI: Markdown, Spinner, Panel, Theme, Live display |
| `tiktoken` | `>=0.7` | Token counting for context window management |
| `tenacity` | `>=8.0` | Retry with exponential backoff for LLM calls |

## Components

### Component 1: LLM Retry (2.3)

**File changes:** `infra/llm_client.py`, `config/settings.yaml`

Add tenacity-based retry decorator to `LLMClient.chat()`. Retry on transient errors (429, 5xx, timeout, connection). After exhausting retries on primary model, fall back to `routing.fallback_model` if configured.

**Retry strategy:**
- Max 3 attempts per model
- Exponential backoff: 1s → 2s → 4s (with jitter, handled by tenacity)
- Retryable exceptions: `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `APIStatusError(5xx)` from both OpenAI and Anthropic SDKs
- After 3 failures on primary model: try fallback model once (if configured)

**Config addition to settings.yaml:**
```yaml
retry:
  max_retries: 3
  base_delay: 1.0
  max_delay: 30.0
```

### Component 2: Token Counting (2.2)

**File changes:** `memory/strategy.py`, `config/settings.yaml`

Replace character-based truncation with tiktoken-based token counting. Use `tiktoken.encoding_for_model("gpt-4")` as universal approximation.

**Key behaviors:**
- Default `max_context_tokens: 8000` (configurable in settings.yaml under `memory` section)
- System messages always preserved (not subject to truncation)
- Graceful fallback: if tiktoken fails, use `len(content) // 4` approximation
- Same reverse-walk accumulation strategy as current implementation

**Config addition:**
```yaml
memory:
  max_context_tokens: 8000
```

### Component 3: Streaming Output + Markdown Rendering (2.1)

**File changes:** `infra/providers/openai_compat.py`, `infra/providers/anthropic_compat.py`, `infra/llm_client.py`, `orchestrator/engine.py`, `orchestrator/state_machine.py`, `orchestrator/langgraph_engine.py`, `cli/app.py`

**New files:** `cli/stream_renderer.py`

Add `chat_stream()` method to each provider and `LLMClient`. Implement `StreamRenderer` with Rich Live display and safe-boundary Markdown rendering. Modify orchestrator to support streaming protocol.

**Streaming protocol (yielded types):**
```python
{"type": "text_delta", "text": "..."}           # streaming text chunk
{"type": "tool_call", "name": "...", "input": {...}}  # tool invocation
{"type": "tool_result", "name": "...", "result": "..."}  # tool result
{"type": "usage", "tokens": 1234}               # token usage info
```

**Provider streaming:**
- OpenAI: `stream=True` on `client.chat.completions.create()`, iterate `async for chunk in response`
- Anthropic: `client.messages.stream()` context manager, iterate text deltas and tool_use blocks

**StreamRenderer design:**
- Rich `Live` display at 15fps
- Safe-boundary detection: wait for complete code fence (`\`\`\``) closure or empty line before rendering
- Buffer incomplete Markdown to prevent broken rendering
- `push_delta(text)` → accumulate → detect boundary → render
- `flush()` → render remaining buffer at stream end

**Orchestrator protocol:**
- `run_stream()` as `AsyncGenerator[dict, None]` on `OrchestratorEngine`
- Both `StateMachineOrchestrator` and `LangGraphOrchestrator` implement it
- Existing `run()` method preserved for backward compatibility

### Component 4: Spinner (11.5)

**New file:** `cli/spinner.py`

Braille dot animation spinner with elapsed time display. Uses Rich Live for smooth updates.

**Lifecycle:**
- `start()` → begin animation in background thread
- `update_label(text)` → change status text
- `finish(label)` → stop, show green checkmark + elapsed time
- `fail(label)` → stop, show red X + elapsed time

**Animation:** 10 Braille frames (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) at 10fps.

**Integration with streaming:**
```
[User input] → Spinner("Thinking...")
→ [LLM first token] → Spinner.stop()
→ StreamRenderer.start() → [text streaming]
→ [tool call] → StreamRenderer.flush() → ToolDisplay
→ [tool done] → StreamRenderer.start() → [more text]
→ [done] → StreamRenderer.flush()
```

### Component 5: Tool Execution Status Panel (11.6)

**New file:** `cli/tool_display.py`

Box-drawn panels showing tool execution details, integrated via the existing Hook system.

**Display modes:**
- **Start**: Panel with tool icon, name, and formatted input detail
  - bash: `$ command` on dark background
  - file_read: `📄 Reading path`
  - file_write: `✏️ Writing path (N lines)`
  - file_edit: Red/green diff preview (first 3 lines)
  - web_search: `🔎 Searching: query`
- **Result**: Single-line summary with status icon, tool name, elapsed time, truncated preview

**Integration:** Register a hook on `"tool_exec"` events:
```python
hooks.register("tool_exec", lambda e: tool_display.show_tool_result(
    e.data["name"], e.data["result"], e.data["ms"]
))
```

### Component 6: Startup Banner (11.7)

**New file:** `cli/banner.py`

ASCII art banner with Brix logo + session info (model, directory, version, help hint).

**Content:**
```
 ██████╗ ██████╗ ██╗██╗  ██╗
 ██╔══██╗██╔══██╗██║╚██╗██╔╝
 ██████╔╝██████╔╝██║ ╚███╔╝
 ██╔══██╗██╔══██╗██║ ██╔██╗
 ██████╔╝██║  ██║██║██╔╝ ██╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝

  Model       minimax/MiniMax-M2.7
  Directory   /Users/kuicao/Applications/Brix
  Version     0.1.0

  Type /help for commands · Ctrl+C to exit
```

### Component 7: Markdown Rendering Theme (11.4)

**New file:** `cli/theme.py`

Custom Rich Theme for Brix terminal output.

**Style definitions:**
```python
BRIX_THEME = Theme({
    "markdown.h1": Style(bold=True, color="cyan"),
    "markdown.h2": Style(bold=True, color="bright_white"),
    "markdown.h3": Style(color="blue"),
    "markdown.code": Style(color="green"),
    "markdown.code_block": Style(bgcolor="grey11"),
    "markdown.link": Style(color="blue", underline=True),
    "markdown.em": Style(italic=True, color="magenta"),
    "markdown.strong": Style(bold=True, color="yellow"),
    "markdown.blockquote": Style(color="grey50"),
    "tool.border": Style(color="grey50"),
    "tool.name": Style(bold=True, color="cyan"),
    "tool.success": Style(color="green"),
    "tool.error": Style(color="red"),
    "spinner.active": Style(color="blue"),
    "spinner.done": Style(color="green"),
    "spinner.failed": Style(color="red"),
})
```

Applied via `Console(theme=BRIX_THEME)` in `BrixCLI.__init__()`.

### Component 8: Hierarchical Config (3.3)

**File changes:** `config/loader.py`

Replace single-file loader with 3-layer merge: global → project → local.

**Layer paths:**
1. `~/.brix/config.yaml` — global defaults
2. `<project>/.brix/settings.yaml` — project config (git-tracked)
3. `<project>/.brix/settings.local.yaml` — local overrides (gitignored)

**Behaviors:**
- Deep merge: nested dicts merged recursively, later layers override earlier
- Missing layers silently skipped
- Backward compatibility: if no `.brix/` directory exists, fall back to `config/settings.yaml` as project layer
- Config validation: check required keys (`providers`, `models`, `routing`)

**gitignore addition:** `.brix/settings.local.yaml`

## Data Flow

### Streaming Request Flow

```
User input
  → BrixCLI._process()
    → HookRegistry.fire("memory")
    → classify_intent() [with spinner]
    → evaluate_complexity()
    → select_model()
    → Spinner.stop()
    → StreamRenderer.start()
    → orchestrator.run_stream(ctx)
      → LLMClient.chat_stream(messages, model, tools)
        → provider.chat_stream(...) [SSE stream]
        → yield {"type": "text_delta", ...}
        → yield {"type": "tool_call", ...}
      → [if tool_call]
        → StreamRenderer.flush()
        → ToolDisplay.show_tool_start()
        → ToolRunner.run(tool_name, params)
        → HookRegistry.fire("tool_exec")
        → ToolDisplay.show_tool_result()
        → [loop back to LLM with tool result]
      → yield {"type": "text_delta", ...}
    → StreamRenderer.flush()
    → MemoryStrategy.save(user_msg, assistant_msg)
    → FlowLog.flush()
```

### Retry Flow

```
LLMClient.chat(messages, model)
  → @tenacity retry decorator
    → provider.chat(...)
    → [on RateLimitError/TimeoutError/ConnectionError]
      → wait exponential(1s, 2s, 4s)
      → retry (up to 3 attempts)
    → [on 3rd failure]
      → try fallback_model via ModelRegistry.get_fallback_model()
      → provider.chat(..., model=fallback_model)
    → [on fallback failure]
      → raise original exception
```

## Error Handling

| Error | Handling |
|-------|----------|
| LLM rate limit (429) | tenacity retry with exponential backoff |
| LLM timeout | tenacity retry, configurable timeout |
| LLM connection error | tenacity retry |
| LLM server error (5xx) | tenacity retry, then fallback model |
| LLM auth error (401/403) | No retry — fail immediately with friendly message |
| Streaming interrupted | StreamRenderer.flush() in finally block |
| tiktoken load failure | Graceful fallback to char/4 approximation |
| Config file malformed | Log warning, use defaults or previous layer |
| Rich terminal not supported | Detect and fall back to plain print() |

## Testing Strategy

### Unit Tests

| Component | Test | Approach |
|-----------|------|----------|
| LLM Retry | Verify retry on transient errors | Mock provider to raise, verify retry count |
| LLM Retry | Verify fallback model | Mock primary fail, verify fallback called |
| Token Count | Verify token-based truncation | Known input → expected output |
| Token Count | Verify system message preservation | System msgs always in result |
| Token Count | Verify graceful fallback | Mock tiktoken failure |
| Config Loader | Verify 3-layer merge | Create temp YAML files, verify merge order |
| Config Loader | Verify backward compat | No .brix/ dir → falls back to config/ |
| Stream Renderer | Verify safe boundary detection | Known Markdown → expected render points |
| Stream Renderer | Verify flush on incomplete stream | Partial stream → flush renders all |
| Spinner | Verify lifecycle | start → finish shows checkmark |
| Tool Display | Verify hook integration | Fire tool_exec event → display called |

### Integration Tests

- Full streaming flow: mock LLM stream → verify output contains expected text
- Retry + fallback: mock primary fail → verify fallback model used
- Config merge: create real YAML files → verify BrixCLI loads correctly

## File Change Summary

| File | Change | Component |
|------|--------|-----------|
| `pyproject.toml` | Add `rich`, `tiktoken`, `tenacity` | All |
| `infra/llm_client.py` | Add `chat_stream()`, tenacity retry decorator | 2.1, 2.3 |
| `infra/providers/openai_compat.py` | Add `chat_stream()` with SSE | 2.1 |
| `infra/providers/anthropic_compat.py` | Add `chat_stream()` with Anthropic streaming | 2.1 |
| `orchestrator/engine.py` | Add `run_stream()` to protocol | 2.1 |
| `orchestrator/state_machine.py` | Implement `run_stream()` | 2.1 |
| `orchestrator/langgraph_engine.py` | Implement `run_stream()` | 2.1 |
| `memory/strategy.py` | Replace char counting with tiktoken | 2.2 |
| `config/loader.py` | 3-layer merge with deep merge | 3.3 |
| `config/settings.yaml` | Add `retry` and `memory` sections | 2.2, 2.3 |
| `cli/app.py` | Integrate Rich, Spinner, StreamRenderer, Banner, config | All |
| `cli/display.py` | Remove passthrough, delegate to Rich modules | 2.1 |
| `cli/stream_renderer.py` | **New**: Safe-boundary Markdown stream renderer | 2.1 |
| `cli/spinner.py` | **New**: Braille animation spinner | 11.5 |
| `cli/tool_display.py` | **New**: Tool execution status panels | 11.6 |
| `cli/banner.py` | **New**: ASCII art startup banner | 11.7 |
| `cli/theme.py` | **New**: Brix Rich theme | 11.4 |

## Out of Scope

- **Auto-compaction / summarization** — Phase 3 item, not Phase 1
- **Tool concurrency** — Phase 3 item
- **Permission system** — Phase 3 item
- **Error display panels** — Phase 2/3 item (basic error handling in scope)
- **Status report formatting** — Phase 2 item
- **Skill system** — Phase 2 item
- **MCP support** — Phase 4 item
- **Web UI** — Phase 4 item
- **Connection pooling** — Future optimization, not Phase 1
- **Config hot-reload** — Not needed for Phase 1
