"""灵魂文件管理器 — 负责 soul.md 的读写。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# 固定部分和成长部分的标题常量
_FIXED_HEADER = "# Soul — 固定部分"
_GROWTH_HEADER = "# Soul — 成长部分"


class SoulManager:
    """管理 memory/data/soul.md 文件。"""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "soul.md"

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

        - 有成长标题：返回成长标题之前的内容
        - 仅有固定标题：返回全部内容
        - 无固定标题（旧格式）：返回空字符串
        """
        content = self.load()
        if not content:
            return ""
        growth_idx = content.find(_GROWTH_HEADER)
        if growth_idx != -1:
            fixed = content[:growth_idx]
            return fixed.rstrip("\n")
        # 无成长标题 — 检查是否有固定标题
        if _FIXED_HEADER in content:
            return content.rstrip("\n")
        # 旧格式（无标题头）
        return ""

    def load_growth(self) -> str:
        """提取成长部分内容（`# Soul — 成长部分` 到文件末尾）。

        - 有成长标题：返回成长标题之后的内容
        - 无成长标题：返回空字符串
        """
        content = self.load()
        if not content:
            return ""
        growth_idx = content.find(_GROWTH_HEADER)
        if growth_idx == -1:
            return ""
        growth = content[growth_idx + len(_GROWTH_HEADER):]
        return growth.lstrip("\n")

    def save_growth(self, growth_content: str) -> None:
        """只更新成长部分，保留固定部分不变。

        - 若 soul.md 不存在，直接写入成长内容
        - 若 soul.md 有成长部分，替换成长部分
        - 若 soul.md 无成长部分，追加成长内容
        """
        if not self._path.exists():
            self.save(growth_content)
            return

        content = self.load()
        growth_idx = content.find(_GROWTH_HEADER)
        if growth_idx != -1:
            # 替换成长部分：保留固定部分 + 新成长内容
            fixed_part = content[:growth_idx]
            new_content = fixed_part + growth_content
        else:
            # 追加成长部分
            if content and not content.endswith("\n"):
                content += "\n"
            new_content = content + "\n" + growth_content
        self.save(new_content)

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
