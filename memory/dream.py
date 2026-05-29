"""Dream 蒸馏管理。"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 双门槛常量
MIN_HOURS = 24
MIN_SESSIONS = 5
MAX_USER_MD_LINES = 50


class DreamManager:
    """Dream 蒸馏：定期将短期记忆整理为长期记忆和核心记忆。"""

    def __init__(
        self,
        data_dir: Path,
        short_term: Any | None = None,
        long_term: Any | None = None,
        user_manager: Any | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._dream_dir = data_dir / "dream"
        self._dream_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._dream_dir / "dream-state.json"
        self._short_term = short_term
        self._long_term = long_term
        self._user_manager = user_manager
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "last_dream_at": datetime.now(timezone.utc).isoformat(),
            "sessions_since_dream": 0,
            "total_dreams": 0,
        }

    def _save_state(self) -> None:
        """原子写入：先写临时文件，再 os.replace()，防止中断导致 JSON 损坏。"""
        content = json.dumps(self._state, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(
            dir=self._dream_dir, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._state_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def should_dream(self) -> bool:
        """检查是否满足双门槛：时间间隔 + 会话数量。"""
        try:
            last = datetime.fromisoformat(self._state["last_dream_at"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            last = datetime.min.replace(tzinfo=timezone.utc)

        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        # 时钟偏移：last_dream_at 在未来时视为无效，触发 dream
        if hours_since < 0:
            hours_since = float("inf")
        sessions = self._state.get("sessions_since_dream", 0)

        return hours_since >= MIN_HOURS and sessions >= MIN_SESSIONS

    def on_session_created(self) -> None:
        """新会话创建时递增计数。"""
        self._state["sessions_since_dream"] = self._state.get("sessions_since_dream", 0) + 1
        self._save_state()

    async def run(self, llm_client: Any, model: str) -> None:
        """执行 Dream 蒸馏。"""
        if not self._short_term:
            return

        # 1. 收集
        items = self._short_term.get_recent(limit=200)
        if not items:
            self._update_state_after_dream()
            return

        # 2. 去重/合并 + 3. 分类（用 LLM）
        try:
            classification = await self._classify_items(llm_client, model, items)
        except Exception:
            logger.warning("Dream 蒸馏 LLM 调用失败，保留会话计数以便重试", exc_info=True)
            return

        # 3. 写入（跟踪成功/失败）
        all_writes_ok = True
        core_items = classification.get("core", [])
        topics = classification.get("topics", {})

        # Issue 2: 降级处理 — sink 不可用但有需写入内容时视为失败
        if core_items and not self._user_manager:
            logger.warning("user_manager 不可用但有 core items，视为写入失败")
            all_writes_ok = False
        if topics and not self._long_term:
            logger.warning("long_term 不可用但有 topics，视为写入失败")
            all_writes_ok = False

        for item in core_items:
            if self._user_manager:
                self._append_to_user_md(item)

        for topic, contents in topics.items():
            if self._long_term:
                if not self._write_to_long_term(topic, contents):
                    all_writes_ok = False

        # 4. 仅在全部写入成功后清理和推进状态
        if not all_writes_ok:
            logger.warning("部分写入失败，跳过清理短期记忆和状态推进")
            return

        # Issue 1: 用 item 级删除替代 session 级清理，避免误删未处理的 items
        processed_ids = [i.get("id", "") for i in items if i.get("id")]
        if processed_ids:
            self._short_term.remove_items(processed_ids)
        self._update_state_after_dream()

    async def _classify_items(self, llm_client: Any, model: str, items: list[dict]) -> dict:
        """用 LLM 对短期记忆分类。

        解析失败时抛出异常，由调用方决定是否清理短期记忆。
        """
        items_text = "\n".join(
            f"- [{i.get('source', '?')}] {i.get('content', '')}"
            for i in items[:50]  # 限制输入量
        )
        prompt = f"""分析以下短期记忆，分类为：
