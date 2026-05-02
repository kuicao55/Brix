# Brix MVP Design

**Date:** 2026-05-02
**Status:** Draft

## Goal

Build a minimum viable CLI-based personal AI agent with a working Orchestrator Layer, allowing basic multi-turn conversation with tool calling capabilities.

## Architecture

Brix follows a layered architecture with clear separation of concerns. Each layer lives in its own directory and communicates through well-defined interfaces. The MVP focuses on the core conversation loop: CLI → Router → Orchestrator → Capability → LLM → Response.

Two milestones:
- **Milestone 1**: Complete chain with pure Python state machine orchestrator
- **Milestone 2**: Add LangGraph orchestrator as a switchable alternative

## Components

### 1. Config Layer (`config/`)

Responsible for: model registry, provider definitions, routing rules.

**Files:**
- `settings.yaml` — model registry, provider configs, routing defaults
- `loader.py` — loads and validates config from YAML
- `model_registry.py` — provides model lookup by id, purpose, cost_tier

**Design:**
- Each provider is defined with `base_url`, `api_key_env`, and `protocol` (openai/anthropic)
- API keys are loaded from environment variables, never stored in config files
- Custom OpenAI-compatible services (DeepSeek, vLLM, etc.) are supported by setting `protocol: "openai"` with a custom `base_url`

### 2. Infra Layer (`infra/`)

Responsible for: unified LLM calling, provider abstraction, retry/timeout.

**Files:**
- `llm_client.py` — single entry point for all LLM calls
- `providers/openai_compat.py` — OpenAI compatible protocol adapter
- `providers/anthropic_compat.py` — Anthropic compatible protocol adapter

**Design:**
- `LLMClient.chat(messages, model, tools) -> LLMResponse` is the unified interface
- Internally routes to the correct provider adapter based on `protocol` field in config
- `LLMResponse` is a normalized response type containing:
  - `content: str` — text response
  - `tool_calls: list[ToolCall]` — parsed tool call requests (name, arguments)
  - `finish_reason: str` — stop, tool_calls, length, etc.
- Provider adapters handle protocol-specific request/response translation
- Tool definitions are passed in OpenAI function calling format; Anthropic adapter translates as needed

### 3. Router Layer (`router/`)

Responsible for: intent classification, complexity evaluation, model selection.

**Files:**
- `intent.py` — classifies user intent using LLM
- `complexity.py` — evaluates task complexity using rules (no LLM)
- `model_router.py` — selects model based on intent + complexity + config

**Design:**
- Intent Classifier uses a lightweight LLM call with a structured prompt, returns: `chat | task | tool_use`
- Complexity Evaluator uses rule-based heuristics (text length, keywords, question marks), returns: `low | medium | high`
- Model Router consults config routing rules and model registry to select the best model
- Router output is a `RouteDecision` dataclass: `{intent, complexity, model_id, requires_tools}`

### 4. Orchestrator Layer (`orchestrator/`)

Responsible for: task orchestration, state management, tool calling coordination.

**Files:**
- `engine.py` — `OrchestratorEngine` Protocol (switchable interface)
- `state_machine.py` — pure Python state machine implementation
- `states.py` — state enum and transition definitions
- `langgraph_engine.py` — LangGraph implementation (Milestone 2)

**State Machine Design:**

States: `IDLE → CLASSIFYING → PLANNING → EXECUTING → REVIEWING → RESPONDING → IDLE`

```
IDLE          — waiting for user input
CLASSIFYING   — (handled by Router, Orchestrator receives pre-classified input)
PLANNING      — LLM decides: respond directly or call tools
EXECUTING     — run tool calls via Tool Runner
REVIEWING     — check if more steps needed, re-plan if required
RESPONDING    — generate final response to user
```

Transitions:
- `PLANNING → RESPONDING` — if LLM decides no tools needed (simple chat)
- `PLANNING → EXECUTING` — if LLM requests tool calls
- `EXECUTING → REVIEWING` — after tools return results
- `REVIEWING → PLANNING` — if more tool calls needed (re-plan loop, max 5 iterations)
- `REVIEWING → RESPONDING` — if task is complete

**Engine Interface:**

```python
class OrchestratorEngine(Protocol):
    async def run(self, user_input: str, context: OrchestratorContext) -> str: ...
```

`OrchestratorContext` carries: conversation history, memory reference, tool runner reference, LLM client reference, model selection.

**Milestone 2**: `LangGraphOrchestrator` implements the same `OrchestratorEngine` protocol using LangGraph's `StateGraph`. Same states, same logic, different execution engine. Users can switch via config or constructor injection.

### 5. Capability Layer (`capability/`)

Responsible for: tool registration, execution, schema generation.

**Files:**
- `base.py` — `Tool` abstract base class
- `runner.py` — `ToolRunner` registry and executor
- `tools/weather.py` — weather lookup tool (mock implementation for MVP, returns hardcoded data)
- `tools/calculator.py` — math expression evaluator
- `tools/file_read.py` — read local file contents

**Design:**

