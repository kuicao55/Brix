"""工具调用结果摘要。"""
from __future__ import annotations

import collections.abc
import json
import logging
import re

from side.base import SideTask, SideTaskContext

logger = logging.getLogger(__name__)

MAX_SUMMARY_LEN = 30

PROMPT = """\
Write a short summary label (under 30 chars) describing what these tool calls accomplished.
Think git-commit-subject, not sentence. Past tense. Drop articles.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Read config.json"""

# --- 控制字符清理 ---

# 匹配 ANSI/CSI 转义序列：ESC[ ... 任意中间字符 ... 终止字母
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# 匹配残留 ESC 字符（孤立 ESC 或非 CSI 形式）
_RESIDUAL_ESC_RE = re.compile(r"\x1b.")
# 匹配 C0 控制字符（0x00-0x1F），保留 \t(0x09)、\n(0x0A)、\r(0x0D)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def _strip_control_chars(text: str) -> str:
    """剥离 ANSI 转义序列和控制字符，仅保留可打印内容。"""
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _RESIDUAL_ESC_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    return text


# --- Secret redaction ---

# 顶层敏感键名（不区分大小写匹配）
_SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "api-key",
    "token", "access_token", "refresh_token", "id_token",
    "secret", "client_secret",
    "password", "passwd",
    "authorization", "auth",
    "credential", "credentials",
    "bearer",
    "private_key", "private-key",
    "ssh_key", "ssh-key",
    "cookie", "session_id", "session-id",
})

# 值中的凭证模式（不使用跨行匹配，避免行间串扰）
_CREDENTIAL_PATTERNS: list[re.Pattern] = [
    # Bearer token（匹配 Bearer 后面的非空白字符）
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    # Authorization header value（单行）
    re.compile(r"Authorization:\s*\S+", re.IGNORECASE),
    # X-Api-Key header value（单行）
    re.compile(r"X-Api-Key:\s*\S+", re.IGNORECASE),
    # 含 password/token/secret 的 YAML/JSON 键值对（如 "db_password: value"）
    re.compile(r"\w*password\w*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\w*token\w*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\w*secret\w*[:=]\s*\S+", re.IGNORECASE),
    # AWS 风格
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # JWT（三段 base64url）
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # GitHub personal access token
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    # 常见 sk-/tok_ 前缀 key（至少 4 字符）
    re.compile(r"sk-[A-Za-z0-9_-]{4,}"),
    re.compile(r"tok_[A-Za-z0-9_-]{4,}"),
    # ya29. 风格 Google OAuth token
    re.compile(r"ya29\.[A-Za-z0-9_-]+"),
]

_REDACT_PLACEHOLDER = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    """判断键名是否属于敏感字段。"""
    return key.lower() in _SENSITIVE_KEYS


def _redact_value(value: str) -> str:
    """对字符串值执行模式级红act（替换匹配到的凭证模式）。"""
    result = value
    for pat in _CREDENTIAL_PATTERNS:
        result = pat.sub(_REDACT_PLACEHOLDER, result)
    return result


def _redact_object(obj: object) -> object:
    """递归红act对象中的敏感数据。

    - Mapping（dict / MappingProxyType 等）：键名命中敏感名单时替换整个值为 [REDACTED]；否则递归处理值
    - str：执行模式级红act
    - list/tuple：逐元素递归
    - 其他类型原样返回
    """
    if isinstance(obj, collections.abc.Mapping):
        redacted: dict = {}
        for k, v in obj.items():
            if _is_sensitive_key(str(k)):
                redacted[k] = _REDACT_PLACEHOLDER
            else:
                redacted[k] = _redact_object(v)
        return redacted
    if isinstance(obj, str):
        return _redact_value(obj)
    if isinstance(obj, (list, tuple)):
        return type(obj)(_redact_object(item) for item in obj)
    return obj


def _serialize_tool_input(tool_input: object) -> str:
    """安全序列化 tool_input，不假设其类型。红act 后再截断。"""
    redacted = _redact_object(tool_input)
    try:
        return json.dumps(redacted, ensure_ascii=False, default=str)[:300]
    except (TypeError, ValueError):
        return repr(redacted)[:300]


def _redact_tool_result(tool_result: object) -> str:
    """序列化并红act tool_result 中的凭证模式。"""
    result_str = str(tool_result)[:300]
    return _redact_value(result_str)


def _sanitize_summary(raw: str | None) -> str | None:
    """校验并清理摘要：剥离控制字符、折叠换行、截断长度。"""
    if not isinstance(raw, str):
        return None
    cleaned = _strip_control_chars(raw)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return None
    return cleaned[:MAX_SUMMARY_LEN]


class ToolSummaryTask(SideTask):
    @property
    def name(self) -> str:
        return "tool_summary"

    async def execute(self, ctx: SideTaskContext) -> str | None:
        try:
            task_args = ctx.config.get("_side_task_args", {})
            tool_name = task_args.get("tool_name", "")
            tool_input = task_args.get("tool_input", {})
            tool_result = task_args.get("tool_result", "")
            input_str = _serialize_tool_input(tool_input)
            output_str = _redact_tool_result(tool_result)
            user_prompt = (
                f"Tool: {tool_name}\nInput: {input_str}\n"
                f"Output: {output_str}\n\nLabel:"
            )
            response = await ctx.llm_client.chat(
                messages=[
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                model=ctx.side_model,
            )
            return _sanitize_summary(response.content)
        except Exception:
            logger.warning("ToolSummaryTask 执行失败", exc_info=True)
            return None
