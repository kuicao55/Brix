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


def _strip_control_chars(text: str) -> str:
    """剥离 ANSI 转义序列和控制字符，仅保留可打印内容。"""
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _RESIDUAL_ESC_RE.sub("", text)
    text = _CONTROL_CHAR_RE.sub("", text)
    return text
