# TUI Upgrade Design Spec

**Date:** 2026-05-07
**Status:** Draft

---

## Problem

1. **User input prompt is ugly** — `"you> "` is a raw string with no styling, visually indistinguishable from plain terminal output.
2. **Pipeline stages are invisible** — During execution, the user only sees "Thinking..." once. The 6 pipeline stages (memory, intent, complexity, router, orch_plan, persist) are logged to JSONL but never shown in the terminal in real-time.

## Goals

1. Beautiful, styled user input prompt that clearly distinguishes user input from agent output.
2. Real-time pipeline stage indicators showing what the agent is doing at each step.

---

## Design

### 1. Styled User Input Prompt

Replace raw `"you> "` with a prompt_toolkit styled prompt:

```
  ❯ _
```

- `❯` in bold cyan (prompt_toolkit style)
- 2-space left indent for visual breathing room
- User types in default terminal color (no extra styling needed — the prompt itself is the visual separator)

**Implementation:** Use `prompt_toolkit` HTML/style formatting:

```python
from prompt_toolkit import HTML
user_input = await session.prompt_async(HTML('<ansicyan><b>  ❯ </b></ansicyan>'))
```

After agent response, print a blank line before the next prompt for spacing.

### 2. Pipeline Stage Indicators

Show each pipeline stage as a compact one-line indicator as it completes. The display appears between user input and agent response.

**Visual flow:**

```
  ❯ 你好

  ⊹ Memory      0.0s
  ⊹ Intent      4.0s
  ⊹ Route       0.0s
  ⠋ Planning    ...
```

Each completed stage prints a one-line summary:
- `⊹` dim gray symbol prefix (completed stages)
- Stage name in dim white
- Elapsed time in dim cyan
- Current (active) stage shows a braille spinner animation

When the orchestrator starts streaming text, the stage indicator stops and the response renders normally.

**Stage descriptions:**

| Stage | Label | Trigger Point |
|-------|-------|---------------|
| memory | Memory | After `get_context_window()` returns |
| intent | Intent | After `classify_intent()` returns |
| complexity | Complexity | After `evaluate_complexity()` returns |
| router | Route | After `select_model()` returns |
| orch_plan | Planning | Spinner shown during orchestrator planning |
| persist | Saved | After `hooks.fire("persist")` |

**Implementation:** New class `StageIndicator` in `cli/stage_indicator.py`:

```python
class StageIndicator:
    """Compact pipeline stage progress display."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._current_spinner: Spinner | None = None

    def stage_done(self, name: str, elapsed: float, detail: str = "") -> None:
        """Print a completed stage line."""
        # e.g. "  ⊹ Intent      4.0s  chat"

    def stage_active(self, name: str) -> Spinner:
        """Start a spinner for the current active stage."""
        # Returns a Spinner that can be updated/finished

    def finish(self) -> None:
        """Stop any active spinner."""
```

**Integration point in `_process_streaming()`:**

```python
# After user input, before pipeline:
indicator = StageIndicator(self._console)

# After memory stage:
t0 = time.time()
context_window = ...
indicator.stage_done("Memory", time.time() - t0)

# After intent stage:
t0 = time.time()
intent = await classify_intent(...)
indicator.stage_done("Intent", time.time() - t0, detail=intent)

# ... same for complexity, router

# Before orchestrator starts:
spinner = indicator.stage_active("Planning")
# ... orchestrator runs, spinner shows animation
# On first text_delta: indicator.finish()
```

### 3. Banner Upgrade (Optional)

Use Rich Console for the banner instead of plain `print()`:

```python
def show_banner(console: Console, model: str, version: str, cwd: str) -> None:
    console.print(BRIX_ASCII, style="bold cyan")
    console.print("  BRIX — Personal AI Agent\n", style="dim")
    # ... use Rich Table for model/version/cwd
```

---

## Files to Modify

| File | Change |
|------|--------|
| `cli/app.py` | Styled prompt, integrate StageIndicator into `_process_streaming()` |
| `cli/stage_indicator.py` | **NEW** — StageIndicator class |
| `cli/spinner.py` | Minor: accept label on construction, no other changes needed |
| `cli/theme.py` | Add `stage.name`, `stage.time`, `stage.detail` styles |
| `cli/banner.py` | (Optional) Use Rich Console |
| `tests/test_stage_indicator.py` | **NEW** — tests for StageIndicator |

## Non-Goals

- Not switching to Textual (full TUI framework) — Rich primitives are sufficient.
- Not adding persistent history (separate feature).
- Not changing the StreamRenderer or ToolDisplay — they work well as-is.

## Visual Example (Complete Flow)

```
 ██████╗ ██████╗ ██╗██╗  ██╗
 ...
  BRIX — Personal AI Agent
  Model: minimax/MiniMax-M2.7   v0.1.0

  ❯ 你好

  ⊹ Memory      0.0s
  ⊹ Intent      4.0s  chat
  ⊹ Route       0.0s  minimax/MiniMax-M2.7
  ⠋ Planning    3.4s

  你好！有什么我可以帮助你的吗？

  ⊹ Saved       0.0s

  ❯ _
```
