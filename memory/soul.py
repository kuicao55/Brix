"""灵魂文件管理器 — 负责 soul.md 的读写。"""
from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

# 固定部分和成长部分的标题常量
_FIXED_HEADER = "# Soul — 固定部分"
_GROWTH_HEADER = "# Soul — 成长部分"


def _find_header_line(lines: list[str], header: str) -> int:
    """在行列表中查找精确匹配 header 的行索引（行锚定匹配）。

    只匹配独立成行的标题，不匹配正文中的子串。
    兼容 CRLF 行尾（rstrip("\\r\\n")）。
    返回行索引，未找到返回 -1。
    """
    for i, line in enumerate(lines):
        if line.rstrip("\r\n") == header:
            return i
    return -1


def _ensure_growth_header(growth_content: str) -> str:
    """确保成长内容以成长标题开头。缺少时自动补齐。"""
    # 去掉前导空行后检查第一行是否为标题
    stripped = growth_content.lstrip("\n")
    if stripped.startswith(_GROWTH_HEADER + "\n") or stripped == _GROWTH_HEADER:
        return growth_content
    # 补齐标题，确保标题后有换行
    if growth_content and not growth_content.startswith("\n"):
        return _GROWTH_HEADER + "\n" + growth_content
    return _GROWTH_HEADER + "\n" + growth_content.lstrip("\n")


class SoulManager:
    """管理 memory/data/soul.md 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "soul.md"
        self._lock_path = data_dir / "soul.md.lock"

    def exists(self) -> bool:
        """判断 soul.md 是否存在且非空。"""
        return self._path.exists() and self._path.stat().st_size > 0

    def load(self) -> str:
        """加载 soul.md 内容，文件不存在时返回空字符串。"""
        if not self._path.exists():
            return ""
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def load_fixed(self) -> str:
        """提取固定部分内容（`# Soul — 固定部分` 到 `# Soul — 成长部分` 之间）。

        使用行锚定解析，只匹配独立成行的标题，防止正文中的标题文本被误匹配。

        - 有成长标题行：返回成长标题行之前的内容
        - 仅有固定标题：返回全部内容
        - 无固定标题（旧格式）：返回空字符串
        """
        content = self.load()
        if not content:
            return ""
        lines = content.split("\n")
        growth_idx = _find_header_line(lines, _GROWTH_HEADER)
        if growth_idx != -1:
            fixed = "\n".join(lines[:growth_idx])
            return fixed.rstrip("\n")
        # 无成长标题行 — 检查是否有固定标题
        if _find_header_line(lines, _FIXED_HEADER) != -1:
            return content.rstrip("\n")
        # 旧格式（无标题头）
        return ""

    def load_growth(self) -> str:
        """提取成长部分内容（`# Soul — 成长部分` 到文件末尾）。

        使用行锚定解析，只匹配独立成行的标题。

        - 有成长标题行：返回成长标题行之后的内容
        - 无成长标题行：返回空字符串
        """
        content = self.load()
        if not content:
            return ""
        lines = content.split("\n")
        growth_idx = _find_header_line(lines, _GROWTH_HEADER)
        if growth_idx == -1:
            return ""
        growth = "\n".join(lines[growth_idx + 1:])
        return growth.lstrip("\n")

    def save_growth(self, growth_content: str) -> None:
        """只更新成长部分，保留固定部分不变。

        - 若 soul.md 不存在，直接写入成长内容（自动补齐 header）
        - 若 soul.md 有成长部分，替换成长部分
        - 若 soul.md 无成长部分，追加成长内容
        - growth_content 缺少成长标题时自动补齐（CQR Finding 3）
        - 全程持有 flock 互斥锁（CQR Finding 1）
        - 使用严格读取，读取失败时 abort 并 re-raise（CQR Finding 2）
        - 空/纯空白 body 时 no-op，防止破坏已有成长（CQR Finding 4）
        """
        # 确保 growth_content 包含成长标题
        growth_content = _ensure_growth_header(growth_content)

        # 剥离标题后，若 body 为空或纯空白则 no-op
        # 防止空内容经过 _ensure_growth_header 后变成纯 header，
        # 从而在替换路径上清空已有成长内容
        body = growth_content[len(_GROWTH_HEADER):]
        if not body.strip():
            return

        # 获取互斥锁，保护读-改-写临界区
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.touch(exist_ok=True)
        fd = os.open(str(self._lock_path), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)

            if not self._path.exists():
                self.save(growth_content)
                return

            # 严格读取：失败时直接 raise，不走 tolerant load() 的 "" 降级
            content = self._path.read_text(encoding="utf-8")
            lines = content.split("\n")
            growth_idx = _find_header_line(lines, _GROWTH_HEADER)
            if growth_idx != -1:
                # 替换成长部分：保留固定部分 + 新成长内容
                fixed_part = "\n".join(lines[:growth_idx])
                new_content = fixed_part + "\n" + growth_content
            else:
                # 追加成长部分
                if content and not content.endswith("\n"):
                    content += "\n"
                new_content = content + "\n" + growth_content
            self.save(new_content)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def save(self, content: str) -> None:
        """原子保存内容到 soul.md：临时文件 + fsync + rename。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".soul-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1  # fd 已由 os.fdopen 接管
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(self._path))
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
