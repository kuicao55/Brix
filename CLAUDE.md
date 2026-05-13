# Brix 开发约束

## 模块化（最高优先级）

所有层通过 Protocol 接口通信，禁止跨层直接 import 内部模块。

- `cli/` → 依赖各层的 Protocol，不 import 内部实现
- `orchestrator/` → 通过 `OrchestratorEngine` Protocol
- `memory/` → 通过 `MemoryProvider` Protocol
- `capability/` → 通过 `Tool` 基类 + `ToolRunner`
- `router/` → 通过函数调用（classify_intent, select_model）
- `infra/` → 通过 `LLMClient` 统一接口

替换任何一层只需满足同一 Protocol，不改动调用方。

## 数据与逻辑分离

运行时数据放 `data/` 子目录（如 `memory/data/`），`.py` 是逻辑层，`.md`/`.json` 是数据层。`data/` 加入 `.gitignore`。

## 需求对齐（强制）

1. **逐项确认**：用户说明需求后，必须复述你的理解（即使第一次就完全理解），等用户确认后才能继续。
2. **穷追不舍地提问**：对任何模糊、矛盾或不完整的地方反复追问，直到双方达成一致。每次只问一个问题，并给出你的推荐答案。如果某个问题可以通过探索代码库来回答，先自己去探索代码库，而不是来问用户。
3. **写码前请示**：在开始编写任何代码之前，必须先向用户说明你打算怎么做并获得明确许可，才能动手执行。

## 代码风格

- 中文注释和文档
- Python 3.11+ 类型语法
- 异步优先，fail gracefully
