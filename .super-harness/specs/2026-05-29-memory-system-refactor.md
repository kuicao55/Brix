# Brix 记忆系统重构 + Side Task 修复 设计文档

**日期:** 2026-05-29
**状态:** Draft

## Goal

将 Brix 的记忆系统从单一 user.md 升级为三层认知架构（核心记忆 + 长期记忆 + 短期记忆），并修复所有未接入的 side task，使记忆系统可扩展、可插拔。

## Architecture

三层记忆 + Dream 蒸馏架构：

```
信息来源                    记忆层                   注入方式
─────────                  ──────                   ────────
pref_detection ──→ ┌─────────────────┐
web search   ──→  │  短期记忆 (JSON)  │ ──→ Side LLM 总结后注入
task experience──→ └────────┬────────┘
                            │ Dream 蒸馏
                            ▼
                   ┌─────────────────┐
                   │ 长期记忆 (MD文件) │ ──→ 主模型通过搜索工具按需检索
                   │ + MEMORY.md 索引 │
                   └────────┬────────┘
                            │ Dream 严格筛选
                            ▼
                   ┌─────────────────┐
                   │   user.md (核心) │ ──→ 每次会话自动注入 system prompt
                   └─────────────────┘
```

- **核心记忆 (user.md)**：最精简、最核心的用户信息，每次会话自动注入 system prompt
- **长期记忆 (long-term/*.md)**：按主题分类的 Markdown 文件，主模型通过 memory_search 工具按需检索
- **短期记忆 (short-term/*.json)**：碎片化的近期记忆，跨会话保留，由 Side LLM 总结后智能注入
- **Dream 蒸馏**：后台定期整理记忆，短期→长期→核心逐级蒸馏

## Components

### 1. ShortTermMemory (`memory/short_term.py`)

管理短期记忆的读写。

```python
class ShortTermMemory:
    def __init__(self, data_dir: Path): ...
    def add_item(self, session_id: str, content: str, source: str, context: str = "") -> None: ...
    def get_recent(self, limit: int = 50) -> list[dict]: ...
    def get_by_session(self, session_id: str) -> list[dict]: ...
    def remove_items(self, item_ids: list[str]) -> None: ...
    def cleanup_sessions(self, session_ids: list[str]) -> None: ...
```

- 存储位置：`memory/data/short-term/{session-uuid}.json`
- 每个文件结构：`{ session_id, created, updated, items: [{ id, content, source, created, context }] }`
- `source` 字段支持：`"pref_detection"`, `"web_search"`, `"task_experience"`, `"manual"`

### 2. LongTermMemory (`memory/long_term.py`)

管理长期记忆文件和 MEMORY.md 索引。

```python
class LongTermMemory:
    def __init__(self, data_dir: Path): ...
    def list_topics(self) -> list[dict]: ...          # 读取 MEMORY.md 索引
    def read_topic(self, topic_file: str) -> str: ... # 读取主题文件内容
    def write_topic(self, topic_file: str, content: str, frontmatter: dict) -> None: ...
    def update_index(self) -> None: ...               # 重建 MEMORY.md 索引
    def remove_topic(self, topic_file: str) -> None: ...
```

- 存储位置：`memory/data/long-term/`
- MEMORY.md 格式：`- [主题名](file.md) — 一行描述`
- 主题文件格式：YAML frontmatter + Markdown 内容

### 3. MemorySearcher Protocol + MemorySearchTool

```python
class MemorySearcher(Protocol):
    def search(self, query: str, limit: int = 5) -> list[MemoryResult]: ...

@dataclass
class MemoryResult:
    source: str       # "short_term" | "long_term" | "user"
    content: str      # 记忆内容片段
    relevance: float  # 相关性评分 0-1
    topic: str | None # 主题文件名（仅长期记忆）
```

实现：
- `KeywordMemorySearcher`：关键词匹配 + TF-IDF 评分（当前）
- `EmbeddingMemorySearcher`：语义搜索（未来，接口兼容）

`MemorySearchTool` 注册到 ToolRunner，主模型可直接调用：
```python
class MemorySearchTool(Tool):
    name = "memory_search"
    description = "搜索长期记忆，查找与当前话题相关的用户信息"
    # 参数：query (搜索关键词)
    # 内部调用 MemorySearcher.search()
    # 返回相关记忆片段
```

### 4. DreamManager (`memory/dream.py`)

Dream 蒸馏管理器。

```python
class DreamManager:
    def __init__(self, data_dir: Path, short_term: ShortTermMemory,
                 long_term: LongTermMemory, user_manager: UserMemoryManager): ...
    def should_dream(self) -> bool: ...     # 检查双门槛
    def on_session_created(self) -> None: ... # 会话计数递增
    async def run(self, llm_client, model) -> None: ... # 执行蒸馏
```

触发条件（双门槛）：
- 距上次 dream ≥ 24 小时
- 新增会话数 ≥ 5

状态文件：`memory/data/dream/dream-state.json`
```json
{
  "last_dream_at": "ISO时间",
  "sessions_since_dream": 0,
  "total_dreams": 0
}
```

蒸馏流程（4 阶段）：
1. **收集**：读取所有 `short-term/*.json` 中的 items
2. **去重/合并**：用 Side LLM 判断相同主题的 items，合并为一条
3. **分类/蒸馏**：
   - 核心信息（反复出现、用户明确强调）→ 写入 user.md（严格标准，≤50 行）
   - 主题知识（有价值但非核心）→ 写入 `long-term/{topic}.md` + 更新 MEMORY.md
   - 琐碎/过时 → 丢弃
4. **清理**：删除已处理的 short-term 文件，更新 dream-state.json

### 5. 记忆注入集成

每轮对话构建上下文时注入记忆：

```python
# cli/app.py _process_streaming() 中
system_prompt = self._memory.build_system_prompt(dynamic_context=dynamic_ctx)

# 注入短期记忆摘要（Side LLM 总结）
if self._side_manager and self._side_manager.enabled:
    summary = await self._side_manager.run_task(
        "memory_summary",  # 新 side task
        session_messages=context_messages,
        user_input=user_input,
        hooks=hooks,
    )
    if summary:
        context_messages.append({
            "role": "system",
            "content": f"[近期记忆]\n{summary}"
        })
```

### 6. Side Task 修复

| 任务 | 修复内容 |
|------|---------|
| **voice_cleanup** | 删除 `side/tasks/voice_cleanup.py`，从 ALL_TASKS 移除 |
| **LLMCleanupProcessor** | settings.yaml 补 `cleanup_enabled: false`, `cleanup_model: ""`, `cleanup_timeout: 0.8`, `cleanup_min_length: 10` |
| **tool_summary** | 改为显示给用户（通过 hooks 或 console.print），不持久化 |
| **pref_detection** | ① 改进 prompt（去除 soul 内容、结构化对话格式、区分玩笑）② 结果写入 ShortTermMemory |
| **context_compress** | 改为 token 数触发：读模型 max_context 配置，token 数 ≥ max_context × 0.8 时触发 |
| **session_summary** | 追踪 last_active_at，空闲 ≥ 5 分钟回来时触发，结果写入短期记忆 |

**pref_detection prompt 改进要点**：
- 只传最近 10 条 user/assistant 对话（去除 system、tool 消息）
- 去除 soul.md 内容注入
- 对话格式化为清晰的 `用户: xxx\n助手: xxx`
- 更严格的判断标准：区分玩笑和真实表达
- 输出直接调用 `ShortTermMemory.add_item()`

## Data Flow

```
用户消息 → CLI
    │
    ▼
_build_dynamic_context()
    ├── user.md → 自动注入 system prompt
    └── short-term → Side LLM 总结 → 注入 context
    │
    ▼
主模型回复（可调用 memory_search 搜索长期记忆）
    │
    ▼
持久化消息 → save_session()
    │
    ▼
Side tasks:
    ├── session_title → 生成会话标题
    ├── tool_summary → 显示工具执行摘要
    ├── pref_detection → 写入短期记忆
    ├── session_summary → 写入短期记忆
    └── memory_summary → 总结短期记忆注入上下文
    │
    ▼
Dream 检查（满足门槛 → fire_and_forget 蒸馏）
```

## Error Handling

- 所有记忆读写失败：log warning，不影响主流程
- Dream 执行失败：记录失败时间，下次重新触发
- memory_search 无结果：返回空列表，主模型正常回复
- 短期记忆文件损坏：隔离文件（quarantine），初始化为空
- MEMORY.md 索引损坏：从 long-term/*.md 重建索引

## Testing Strategy

- `ShortTermMemory`：单元测试 add/get/remove/cleanup
- `LongTermMemory`：单元测试 read/write/update_index/remove
- `KeywordMemorySearcher`：单元测试关键词匹配和评分
- `MemorySearchTool`：单元测试工具调用和返回格式
- `DreamManager`：单元测试 should_dream 门槛逻辑，mock LLM 测试蒸馏流程
- 集成测试：pref_detection → 短期记忆 → Dream → 长期记忆 → memory_search 完整链路

## Out of Scope

- Embedding 语义搜索（未来迭代，当前只做关键词搜索）
- 会话结束时自动蒸馏（当前只在 Dream 时蒸馏）
- 记忆导入/导出功能
- 记忆可视化 UI
- 多设备记忆同步

## Milestone 分解

### Milestone A: Side Task 修复 + 记忆基础设施
- 删除 voice_cleanup
- LLMCleanupProcessor 可插拔
- tool_summary 改显示
- pref_detection 改进 + 写入短期记忆
- context_compress token 触发
- session_summary 接入
- ShortTermMemory 类实现
- LongTermMemory 类实现

### Milestone B: 搜索工具 + 记忆注入
- KeywordMemorySearcher 实现
- MemorySearchTool 注册到 ToolRunner
- 短期记忆注入集成（memory_summary side task）
- 完整对话流程集成

### Milestone C: Dream 蒸馏
- DreamManager 实现
- 蒸馏 prompt 设计
- Dream 状态管理
- Dream 触发集成到 CLI
