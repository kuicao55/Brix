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
        soul_manager: Any | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._dream_dir = data_dir / "dream"
        self._dream_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._dream_dir / "dream-state.json"
        self._short_term = short_term
        self._long_term = long_term
        self._user_manager = user_manager
        self._soul_manager = soul_manager
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
        """执行 Dream 蒸馏（五路径）。"""
        if not self._short_term:
            return

        # 1. 收集
        items = self._short_term.get_recent(limit=200)
        if not items:
            self._update_state_after_dream()
            return

        # 2. 分类（用 LLM）
        try:
            classification = await self._classify_items(llm_client, model, items)
        except Exception:
            logger.warning("Dream 蒸馏 LLM 调用失败，保留会话计数以便重试", exc_info=True)
            return

        # 3. 写入（跟踪成功/失败）
        all_writes_ok = True

        user_items = classification.get("user", [])
        knowledge_items = classification.get("knowledge", [])
        work_items = classification.get("work", [])
        history_items = classification.get("history", [])
        soul_items = classification.get("soul", [])
        discard_items = classification.get("discard", [])

        # Finding 2: 全空分类守卫 — LLM 返回退化响应时跳过清理和状态推进
        if not any([user_items, knowledge_items, work_items, history_items, soul_items, discard_items]):
            logger.warning("分类结果全部为空（退化 LLM 响应），跳过清理和状态推进")
            return

        # 降级处理 — sink 不可用但有需写入内容时视为失败
        if user_items and not self._user_manager:
            logger.warning("user_manager 不可用但有 user items，视为写入失败")
            all_writes_ok = False
        long_term_items = knowledge_items or work_items or history_items
        if long_term_items and not self._long_term:
            logger.warning("long_term 不可用但有 knowledge/work/history items，视为写入失败")
            all_writes_ok = False
        if soul_items and not self._soul_manager:
            logger.warning("soul_manager 不可用但有 soul items，视为写入失败")
            all_writes_ok = False

        # user → user_manager
        for item in user_items:
            if self._user_manager:
                self._append_to_user_md(item)

        # knowledge → knowledge.md
        if knowledge_items and self._long_term:
            if not self._write_to_long_term("knowledge", knowledge_items):
                all_writes_ok = False

        # work → work.md
        if work_items and self._long_term:
            if not self._write_to_long_term("work", work_items):
                all_writes_ok = False

        # history → history.md
        if history_items and self._long_term:
            if not self._write_to_long_term("history", history_items):
                all_writes_ok = False

        # soul → soul_manager
        # 将所有 soul items 合并为一批写入，避免逐条 save_growth 覆盖已有内容
        # TODO: Task 3 会实现 _update_soul_growth() 替代此临时方案
        if soul_items and self._soul_manager:
            try:
                batch = "\n".join(f"- {s}" for s in soul_items)
                self._soul_manager.save_growth(batch)
            except Exception:
                logger.warning("写入 soul 失败", exc_info=True)
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

    @staticmethod
    def _format_items_text(items: list[dict]) -> str:
        """格式化 items 为带 type/category 信息的文本。"""
        lines = []
        for i in items:
            content = i.get("content", "")
            item_type = i.get("type", "")
            category = i.get("category", "")
            if item_type or category:
                lines.append(f"- [{item_type}/{category}] {content}")
            else:
                source = i.get("source", "?")
                lines.append(f"- [{source}] {content}")
        return "\n".join(lines)

    async def _classify_items(self, llm_client: Any, model: str, items: list[dict]) -> dict:
        """用 LLM 对短期记忆分类（五路径）。

        解析失败时抛出异常，由调用方决定是否清理短期记忆。
        """
        items_text = self._format_items_text(items[:50])
        prompt = f"""分析以下短期记忆，分类为 6 个路径：

1. user：核心用户画像信息（偏好、基本信息、关键个人信息）
2. knowledge：通用知识（有价值的事实、技术知识）
3. work：工作相关信息（项目、任务、截止日期）
4. history：经历事件（非工作的生活经历、旅行等）
5. soul：性格倾向、经验教训、情绪状态、反思
6. discard：琐碎/过时/一次性的信息

判断指引：
- preference + fact(category=user, 核心) → user
- fact(通用知识) → knowledge
- fact + event(工作相关) → work
- event(非工作经历) → history
- emotion + reflection → soul
- 琐碎/过时/一次性 → discard

短期记忆：
{items_text}

返回 JSON 格式：
{{"user": ["信息1"], "knowledge": ["知识1"], "work": ["工作1"], "history": ["经历1"], "soul": ["反思1"], "discard": ["丢弃1"]}}"""

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
        """校验分类结果结构（6-key 五路径），过滤无效条目。"""
        keys = ("user", "knowledge", "work", "history", "soul", "discard")
        validated: dict[str, list[str]] = {}
        for key in keys:
            raw = result.get(key, [])
            if isinstance(raw, list):
                validated[key] = [s for s in raw if isinstance(s, str)]
            else:
                validated[key] = []
        return validated

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
        """将主题知识写入长期记忆（使用 append 模式，由 write_topic 内部去重和加锁）。

        Returns:
            True 表示写入成功，False 表示写入失败。
        """
        if not self._long_term:
            return True
        safe_name = topic + ".md"
        try:
            new_content = "\n".join(f"- {c}" for c in contents)
            self._long_term.write_topic(safe_name, new_content, {
                "name": topic,
                "description": f"关于{topic}的记忆",
                "type": "long_term",
            }, append=True)
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
