"""短期记忆管理 — 按日期文件结构。"""
from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 日期格式校验：YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ShortTermMemory:
    """管理短期记忆的读写。每天一个 JSON 文件，路径为 short-term/YYYY-MM-DD.json。"""

    def __init__(self, data_dir: Path) -> None:
        self._dir = (data_dir / "short-term").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def _validate_date(date: str) -> None:
        """校验日期格式和语义合法性，防路径遍历。"""
        if not _DATE_RE.match(date):
            raise ValueError(f"非法日期: {date!r}，要求格式 YYYY-MM-DD")
        # 语义校验：确保是真实日期
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"非法日期: {date!r}，不是有效日期")

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

    @staticmethod
    def _validate_file_shape(path: Path, data: Any) -> bool:
        """集中校验文件结构：dict + date 字符串 + items 为 dict 列表。
        date 必须匹配文件名 stem，否则隔离。
        校验通过返回 True；隔离后返回 False。
        """
        stem = path.stem  # "YYYY-MM-DD"
        ok = (
            isinstance(data, dict)
            and isinstance(data.get("date"), str)
            and isinstance(data.get("items"), list)
            and data["date"] == stem
            and all(isinstance(i, dict) for i in data["items"])
        )
        if not ok:
            ShortTermMemory._quarantine_file(path)
        return ok

    def _date_path(self, date: str) -> Path:
        """返回日期文件路径，校验日期格式防止路径遍历。"""
        self._validate_date(date)
        path = (self._dir / f"{date}.json").resolve()
        if not path.is_relative_to(self._dir):
            raise ValueError(f"路径遍历: {date!r}")
        return path

    @staticmethod
    def _empty_date_file(date: str) -> dict:
        return {"date": date, "items": []}

    def _load_date_file(self, date: str) -> dict:
        """加载指定日期的数据文件，使用集中校验，损坏文件会被隔离。"""
        path = self._date_path(date)
        if not path.exists():
            return self._empty_date_file(date)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine_file(path)
            return self._empty_date_file(date)
        if not self._validate_file_shape(path, data):
            return self._empty_date_file(date)
        return data

    def _read_and_validate(self, path: Path) -> dict | None:
        """从指定路径读取并集中校验，校验失败返回 None（已隔离）。"""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine_file(path)
            return None
        if not self._validate_file_shape(path, data):
            return None
        return data

    @staticmethod
    def _quarantine_file(path: Path) -> None:
        """将损坏的文件重命名为 .corrupt，保留原始内容供排查。"""
        quarantine_path = path.with_suffix(path.suffix + ".corrupt")
        try:
            os.replace(path, quarantine_path)
            logger.warning("日期文件损坏，已隔离为: %s", quarantine_path)
        except OSError:
            logger.warning("日期文件损坏且隔离失败: %s", path)

    def _save_date_file(self, data: dict) -> None:
        """原子写入：先写临时文件，再 rename，防止中断导致数据损坏。"""
        path = self._date_path(data["date"])
        self._atomic_write(path, data)

    def _save_to_path(self, data: dict, path: Path) -> None:
        """原子写入到指定路径（用于 remove_items/cleanup_sessions 避免跨日期覆盖）。"""
        self._atomic_write(path, data)

    def _atomic_write(self, path: Path, data: dict) -> None:
        """原子写入核心：先写临时文件，再 os.replace。"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_item(
        self,
        content: str,
        source: str,
        *,
        date: str = "",
        type: str = "note",
        category: str = "",
        session_id: str = "",
        context: str = "",
    ) -> None:
        """添加一条短期记忆。date 默认为今天（UTC）。"""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._date_path(date)
        with self._file_lock(path), self._lock:
            data = self._load_date_file(date)
            now = datetime.now(timezone.utc).isoformat()
            data["items"].append({
                "id": str(uuid.uuid4()),
                "content": content,
                "source": source,
                "type": type,
                "category": category,
                "session_id": session_id,
                "created": now,
                "context": context,
            })
            self._save_date_file(data)

    def get_by_date(self, date: str) -> list[dict[str, Any]]:
        """返回指定日期的所有 items。"""
        self._validate_date(date)
        return self._load_date_file(date).get("items", [])

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """跨日期文件聚合最近的 items，按 mtime 倒序扫描文件。"""
        all_items: list[dict[str, Any]] = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            data = self._read_and_validate(p)
            if data is None:
                continue
            for item in data.get("items", []):
                all_items.append(item)
        all_items.sort(key=lambda x: x.get("created", ""), reverse=True)
        return all_items[:limit]

    def get_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """跨日期文件扫描指定 session 的 items。"""
        all_items: list[dict[str, Any]] = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            data = self._read_and_validate(p)
            if data is None:
                continue
            for item in data.get("items", []):
                if item.get("session_id") == session_id:
                    all_items.append(item)
        all_items.sort(key=lambda x: x.get("created", ""), reverse=True)
        return all_items

    def get_summary(self, limit: int = 10) -> str | None:
        """返回最近 N 条短期记忆的格式化摘要（含时间和类型）。无内容返回 None。

        格式：- [Weekday YYYY-MM-DD HH:MM] [{type}] {content}
        """
        items = self.get_recent(limit=limit)
        lines: list[str] = []
        for item in items:
            content = item.get("content", "")
            if not content or not isinstance(content, str):
                continue
            ts = item.get("created", "")
            item_type = item.get("type", "note")
            dt_str = self._format_ts(ts)
            if dt_str:
                lines.append(f"- [{dt_str}] [{item_type}] {content}")
            else:
                lines.append(f"- [{item_type}] {content}")
        return "\n".join(lines) if lines else None

    @staticmethod
    def _format_ts(ts: str) -> str:
        """将 ISO 时间戳格式化为 'Weekday YYYY-MM-DD HH:MM'（本地时区）。"""
        if len(ts) < 16:
            return ""
        try:
            dt = datetime.fromisoformat(ts)
            local_dt = dt.astimezone()
            return local_dt.strftime("%A %Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return ts[:16].replace("T", " ")

    def remove_items(self, item_ids: list[str]) -> None:
        """跨日期文件删除指定 id 的 items。"""
        ids = set(item_ids)
        for p in self._dir.glob("*.json"):
            data = self._read_and_validate(p)
            if data is None:
                continue
            original_len = len(data["items"])
            data["items"] = [i for i in data["items"] if i.get("id") not in ids]
            if len(data["items"]) != original_len:
                self._save_to_path(data, p)

    def cleanup_sessions(self, session_ids: list[str]) -> None:
        """删除指定 session 的所有 items（跨日期文件扫描）。"""
        sids = set(session_ids)
        for p in self._dir.glob("*.json"):
            data = self._read_and_validate(p)
            if data is None:
                continue
            original_len = len(data["items"])
            data["items"] = [i for i in data["items"] if i.get("session_id") not in sids]
            if len(data["items"]) != original_len:
                self._save_to_path(data, p)

    def cleanup_old(self, keep_days: int = 14, today: str = "") -> None:
        """清理超过 keep_days 天的日期文件。today 参数仅供测试使用。"""
        if not today:
            cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
        else:
            cutoff = datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=keep_days)
        for p in self._dir.glob("*.json"):
            name = p.stem  # "YYYY-MM-DD"
            if not _DATE_RE.match(name):
                continue  # 跳过非日期文件
            try:
                file_date = datetime.strptime(name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    p.unlink()
                    logger.info("清理过期日期文件: %s", p.name)
                except OSError:
                    logger.warning("清理过期文件失败: %s", p.name)
