# Brix 记忆系统 v3 — 设计文档

**日期:** 2026-06-06
**状态:** Draft

## Goal

将 Brix 的记忆系统从 v2（side 小模型提取偏好 + 按 session/point 存储）升级为 v3（主模型主动写入 + 按日期/分类存储 + 人格演化），使 agent 具备更丰富的自我认知和长期成长能力。

## 动机

当前 v2 系统存在以下问题：
1. **短期记忆按 session UUID 存储**，文件碎片化，跨 session 查询需要遍历所有文件
2. **长期记忆按 topic 分文件**，粒度过细，单次提及的 topic 也会创建独立文件
3. **Side 小模型每 5 轮提取偏好**，上下文有限、判断质量低、间隔导致遗漏
4. **记忆内容格式扁平**，只有 content + source，无法区分偏好/事实/情绪/事件
5. **Dream 只做三分类**（core/topics/discard），不支持人格演化
6. **soul.md 是静态文件**，不会随 agent 经历而成长

## 整体架构

```
信息来源                      短期记忆                     长期记忆
─────────                    ────────                    ────────
主模型 tool call ──→  ┌────────────────────┐
  (preference/fact/   │ short-term/         │
   emotion/task/      │   YYYY-MM-DD.json   │
   reflection)        │                     │
                      │ items: [            │    Dream 蒸馏
Side session summary ──→ │   {type, category,  │ ──────────────→ ┌──────────────────┐
  (event)             │    content, context, │                  │ user.md (核心画像) │
                      │    source, timestamp}│                  │ knowledge.md      │
                      └────────────────────┘                  │ work.md           │
                           │                                   │ history.md        │
                           │ 每次构建 system prompt             │ soul.md (成长部分) │
                           ▼                                   └──────────────────┘
                      <short_term_memory>
                      [时间戳] 记忆内容
                      </short_term_memory>
```

---

## 一、短期记忆存储改造

### 1.1 按日期文件存储

**变更**：`memory/data/short-term/{session_id}.json` → `memory/data/short-term/YYYY-MM-DD.json`

**日期归属规则**：
- 日期取 session 开始日期，不是记忆产生日期
- 跨天 session 的记忆写入 session 开始日期的文件
- Side session summary 也写入 session 开始日期的文件

**文件结构**：
```json
{
  "date": "2026-06-06",
  "items": [
    {
      "id": "uuid",
      "type": "preference",
      "category": "user",
      "content": "在家办公，主要吃中餐",
      "context": "用户纠正助手关于工位的假设",
      "source": "main_model",
      "session_id": "uuid-of-origin-session",
      "created": "2026-06-06T14:30:00+08:00"
    }
  ]
}
```

**设计理由**：
- 文件数量从潜在上百个 session 文件降到 14 个（按 keep_days 配置）
- `get_recent()` 遍历开销大幅降低
- Dream 天然按时间批次处理，日期文件是天然的批次边界

### 1.2 内容格式 — 六种 type

| type | category | 谁写 | 含义 | 例子 |
|------|----------|------|------|------|
| `preference` | user | 主模型 | 用户偏好/习惯 | "在家办公，主要吃中餐" |
| `fact` | user/self | 主模型 | 事实性信息 | "用户是创业者" / "今天是端午节" |
| `emotion` | user/self | 主模型 | 情绪状态 | "用户今天心情不错" |
| `task` | self | 主模型 | 任务/承诺 | "用户说下周要发布新版本" |
| `reflection` | self | 主模型 | 自我反思 | "不应该假设用户的工作环境" |
| `event` | — | Side | session 事件摘要 | "今天聊了 Flutter 布局问题，解决了溢出 bug" |

**可扩展性**：type 和 category 为 string 字段，新增类型只需更新 prompt + Dream 分类规则，不改代码结构。未来可能新增：`correction`（用户纠正）、`decision`（重要决策）、`milestone`（项目里程碑）。

### 1.3 接口

```python
class ShortTermMemory:
    def add_item(self, date: str, session_id: str, type: str, category: str,
                 content: str, source: str, context: str = "") -> None: ...
    def get_recent(self, limit: int = 50) -> list[dict]: ...  # 跨日期文件聚合
    def get_by_date(self, date: str) -> list[dict]: ...       # 按日期查询
    def get_summary(self, limit: int = 10) -> str | None: ... # 格式化摘要注入
    def remove_items(self, item_ids: list[str]) -> None: ...
    def cleanup_old(self, keep_days: int = 14) -> None: ...   # 清理过期文件
```

