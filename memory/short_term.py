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
        # 旧格式迁移结果暂存（在 glob 扫描期间使用）
        self._pending_migrated_items: list[dict[str, Any]] = []

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

    # UUID 文件名模式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

    # item 必要字段及其期望类型
    # created 允许任意类型（排序时降级处理），其他字段要求字符串
    _REQUIRED_ITEM_FIELDS = {
        "id": str,
        "content": str,
        "source": str,
    }
    _REQUIRED_ITEM_ANY_TYPE = {"created"}

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

    @classmethod
    def _sanitize_items(cls, items: list[dict]) -> list[dict]:
        """校验并过滤 item 级 schema：保留必要字段齐全且类型正确的条目。
        id/content/source 必须为字符串，created 只需存在（允许任意类型）。
        """
        valid = []
        for item in items:
            ok = True
            # 检查必须为字符串的字段
            for field, expected_type in cls._REQUIRED_ITEM_FIELDS.items():
                val = item.get(field)
                if val is None or not isinstance(val, expected_type):
                    ok = False
                    break
            # 检查 created 字段存在（不要求类型）
            if ok and item.get("created") is None:
                ok = False
            if ok:
                valid.append(item)
        return valid

    @classmethod
    def _is_legacy_file(cls, path: Path) -> bool:
        """判断文件是否为旧格式（UUID 命名的 session 文件）。"""
        return bool(cls._UUID_RE.match(path.stem))

    def _migrate_legacy_file(self, path: Path) -> list[dict[str, Any]]:
        """迁移旧格式 session 文件到日期 bucket。
        根据 items 的 created 字段确定目标日期，写入对应日期文件。
        迁移成功后删除旧文件；无法迁移则隔离。
        返回迁移后的所有有效 items（供调用方直接使用）。
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine_file(path)
            return []

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self._quarantine_file(path)
            return []

        # 按日期分组 items
        date_buckets: dict[str, list[dict]] = {}
        all_migrated: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            created = item.get("created", "")
            if not isinstance(created, str) or len(created) < 10:
                continue
            date_str = created[:10]  # "YYYY-MM-DD"
            try:
                self._validate_date(date_str)
            except ValueError:
                continue
            if date_str not in date_buckets:
                date_buckets[date_str] = []
            date_buckets[date_str].append(item)
            all_migrated.append(item)

        if not date_buckets:
            # 没有可迁移的 items，隔离
            self._quarantine_file(path)
            return []

        # 合并到目标日期文件
        for date_str, new_items in date_buckets.items():
            target_path = self._date_path(date_str)
            with self._file_lock(target_path):
                if target_path.exists():
                    existing = self._read_and_validate(target_path, skip_legacy=True)
                    if existing is None:
                        existing = self._empty_date_file(date_str)
                else:
                    existing = self._empty_date_file(date_str)
                existing["items"].extend(new_items)
                self._atomic_write(target_path, existing)

        # 迁移完成，删除旧文件
        try:
            path.unlink()
            logger.info("旧格式文件已迁移: %s", path.name)
        except OSError:
            logger.warning("旧格式文件迁移后删除失败: %s", path.name)

        return all_migrated

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
        """加载指定日期的数据文件，使用集中校验，损坏文件会被隔离。
        item 级校验：丢弃缺少必要字段的条目。
        """
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
        # item 级校验：丢弃坏条目，保留好条目
        data["items"] = self._sanitize_items(data["items"])
        return data

    def _read_and_validate(self, path: Path, *, skip_legacy: bool = False) -> dict | None:
        """从指定路径读取并集中校验，校验失败返回 None（已隔离）。
        支持旧格式文件迁移（skip_legacy=True 时跳过，用于已持有文件锁的场景）。
        item 级校验：丢弃缺少必要字段的条目。
        旧格式迁移后的 items 通过 _pending_migrated_items 暂存，调用方需取出。
        """
        # 旧格式 UUID 文件：迁移而非隔离
        if not skip_legacy and self._is_legacy_file(path):
            migrated = self._migrate_legacy_file(path)
            # 暂存迁移结果，供调用方取出
            self._pending_migrated_items.extend(migrated)
            return None  # 迁移后旧文件已删除，调用方跳过
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quarantine_file(path)
            return None
        if not self._validate_file_shape(path, data):
            return None
        # item 级校验：丢弃坏条目，保留好条目
        data["items"] = self._sanitize_items(data["items"])
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

    @staticmethod
    def _sort_key_created(item: dict) -> str:
        """排序用的 created 键提取：非字符串类型降级为空字符串。"""
        val = item.get("created", "")
        return val if isinstance(val, str) else ""

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """跨日期文件聚合最近的 items，按 mtime 倒序扫描文件。"""
        self._pending_migrated_items = []
        all_items: list[dict[str, Any]] = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            data = self._read_and_validate(p)
            if data is None:
                continue
            for item in data.get("items", []):
                all_items.append(item)
        # 添加旧格式迁移后的 items
        all_items.extend(self._pending_migrated_items)
        self._pending_migrated_items = []
        all_items.sort(key=self._sort_key_created, reverse=True)
        return all_items[:limit]

    def get_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """跨日期文件扫描指定 session 的 items。"""
        self._pending_migrated_items = []
        all_items: list[dict[str, Any]] = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            data = self._read_and_validate(p)
            if data is None:
                continue
            for item in data.get("items", []):
                if item.get("session_id") == session_id:
                    all_items.append(item)
        # 添加旧格式迁移后的 items（按 session 过滤）
        for item in self._pending_migrated_items:
            if item.get("session_id") == session_id:
                all_items.append(item)
        self._pending_migrated_items = []
        all_items.sort(key=self._sort_key_created, reverse=True)
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
        """跨日期文件删除指定 id 的 items。
        每个文件的 read-modify-write 在文件锁内完成，防止并发丢失数据。
        """
        ids = set(item_ids)
        for p in self._dir.glob("*.json"):
            # 旧格式文件迁移（不需要文件锁，因为是独立操作）
            if self._is_legacy_file(p):
                self._migrate_legacy_file(p)
                continue
            with self._file_lock(p):
                data = self._read_and_validate(p, skip_legacy=True)
                if data is None:
                    continue
                original_len = len(data["items"])
                data["items"] = [i for i in data["items"] if i.get("id") not in ids]
                if len(data["items"]) != original_len:
                    self._atomic_write(p, data)

    def cleanup_sessions(self, session_ids: list[str]) -> None:
        """删除指定 session 的所有 items（跨日期文件扫描）。
        每个文件的 read-modify-write 在文件锁内完成，防止并发丢失数据。
        """
        sids = set(session_ids)
        for p in self._dir.glob("*.json"):
            # 旧格式文件迁移（不需要文件锁，因为是独立操作）
            if self._is_legacy_file(p):
                self._migrate_legacy_file(p)
                continue
            with self._file_lock(p):
                data = self._read_and_validate(p, skip_legacy=True)
                if data is None:
                    continue
                original_len = len(data["items"])
                data["items"] = [i for i in data["items"] if i.get("session_id") not in sids]
                if len(data["items"]) != original_len:
                    self._atomic_write(p, data)

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
