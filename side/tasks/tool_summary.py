"""工具调用结果摘要。"""
from __future__ import annotations

import collections.abc
import json
import logging
import re

from side.base import SideTask, SideTaskContext
from side.tasks._util import _strip_control_chars

logger = logging.getLogger(__name__)

MAX_SUMMARY_LEN = 30

PROMPT = """\
Write a short summary label (under 30 chars) describing what these tool calls accomplished.
Think git-commit-subject, not sentence. Past tense. Drop articles.

Examples:
- Searched in auth/
- Fixed NPE in UserService
- Read config.json"""

# --- Secret redaction ---

# 敏感键名模式：键名归一化后（小写 + 分隔符移除）匹配以下子串即视为敏感
_SENSITIVE_KEY_PATTERN = re.compile(
    r"password|passwd|token|secret|apikey|api_key|privatekey|private_key"
    r"|sshkey|ssh_key|sessionid|session_id|authorization|auth|credential"
    r"|bearer|cookie",
)

# 值中的凭证模式（不使用跨行匹配，避免行间串扰）
# 敏感 HTTP header 名（小写），精确匹配
_SENSITIVE_HEADERS_EXACT = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}

# 敏感 header 名 fallback 模式：header 名归一化后含以下子串即视为敏感
_SENSITIVE_HEADER_KEYWORDS = re.compile(
    r"token|secret|key|auth", re.IGNORECASE
)

_CREDENTIAL_PATTERNS: list[re.Pattern] = [
    # Bearer token（匹配 Bearer 后面的非空白字符）
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    # Authorization header value（匹配到行尾，含 Basic dXNlcj... 等多 token 值）
    re.compile(r"Authorization:\s*[^\r\n]+", re.IGNORECASE),
    # X-Api-Key header value（匹配到行尾）
    re.compile(r"X-Api-Key:\s*[^\r\n]+", re.IGNORECASE),
    # Cookie header value（匹配到行尾）
    re.compile(r"Cookie:\s*[^\r\n]+", re.IGNORECASE),
    # Set-Cookie header value（匹配到行尾）
    re.compile(r"Set-Cookie:\s*[^\r\n]+", re.IGNORECASE),
    # Proxy-Authorization header value（匹配到行尾）
    re.compile(r"Proxy-Authorization:\s*[^\r\n]+", re.IGNORECASE),
    # X-Auth-Token header value（匹配到行尾）
    re.compile(r"X-Auth-Token:\s*[^\r\n]+", re.IGNORECASE),
    # 含 password/token/secret 的 YAML/JSON 键值对（如 "db_password: value"）
    # 值在遇到空白或 URL 分隔符（& ; #）时截断，避免跨参数串扰
    re.compile(r"\w*password\w*[:=]\s*[^\s&;#]+", re.IGNORECASE),
    re.compile(r"\w*token\w*[:=]\s*[^\s&;#]+", re.IGNORECASE),
    re.compile(r"\w*secret\w*[:=]\s*[^\s&;#]+", re.IGNORECASE),
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
    # URL/query 参数形式的凭证（api_key=, access_token=, client_secret=, session_id=）
    re.compile(r"api[_-]?key\s*=\s*[^\s&;#]+", re.IGNORECASE),
    re.compile(r"access[_-]?token\s*=\s*[^\s&;#]+", re.IGNORECASE),
    re.compile(r"client[_-]?secret\s*=\s*[^\s&;#]+", re.IGNORECASE),
    re.compile(r"session[_-]?id\s*=\s*[^\s&;#]+", re.IGNORECASE),
]


def _redact_http_headers(text: str) -> str:
    """识别并红act HTTP header 行中的敏感值。

    精确匹配已知敏感 header 名 + fallback 模式匹配 header 名含
    token/secret/key/auth 的未知 header。
    """
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        if ":" in line:
            name, _, _rest = line.partition(":")
            name_lower = name.strip().lower()
            if (
                name_lower in _SENSITIVE_HEADERS_EXACT
                or _SENSITIVE_HEADER_KEYWORDS.search(name_lower)
            ):
                result.append(f"{name}: {_REDACT_PLACEHOLDER}")
                continue
        result.append(line)
    return "\n".join(result)

_REDACT_PLACEHOLDER = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    """判断键名是否属于敏感字段（模式匹配：归一化后含敏感子串即命中）。

    归一化：casefold + 移除分隔符（_ - 空格），使 db_password / apiToken /
    auth-header 等变体均可匹配。
    """
    normalized = re.sub(r"[\s_-]+", "", key.casefold())
    return bool(_SENSITIVE_KEY_PATTERN.search(normalized))


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
    """序列化并红act tool_result 中的凭证模式。

    - str：直接 header + 值级红act（保留原始换行以匹配 header 行）
    - Mapping / Sequence：先递归红act键值（_redact_object），再 JSON 序列化，
      最后对文本执行 header / 值级红act
    """
    if isinstance(tool_result, str):
        result_str = tool_result[:300]
        result_str = _redact_http_headers(result_str)
        return _redact_value(result_str)
    redacted = _redact_object(tool_result)
    try:
        result_str = json.dumps(redacted, ensure_ascii=False, default=str)[:300]
    except (TypeError, ValueError):
        result_str = repr(redacted)[:300]
    result_str = _redact_http_headers(result_str)
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
