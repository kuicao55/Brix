# SkillTool 修复计划 — 让 LLM 能主动调用 Skill

## 问题

当前 Brix 的 Skill 系统只支持用户手动输入 `/name` 调用，LLM 无法通过 function calling 主动调用 Skill。这导致用户说"帮我搜一下 xxx"时，LLM 不知道怎么调用 web-search skill，只能调无关的 tool。

## 参考：Claude Code 的做法

1. 注册一个 `Skill` tool，schema: `{ skill: string, args?: string }`
2. Skill 列表通过 system-reminder 注入对话，格式：`- name: description (whenToUse)`
3. System prompt 告诉 LLM：`Use the Skill tool to execute them`
4. LLM 决定调用 → Skill tool 执行 → 加载 SKILL.md → prompt 注入 → 返回结果

## 改动范围

### 1. 新建 `capability/tools/skill_tool.py`

```python
class SkillTool(Tool):
    name = "Skill"
    description = "Execute a skill. Use when a matching skill exists for the user's request."

    input_schema = {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "The skill name, e.g. 'commit', 'web-search-gemini'"
            },
            "args": {
                "type": "string",
                "description": "Optional arguments for the skill",
                "default": ""
            }
        },
        "required": ["skill"]
    }

    def __init__(self, command_registry: CommandRegistry):
        self._registry = command_registry

    async def execute(self, skill: str, args: str = "") -> str:
        # 1. 从 registry 查找 skill command
        # 2. 创建 CommandContext
        # 3. 执行 skill.execute(args, context)
        # 4. 返回 prompt_text（让 LLM 继续处理）
```

关键逻辑：
- 查找 skill → 执行 → 返回 `CommandResult.prompt_text`
- 如果 skill 有 `allowed_tools` / `model` 覆盖，需要注入到上下文
- 错误处理：skill 不存在时返回友好错误信息

### 2. 修改 `cli/app.py`

在 `_register_commands()` 之后注册 SkillTool：

```python
from capability.tools.skill_tool import SkillTool
self._tool_runner.register(SkillTool(self._command_registry))
```

### 3. 修改 system prompt 中的 skill listing 格式

当前格式（`cli/app.py` 中 `get_skill_listing_text()`）：
```
可用的 Skills:
- /commit: 提交代码变更 (当用户要求提交代码时)
```

改为（加上 Skill tool 调用提示）：
```
The following skills are available for use with the Skill tool:
- commit: 提交代码变更 (当用户要求提交代码时)

Use the Skill tool to execute them when the user's request matches a skill.
When users reference a "/<name>" command, invoke the Skill tool with that name.
```

### 4. 测试

- `tests/test_skill_tool.py` — SkillTool 单元测试
  - 正常调用：skill 存在 → 返回 prompt_text
  - 错误处理：skill 不存在 → 返回错误信息
  - 参数传递：args 正确传递到 skill
  - allowed_tools/model 传递

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `capability/tools/skill_tool.py` | 新建 | SkillTool 实现 |
| `cli/app.py` | 修改 | 注册 SkillTool + 更新 skill listing 格式 |
| `tests/test_skill_tool.py` | 新建 | SkillTool 测试 |

## 执行顺序

1. 写测试（RED）
2. 实现 SkillTool（GREEN）
3. 注册到 CLI
4. 更新 skill listing 格式
5. 全量测试验证
