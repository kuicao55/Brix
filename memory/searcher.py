"""记忆搜索。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """搜索结果条目。"""

    source: str       # "short_term" | "long_term"
    content: str
    relevance: float
    topic: str | None = None


class MemorySearcher(Protocol):
    """记忆搜索器接口。"""

    def search(self, query: str, limit: int = 5) -> list[MemoryResult]: ...


class KeywordMemorySearcher:
    """关键词匹配搜索。"""

    def __init__(self, long_term: Any, short_term: Any | None) -> None:
        self._long_term = long_term
        self._short_term = short_term

    def search(self, query: str, limit: int = 5) -> list[MemoryResult]:
        """搜索长期和短期记忆，返回按相关度排序的结果。"""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        results: list[MemoryResult] = []

        # 搜索长期记忆
        if self._long_term:
            for topic in self._long_term.list_topics():
                try:
                    if not isinstance(topic, dict) or "file" not in topic:
                        logger.warning("跳过格式异常的长期记忆条目: %r", topic)
                        continue
                    content = self._long_term.read_topic(topic["file"])
                    if not isinstance(content, str):
                        logger.warning("长期记忆 topic=%s 内容非字符串，跳过", topic["file"])
                        continue
                    score = self._score(content, keywords)
                    if score > 0:
                        results.append(MemoryResult(
                            source="long_term",
                            content=self._extract_snippet(content, keywords),
                            relevance=score,
                            topic=topic["file"],
                        ))
                except Exception:
                    logger.warning("读取长期记忆 topic=%r 失败，跳过", topic, exc_info=True)

        # 搜索短期记忆
        if self._short_term:
            for item in self._short_term.get_recent(limit=100):
                try:
                    if not isinstance(item, dict):
                        logger.warning("跳过格式异常的短期记忆条目: %r", item)
                        continue
                    content = item.get("content")
                    if not isinstance(content, str):
                        logger.warning("短期记忆 content 非字符串 (%r)，跳过", content)
                        continue
                    score = self._score(content, keywords)
                    if score > 0:
                        results.append(MemoryResult(
                            source="short_term",
                            content=content,
                            relevance=score,
                        ))
                except Exception:
                    logger.warning("读取短期记忆条目 %r 失败，跳过", item, exc_info=True)

        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[:limit]

    @staticmethod
    def _extract_keywords(query: str) -> list[str]:
        """从查询中提取关键词，过滤短词（CJK 单字保留）。"""
        words = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
        # CJK 单字有意义，保留；拉丁/数字仍要求 len >= 2
        seen: set[str] = set()
        result: list[str] = []
        for w in words:
            if w in seen:
                continue
            is_cjk = bool(re.match(r"[\u4e00-\u9fff]", w))
            if len(w) >= 2 or is_cjk:
                seen.add(w)
                result.append(w)
        return result

    @staticmethod
    def _score(text: str, keywords: list[str]) -> float:
        """计算文本与关键词的相关度分数。"""
        text_lower = text.lower()
        hits = sum(1 for kw in keywords if kw in text_lower)
        return hits / len(keywords) if keywords else 0

    @staticmethod
    def _extract_snippet(content: str, keywords: list[str], context_chars: int = 200) -> str:
        """提取包含关键词的文本片段。"""
        content_lower = content.lower()
        for kw in keywords:
            idx = content_lower.find(kw)
            if idx >= 0:
                start = max(0, idx - context_chars)
                end = min(len(content), idx + len(kw) + context_chars)
                return content[start:end]
        return content[:context_chars]
