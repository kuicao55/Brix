"""长期记忆管理。"""
from __future__ import annotations

import fcntl
import logging
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# topic_file 白名单：仅允许字母、数字、下划线、短横线、点号
_SAFE_TOPIC_RE = re.compile(r"^[A-Za-z0-9_\-\.]+$")

# 按大分类存储的固定文件列表
CATEGORY_FILES: set[str] = {"user.md", "knowledge.md", "work.md", "history.md"}


class LongTermMemory:
    """管理长期记忆文件和 MEMORY.md 索引。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = (data_dir / "long-term").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "MEMORY.md"

    @contextmanager
    def _file_lock(self, path: Path, exclusive: bool = True):
        """跨进程文件锁：围绕 load+modify+save 的原子操作。"""
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.touch(exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

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

    def write_topic(self, topic_file: str, content: str, frontmatter: dict[str, str], append: bool = False) -> None:
        """原子写入主题文件，包含 frontmatter。

        Args:
            append: True 时追加内容（带去重），False 时覆盖写入。
        """
        path = self._topic_path(topic_file)

        if append and path.exists():
            # 追加模式：文件锁保护读-去重-写关键区域
            with self._file_lock(path):
                existing = path.read_text(encoding="utf-8")
                existing_fm = self._parse_frontmatter(existing)
                existing_body = self._extract_body(existing)
                # 去重：行级精确匹配（strip 后），而非子串匹配
                existing_lines = {line.strip() for line in existing_body.splitlines()}
                if content.strip() in existing_lines:
                    return
                # 合并 frontmatter（新的覆盖旧的）
                merged_fm = {**existing_fm, **frontmatter}
                fm_str = "\n".join(f"{k}: {v}" for k, v in merged_fm.items())
                new_body = existing_body.rstrip() + "\n" + content + "\n"
                full = f"---\n{fm_str}\n---\n\n{new_body}"
        else:
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
        """扫描 long-term 目录，重建 MEMORY.md 索引（仅索引 CATEGORY_FILES）。"""
        entries: list[str] = []
        for name in sorted(CATEGORY_FILES):
            p = self._dir / name
            if not p.exists():
                continue
            try:
                text = p.read_text(encoding="utf-8")
                fm = self._parse_frontmatter(text)
                topic_name = fm.get("name", p.stem)
                desc = fm.get("description", "")
                entries.append(f"- [{topic_name}]({name}) — {desc}")
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
    def _find_closing_delimiter(text: str) -> int:
        """查找 frontmatter 的闭合 '---' 定界符（行锚定）。
        返回闭合 '---' 的起始字符索引，未找到返回 -1。
        """
        lines = text.split("\n")
        pos = len(lines[0]) + 1  # 跳过第一行 '---' 及其换行符
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                return pos
            pos += len(line) + 1  # +1 for '\n'
        return -1

    @staticmethod
    def _parse_frontmatter(text: str) -> dict[str, str]:
        """解析 YAML frontmatter（简易实现），行锚定查找闭合定界符。"""
        result: dict[str, str] = {}
        if not text.startswith("---"):
            return result
        end = LongTermMemory._find_closing_delimiter(text)
        if end == -1:
            return result
        for line in text[3:end].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                result[k.strip()] = v.strip()
        return result

    @staticmethod
    def _extract_body(text: str) -> str:
        """提取 frontmatter 之后的 body 内容。无 frontmatter 时返回原文。"""
        if not text.startswith("---"):
            return text
        end = LongTermMemory._find_closing_delimiter(text)
        if end == -1:
            return text
        body = text[end + 3:]
        # 跳过 frontmatter 结束后的换行
        if body.startswith("\n"):
            body = body[1:]
        if body.startswith("\n"):
            body = body[1:]
        return body
