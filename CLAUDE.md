# Brix 开发约束

## 模块化（最高优先级）

所有层通过 TypeScript 接口通信，禁止跨层直接 import 内部实现。

- `cli/` → 依赖各层的接口定义，不 import 内部实现
- `orchestrator/` → 通过 `OrchestratorEngine` 接口
- `memory/` → 通过 `MemoryProvider` 接口
- `capability/` → 通过 `Tool` 接口 + `ToolRunner`
- `router/` → 通过函数调用（classifyIntent, selectModel）
- `infra/` → 通过 `LLMClient` 类

替换任何一层只需满足同一接口，不改动调用方。

## 数据与逻辑分离

运行时数据放各模块的 `data/` 子目录（如 `src/memory/data/`、`src/log/data/`），`.ts` 是逻辑层，`.md`/`.json` 是数据层。各 `data/` 目录加入 `.gitignore`。

## 代码风格

- 中文注释和文档
- TypeScript strict 模式
- 异步优先 (async/await)，fail gracefully
- 文件名使用 kebab-case
- 类型定义优先使用 `type` 而非 `interface`（与参考项目一致，但 Protocol 用 `interface`）