---

## 二、记忆写入方式改造

### 2.1 主模型 Tool Call 写入（偏好/事实/情绪/任务/反思）

**新增工具**：`save_memory`

```python
class SaveMemoryTool(Tool):
    name = "save_memory"
    description = "将值得长期记住的信息写入短期记忆"
    # 参数：
    #   type: str       — preference / fact / emotion / task / reflection
    #   category: str   — user / self
    #   content: str    — 记忆内容（简洁的一句话描述）
    #   context: str    — 对话中的依据（可选）
```

**设计理由**（对比 Claude Code）：
- Claude Code 的主模型在对话中顺手用 file_edit 写记忆，不需要额外 LLM 调用
- Brix 同样让主模型通过 tool call 写入，没有额外延迟
- 主模型有完整上下文，判断质量远高于 side 小模型看 10 条消息片段

**触发指引**（写入 system prompt）：
```
当你在对话中发现以下信息时，调用 save_memory 工具保存：
- 用户明确表达的偏好、习惯、做事方式
- 用户告知的关于自身的重要事实（身份、职业、生活环境等）
- 用户的情绪状态或对你行为的反馈
- 用户提到的待办事项或承诺
- 你自己犯的错误或值得记住的经验教训

不要每次都保存，只在信息有长期价值时调用。
```

### 2.2 Side Session Summary（事件记录）

**职责分工**：
- 主模型 = 实时观察者，记录偏好/事实/情绪/反思
- Side = 事后记录者，总结 session 级别的事件

**触发时机**（全覆盖）：

| 场景 | 触发方式 |
|------|---------|
| `/clear` | `clear_session()` 前触发 |
| `/quit` | `sys.exit()` 前触发 |
| Ctrl+C | `KeyboardInterrupt` 异常捕获中触发 |
| Context compact | compact 完成后触发 |
| 兜底 | 下次 `create_session()` 时检查上一个 session 是否有 summary，没有则补写 |

**写入内容**：type=`event`，source=`side_summary`，category 留空。

**幂等性**：同一 session 不会写入重复的 event 摘要（检查该 session_id 是否已有 type=event 的 item）。

---

## 三、长期记忆存储改造

### 3.1 按大分类存储

**变更**：`memory/data/long-term/{topic}.md` → 固定分类文件

| 文件 | 定位 | Dream 来源 |
|------|------|-----------|
| `user.md` | 用户核心画像（已有） | `preference` + `fact`(category=user) 中最核心的 |
| `knowledge.md` | 通用知识 | `fact` 中与用户工作无关的知识性内容 |
| `work.md` | 用户工作上下文 | `fact` + `event` 中与用户职业/项目相关的 |
| `history.md` | 经历和事件归档 | `event` 中值得长期保留的 |
| `soul.md` | agent 人格（成长部分） | `emotion` + `reflection` 的累积提炼 |

**设计理由**：
- 按 topic 分文件太细，单次提及的帆船也会创建独立文件
- 大分类减少文件数量，提高可维护性
- 每个分类文件有明确的语义边界

**扩展性**：
- 当某个分类文件膨胀到一定大小（如 200 行），Dream 可以决定拆分
- 代码层面维护一个"已存在的分类文件列表"，Dream 的 LLM 可以创建新分类文件
- 不需要预设所有文件，按需创建

**索引**：`MEMORY.md` 索引所有长期记忆文件：
```
- [用户画像](user.md) — 用户基本信息、偏好、习惯
- [通用知识](knowledge.md) — 跨领域知识积累
- [工作上下文](work.md) — 用户职业、项目、技术栈相关
- [经历档案](history.md) — 重要事件和经历记录
```

---

## 四、Dream 蒸馏升级

### 4.1 分类逻辑改造

**输入**：短期记忆的 6 种 type items

**输出路径**：
```
preference + fact(category=user, 核心) → user.md
fact(通用知识)                         → knowledge.md
fact + event(工作相关)                 → work.md
event(非工作经历)                      → history.md
emotion + reflection                   → soul.md 成长部分
task(已过期/已完成)                    → 评估后归档或丢弃
discard                                → 删除
```

