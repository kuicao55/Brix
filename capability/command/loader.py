"""SKILL.md 文件加载器 -- 解析 frontmatter + 变量替换。"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

from capability.command.base import CommandMeta, CommandType


class FileSkill:
    """从 SKILL.md 文件加载的 Skill。"""

    def __init__(self, skill_dir: Path) -> None:
        self._skill_dir = skill_dir
        self._meta, self._prompt_template = self._parse(skill_dir / "SKILL.md")

    @property
    def meta(self) -> CommandMeta:
        return self._meta

    async def get_prompt(self, args: str, context: dict) -> str:
        """生成 Skill 的 prompt 内容，执行变量替换。"""
        prompt = self._prompt_template

        # ${SKILL_DIR} 替换
        prompt = prompt.replace("${SKILL_DIR}", str(self._skill_dir))

        # ${SESSION_ID} 替换
        if "session_id" in context:
            prompt = prompt.replace("${SESSION_ID}", context["session_id"])

        # 参数替换
        prompt = self._substitute_arguments(prompt, args)

        return prompt

    @staticmethod
    def _substitute_arguments(prompt: str, args: str) -> str:
        """替换 $ARGUMENTS 和位置参数。"""
        if not args.strip():
            # 无参数时，移除 $ARGUMENTS 占位符
            prompt = prompt.replace("$ARGUMENTS", "")
            # 移除 $0, $1, ... 占位符
            prompt = re.sub(r"\$\d+", "", prompt)
            return prompt.strip()

        # 解析参数为 token 列表
        try:
            tokens = shlex.split(args)
        except ValueError:
            # shlex 解析失败时按空格分割
            tokens = args.split()

        has_placeholder = False

        # $ARGUMENTS 整体替换
        if "$ARGUMENTS" in prompt:
            prompt = prompt.replace("$ARGUMENTS", args)
            has_placeholder = True

        # $0, $1, ... 位置参数替换
        for i, token in enumerate(tokens):
            placeholder = f"${i}"
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, token)
                has_placeholder = True

        # 若无任何占位符，自动追加
        if not has_placeholder and args.strip():
            prompt = prompt.rstrip() + f"\n\nARGUMENTS: {args}"

        return prompt.strip()

    @staticmethod
    def _parse(path: Path) -> tuple[CommandMeta, str]:
        """解析 SKILL.md 文件。"""
        content = path.read_text(encoding="utf-8")

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1]) or {}
                prompt_body = parts[2].strip()
            else:
                frontmatter = {}
                prompt_body = content
        else:
            frontmatter = {}
            prompt_body = content

        # 解析 allowedTools（兼容 camelCase 和 snake_case）
        allowed_tools = frontmatter.get(
            "allowedTools", frontmatter.get("allowed_tools", [])
        )

        meta = CommandMeta(
            name=frontmatter.get("name", path.parent.name),
            description=frontmatter.get("description", ""),
            type=CommandType.SKILL,
            when_to_use=frontmatter.get(
                "whenToUse", frontmatter.get("when_to_use", "")
            ),
            user_invocable=frontmatter.get(
                "userInvocable", frontmatter.get("user_invocable", True)
            ),
            disable_model_invocation=frontmatter.get(
                "disableModelInvocation",
                frontmatter.get("disable_model_invocation", False),
            ),
            allowed_tools=allowed_tools,
            model=frontmatter.get("model"),
            context=frontmatter.get("context", "inline"),
            skill_root=str(path.parent),
        )

        return meta, prompt_body