```python
class Tool(ABC):
    name: str
    description: str
    input_schema: dict  # JSON Schema format
    
    @abstractmethod
    async def execute(self, **params) -> str: ...

class ToolRunner:
    def register(self, tool: Tool): ...
    async def run(self, tool_name: str, params: dict) -> str: ...
    def get_tool_schemas(self) -> list[dict]:  # for LLM tool definitions
```

- Each tool is a standalone class, independently testable
- `ToolRunner` is the single entry point for all tool execution
- Tool schemas are auto-generated from each tool's `input_schema`
- Tool results are always returned as strings (LLM-friendly)

### 6. Memory Layer (`memory/`)

Responsible for: conversation persistence, context window management.

**Files:**
- `storage.py` — JSON file read/write for conversation history
- `strategy.py` — what to save, when to save, context window truncation

**Design:**
- `MemoryStorage` stores messages in `data/memory.json`
- Each message: `{role, content, timestamp}`
- `get_history(limit)` returns recent N messages
- `MemoryStrategy.should_save()` — MVP: save all messages
- `MemoryStrategy.get_context_window()` — truncate history to fit within token budget (simple character-based estimate for MVP)

### 7. CLI Interface (`cli/`)

Responsible for: user input, output display, command handling.

**Files:**
- `app.py` — REPL loop using prompt_toolkit
- `display.py` — output formatting with colors and markdown

**Design:**
- Rich CLI with prompt_toolkit: history (up/down arrows), colors, styled output
- Commands: `/quit`, `/clear`, `/model <name>`, `/history`
- Agent responses displayed with syntax highlighting for code blocks
- Streaming output if provider supports it (nice-to-have for MVP)

## Data Flow

### Simple Chat (no tools)

```
User input
  → CLI receives
  → Router: classify intent (chat), complexity (low), select model (gpt-4.1-mini)
  → Orchestrator: PLANNING state, LLM decides respond directly
  → Orchestrator: RESPONDING state, generate response
  → CLI displays response
  → Memory saves both messages
```

### Tool-Using Task

```
User input: "What's the weather in Tokyo?"
  → CLI receives
  → Router: classify intent (tool_use), complexity (low), select model
  → Orchestrator: PLANNING state, LLM requests weather tool call
  → Orchestrator: EXECUTING state, ToolRunner.run("weather", {city: "Tokyo"})
  → Tool returns result
  → Orchestrator: REVIEWING state, check if more steps needed (no)
  → Orchestrator: RESPONDING state, LLM generates final response with tool result
  → CLI displays response
  → Memory saves all messages including tool interaction
```

### Multi-Step Task

```
User input: "Calculate 15% of 2500 and write the result to result.txt"
  → CLI receives
  → Router: classify intent (task), complexity (medium), select model
  → Orchestrator: PLANNING state, LLM requests calculator tool
  → Orchestrator: EXECUTING, calculator returns 375
  → Orchestrator: REVIEWING, more steps needed → back to PLANNING
  → Orchestrator: PLANNING, LLM requests file_write tool
  → Orchestrator: EXECUTING, file_write saves "375"
  → Orchestrator: REVIEWING, done → RESPONDING
  → CLI displays confirmation
```

## Error Handling

- **LLM API errors**: Retry up to 3 times with exponential backoff. If all retries fail, show error to user and fall back to default model.
- **Tool execution errors**: Catch exceptions in tool.execute(), return error string to LLM as tool result. LLM can then explain the error to user.
- **Max iteration guard**: Orchestrator limits re-plan loops to 5 iterations to prevent infinite loops.
- **Config errors**: Fail fast on startup if config is invalid or required env vars are missing.
- **Memory errors**: If JSON file is corrupted, start with empty history and log warning.

## Testing Strategy

- **Unit tests with pytest**: Each module tested independently
- **Mock LLM calls**: All tests use mocked LLM responses (no real API calls in tests)
- **Test files**: One test file per module (`test_router.py`, `test_orchestrator.py`, etc.)
- **Key test cases**:
  - Router: intent classification, complexity evaluation, model selection
  - Orchestrator: state transitions, tool calling loop, max iteration guard
  - Capability: each tool's execute method, tool runner registration and dispatch
  - Memory: save/load, context window truncation
  - Infra: provider adapter request/response translation

## Out of Scope

- Streaming output (nice-to-have, not required for MVP)
- Multi-agent coordination
- Embedding-based memory retrieval
- Web/Desktop/Mobile interfaces
- User authentication
- Production-grade error recovery
- LangGraph implementation (Milestone 2, separate spec/plan)

## Milestones

### Milestone 1: Core Chain (Pure Python)

Complete working CLI agent with:
- Config loading and model registry
- Multi-provider LLM client (OpenAI + Anthropic compatible)
- Router with intent, complexity, model selection
- State machine orchestrator with tool calling loop
- 3 example tools (weather, calculator, file_read)
- JSON memory storage
- Rich CLI with prompt_toolkit
- pytest unit tests

### Milestone 2: LangGraph Orchestrator

Add LangGraph-based orchestrator:
- Implement `LangGraphOrchestrator` with same `OrchestratorEngine` protocol
- Same states and transitions as state machine version
- Config option to switch between engines
- Tests for LangGraph implementation
