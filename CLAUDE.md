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

## 代码风格

- 中文注释和文档
- Python 3.11+ 类型语法
- 异步优先，fail gracefully
