"""SkillTool — 让 LLM 通过 function calling 主动调用 Skill。"""
from __future__ import annotations

from typing import Any

from capability.base import Tool
from capability.command.base import CommandContext, CommandResultType
from capability.command.registry import CommandRegistry

# Orchestrator 通过此前缀识别 skill 指令，注入为 user message
SKILL_PROMPT_PREFIX = "[[SKILL_PROMPT]]"


class SkillTool(Tool):
    """将 CommandRegistry 中的 Skill 暴露为可被 LLM 调用的 Tool。

    返回 SKILL.md 内容（带 SKILL_PROMPT_PREFIX 前缀），orchestrator 会将其
    注入为 user message，让 LLM 在下一轮规划中按指令执行。
    """

    def __init__(
        self,
        *,
        registry: CommandRegistry,
        session_id: str = "",
        data_dir: str = "",
        console: Any = None,
        config: dict | None = None,
        memory: Any = None,
        llm_client: Any = None,
    ) -> None:
        self._registry = registry
        self._session_id = session_id
        self._data_dir = data_dir
        self._console = console
        self._config = config or {}
        self._memory = memory
        self._llm_client = llm_client

    @property
    def name(self) -> str:
        return "Skill"

    @property
    def description(self) -> str:
        return (
            "Execute a skill. Use when a matching skill exists for the user's request."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "The skill name, e.g. 'commit', 'web-search-gemini'",
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments for the skill",
                    "default": "",
                },
            },
            "required": ["skill"],
        }

    async def execute(self, *, skill: str, args: str = "", **kwargs: Any) -> str:
        command = self._registry.get(skill)
        if command is None:
            return f"Error: skill '{skill}' not found. Available: {', '.join(m.name for m in self._registry.list_all())}"

        ctx = CommandContext(
            session_id=self._session_id,
            data_dir=self._data_dir,
            console=self._console,
            config=self._config,
            memory=self._memory,
            llm_client=self._llm_client,
        )
        result = await command.execute(args, ctx)

        if result.type == CommandResultType.PROMPT:
            # 构建工具指引：告知 LLM 应使用哪些工具执行 skill
            allowed = command.meta.allowed_tools or []
            if allowed:
                tool_list = ", ".join(allowed)
                tool_hint = (
                    f"\n\n[Available tools for this skill: {tool_list}. "
                    f"Use these tools to execute the above instructions.]"
                )
            else:
                tool_hint = ""
            # 返回带前缀的 prompt，orchestrator 会注入为 user message
            return SKILL_PROMPT_PREFIX + result.prompt_text + tool_hint

        return f"Skill '{skill}' executed (non-prompt result)."