**关键判断**：
- `fact` 归属 `knowledge.md` 还是 `work.md`？根据内容是否与用户职业/项目相关
- `event` 归属 `work.md` 还是 `history.md`？同上
- 哪些属于"核心"写入 `user.md`？反复出现、用户明确强调的

### 4.2 人格演化

**输入**：`emotion` + `reflection` 类的短期记忆

**处理逻辑**：
1. 分析是否有性格倾向的变化趋势（不是个别事件，而是趋势）
2. 提炼经验教训（用户明确纠正或 agent 犯了可总结的错误）
3. 更新 soul.md 的成长部分（不覆盖固定部分）

**soul.md 格式改造**：
```markdown
# Soul — 固定部分
（用户定义的人格底线，Dream 不修改）

# Soul — 成长部分
## 性格倾向
（随经历累积变化）

## 经验教训
（从 reflection 中提炼的行为准则）

## 情绪基线
（最近的状态和氛围）
```

**设计理由**：
- 固定部分是用户对 agent 人格的定义，不应被 Dream 修改
- 成长部分是 agent 通过经历自然演化的内容
- 分区明确，避免 Dream 误改用户定义的人格

---

## 五、system prompt 注入

### 5.1 注入内容

每次构建 system prompt 时注入：
- `<soul>` — soul.md 完整内容（固定 + 成长）
- `<user_memory>` — user.md 内容
- `<short_term_memory>` — 最近 10 条短期记忆，带时间戳
- `<dynamic_context>` — platform, working directory（静态，session 内不变）

### 5.2 时间戳格式统一

- 用户消息前缀：`[Weekday YYYY-MM-DD HH:MM TZ] 你好`
- 短期记忆摘要：`[Weekday YYYY-MM-DD HH:MM] 记忆内容`
- 格式一致，方便 agent 对照时间线

---

## 六、数据迁移与清理

- 删除所有现有 `memory/data/short-term/*.json`（按 session UUID 命名的旧文件）
- 删除所有现有 `memory/data/long-term/*.md`（按 topic 命名的旧文件）
- 保留 `memory/data/soul.md` 和 `memory/data/user.md`（格式兼容，内容保留）
- 重建 `MEMORY.md` 索引
- `dream-state.json` 重置（清除旧的 dream 计数）

---

## 七、完整数据流

```
用户消息 → CLI
    │
    ▼
system prompt 构建
    ├── <soul> (soul.md，固定+成长)
    ├── <user_memory> (user.md)
    ├── <short_term_memory> (最近 10 条，含时间戳)
    └── <dynamic_context> (platform, working dir)
    │
    ▼
主模型对话（可调用 save_memory / memory_search）
    ├── save_memory → ShortTermMemory.add_item()
    └── memory_search → KeywordMemorySearcher.search()
    │
    ▼
持久化消息 → save_session()
    │
    ▼
Side tasks:
    ├── session_title → 生成会话标题（fire-and-forget）
    ├── tool_summary → 显示工具执行摘要（fire-and-forget）
    └── dream → 满足门槛时蒸馏（fire-and-forget）
    │
    ▼
Session 结束（/clear, /quit, Ctrl+C, compact, timeout）
    │
    ▼
Side session summary → ShortTermMemory.add_item(type=event)
    │
    ▼
下次 create_session() → 兜底检查上一个 session 是否有 summary
```

---

## Out of Scope

- Embedding 语义搜索（当前只做关键词搜索）
- 多设备记忆同步
- 记忆可视化 UI
- 记忆导入/导出
- Dream 自动拆分过大的分类文件（可在未来迭代）

## Testing Strategy

- ShortTermMemory：日期文件读写、跨日期聚合、过期清理
- SaveMemoryTool：工具注册、参数校验、写入验证
- SessionSummaryTask：各退出路径触发、幂等性、兜底补写
- LongTermMemory：分类文件读写、索引重建
- DreamManager：新的分类逻辑、人格演化写入 soul.md
- 集成测试：完整链路（主模型写入 → 短期记忆 → Dream → 长期记忆 → system prompt 注入）
