"""Side tasks 共享工具函数。"""
from __future__ import annotations

import re

# --- 控制字符清理 ---

# 匹配 ANSI/CSI 转义序列：ESC[ ... 任意中间字符 ... 终止字母
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# 匹配残留 ESC 字符（孤立 ESC 或非 CSI 形式）
_RESIDUAL_ESC_RE = re.compile(r"\x1b.")
# 匹配 C0 控制字符（0x00-0x1F），保留 \t(0x09)、\n(0x0A)、\r(0x0D)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

_MAX_ERROR_LEN = 120


def _strip_control_chars(text: str) -> str:
    """剥离 ANSI 转义序列和控制字符，仅保留可打印内容。"""
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _RESIDUAL_ESC_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    return text


def _short_error(e: BaseException, max_len: int = _MAX_ERROR_LEN) -> str:
    """截断异常信息到单行，避免 logger 输出撑爆终端。"""
    text = str(e).split("\n")[0].strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"
