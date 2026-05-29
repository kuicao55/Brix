"""长期记忆管理。"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# topic_file 白名单：仅允许字母、数字、下划线、短横线、点号
_SAFE_TOPIC_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")


class LongTermMemory:
    """管理长期记忆文件和 MEMORY.md 索引。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = (data_dir / "long-term").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "MEMORY.md"

    # 保留文件名，不允许作为 topic 写入
    _RESERVED_FILES = {"MEMORY.md"}

    def _topic_path(self, topic_file: str) -> Path:
        """返回 topic 文件路径，校验 topic_file 防止路径遍历和保留文件覆盖。"""
        if not _SAFE_TOPIC_RE.match(topic_file):
            raise ValueError(f"非法 topic_file: {topic_file!r}")
        if topic_file in self._RESERVED_FILES:
            raise ValueError(f"保留文件不允许操作: {topic_file!r}")
        path = (self._dir / topic_file).resolve()
        if not path.is_relative_to(self._dir):
            raise ValueError(f"路径遍历: {topic_file!r}")
        return path

    def list_topics(self) -> list[dict[str, str]]:
        """从 MEMORY.md 索引读取主题列表。"""
        if not self._index_path.exists():
            return []
        topics: list[dict[str, str]] = []
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^- \[(.+?)\]\((.+?)\) — (.+)$", line.strip())
            if m:
                topics.append({"name": m.group(1), "file": m.group(2), "description": m.group(3)})
        return topics

    def read_topic(self, topic_file: str) -> str:
        """读取主题文件内容，不存在则返回空字符串。"""
        path = self._topic_path(topic_file)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_topic(self, topic_file: str, content: str, frontmatter: dict[str, str]) -> None:
        """原子写入主题文件，包含 frontmatter。"""
        path = self._topic_path(topic_file)
        fm = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
        full = f"---\n{fm}\n---\n\n{content}"
        # 原子写入：先写临时文件，再 replace
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(full)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def update_index(self) -> None:
        """扫描 long-term 目录，重建 MEMORY.md 索引。"""
        entries: list[str] = []
        for p in sorted(self._dir.glob("*.md")):
            if p.name == "MEMORY.md":
                continue
            try:
                text = p.read_text(encoding="utf-8")
                fm = self._parse_frontmatter(text)
                name = fm.get("name", p.stem)
                desc = fm.get("description", "")
                entries.append(f"- [{name}]({p.name}) — {desc}")
            except OSError:
                continue
        # 原子写入索引
        content = "\n".join(entries) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._index_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def remove_topic(self, topic_file: str) -> None:
        """删除主题文件并更新索引。"""
        path = self._topic_path(topic_file)
        if path.exists():
            path.unlink()
        self.update_index()

    @staticmethod
    def _parse_frontmatter(text: str) -> dict[str, str]:
        """解析 YAML frontmatter（简易实现）。"""
        result: dict[str, str] = {}
        if not text.startswith("---"):
            return result
        end = text.find("---", 3)
        if end == -1:
            return result
        for line in text[3:end].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                result[k.strip()] = v.strip()
        return result