1. core：核心信息（用户反复强调、基本偏好、关键个人信息），写入永久记忆
2. topics：主题知识（有价值但非核心），按主题分组
3. discard：琐碎/过时/一次性的信息

短期记忆：
{items_text}

返回 JSON 格式：
{{"core": ["核心记忆1", "核心记忆2"], "topics": {{"主题名": ["知识1", "知识2"]}}, "discard": ["丢弃1"]}}"""

        response = await llm_client.chat(
            messages=[
                {"role": "system", "content": "你是记忆分类助手。只返回 JSON，不要解释。"},
                {"role": "user", "content": prompt},
            ],
            model=model,
        )
        # 提取 JSON 文本
        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        # 解析失败直接抛异常，不返回 fallback
        result = json.loads(text)  # 可能抛 JSONDecodeError
        if not isinstance(result, dict):
            raise ValueError(f"LLM 返回非 dict 类型: {type(result)}")
        return self._validate_classification(result)

    @staticmethod
    def _slugify_topic(name: str) -> str:
        """将主题名转为安全的 ASCII slug。

        仅保留字母、数字、下划线、短横线；空格转下划线；全部小写。
        """
        slug = name.lower().replace(" ", "_")
        # 移除所有非 ASCII 字母数字和 _ - 的字符
        slug = re.sub(r"[^a-z0-9_\-]", "", slug)
        # 合并连续下划线
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug or "untitled"

    @staticmethod
    def _validate_classification(result: dict) -> dict:
        """校验分类结果结构，过滤无效条目。"""
        # core: 保留字符串条目
        raw_core = result.get("core", [])
        if isinstance(raw_core, list):
            core = [s for s in raw_core if isinstance(s, str)]
        else:
            core = []

        # topics: dict[str, list[str]]，key 转为安全 slug
        raw_topics = result.get("topics", {})
        topics: dict[str, list[str]] = {}
        if isinstance(raw_topics, dict):
            for key, val in raw_topics.items():
                if isinstance(key, str) and isinstance(val, list):
                    safe_key = DreamManager._slugify_topic(key)
                    filtered = [s for s in val if isinstance(s, str)]
                    if safe_key in topics:
                        topics[safe_key].extend(filtered)
                    else:
                        topics[safe_key] = filtered

        return {"core": core, "topics": topics}

    def _append_to_user_md(self, content: str) -> None:
        """将核心记忆追加到 user.md（严格控制行数）。"""
        if not self._user_manager:
            return
        current = self._user_manager.load()
        lines = current.strip().splitlines()
        if len(lines) >= MAX_USER_MD_LINES:
            logger.warning("user.md 已达 %d 行上限，跳过追加", MAX_USER_MD_LINES)
            return
        new_line = f"- {content}"
        if new_line not in current:
            updated = current.rstrip() + "\n" + new_line + "\n"
            self._user_manager.save(updated)

    def _write_to_long_term(self, topic: str, contents: list[str]) -> bool:
        """将主题知识写入长期记忆。topic 应已被 _slugify_topic 处理。

        Returns:
            True 表示写入成功，False 表示写入失败。
        """
        if not self._long_term:
            return True
        safe_name = topic + ".md"
        try:
            existing = self._long_term.read_topic(safe_name)
            new_content = "\n".join(f"- {c}" for c in contents)
            if new_content not in existing:
                combined = existing.rstrip() + "\n" + new_content + "\n" if existing else new_content + "\n"
                self._long_term.write_topic(safe_name, combined, {
                    "name": topic,
                    "description": f"关于{topic}的记忆",
                    "type": "user",
                })
                self._long_term.update_index()
            return True
        except Exception:
            logger.warning("写入长期记忆主题 %r 失败", topic, exc_info=True)
            return False

    def _update_state_after_dream(self) -> None:
        self._state["last_dream_at"] = datetime.now(timezone.utc).isoformat()
        self._state["sessions_since_dream"] = 0
        self._state["total_dreams"] = self._state.get("total_dreams", 0) + 1
        self._save_state()
