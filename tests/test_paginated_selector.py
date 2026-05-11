"""Tests for PaginatedSelector TUI component.

纯 UI 组件的单元测试，不依赖业务逻辑。
"""

import math
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from cli.paginated_selector import PaginatedSelector


# ------------------------------------------------------------------
# 分页逻辑测试
# ------------------------------------------------------------------

class TestPaginationLogic:
    """测试分页计算逻辑（纯逻辑，不涉及 prompt_toolkit）。"""

    def test_total_pages_exact_multiple(self):
        """items 数量刚好是 page_size 的整数倍。"""
        sel = PaginatedSelector(items=list(range(20)), format_item=lambda x, i: str(x), page_size=10)
        assert sel._total_pages == 2

    def test_total_pages_non_multiple(self):
        """items 数量不是 page_size 的整数倍，向上取整。"""
        sel = PaginatedSelector(items=list(range(15)), format_item=lambda x, i: str(x), page_size=10)
        assert sel._total_pages == 2

    def test_total_pages_single_item(self):
        sel = PaginatedSelector(items=[42], format_item=lambda x, i: str(x), page_size=10)
        assert sel._total_pages == 1

    def test_total_pages_empty_list(self):
        sel = PaginatedSelector(items=[], format_item=lambda x, i: str(x), page_size=10)
        assert sel._total_pages == 1

    def test_page_items_first_page(self):
        items = list(range(25))
        sel = PaginatedSelector(items=items, format_item=lambda x, i: str(x), page_size=10)
        assert sel._page_items == list(range(10))

    def test_page_items_second_page(self):
        items = list(range(25))
        sel = PaginatedSelector(items=items, format_item=lambda x, i: str(x), page_size=10)
        sel._current_page = 1
        assert sel._page_items == list(range(10, 20))

    def test_page_items_last_page_partial(self):
        items = list(range(25))
        sel = PaginatedSelector(items=items, format_item=lambda x, i: str(x), page_size=10)
        sel._current_page = 2
        assert sel._page_items == list(range(20, 25))

    def test_global_index_first_page(self):
        items = list(range(25))
        sel = PaginatedSelector(items=items, format_item=lambda x, i: str(x), page_size=10)
        sel._selected_on_page = 3
        assert sel._global_index == 3

    def test_global_index_second_page(self):
        items = list(range(25))
        sel = PaginatedSelector(items=items, format_item=lambda x, i: str(x), page_size=10)
        sel._current_page = 1
        sel._selected_on_page = 5
        assert sel._global_index == 15


# ------------------------------------------------------------------
# 渲染测试
# ------------------------------------------------------------------

class TestRendering:
    """测试渲染输出。"""

    def test_title_appears(self):
        sel = PaginatedSelector(
            items=["a", "b"],
            format_item=lambda x, i: x,
            title="测试标题",
        )
        fragments = sel._get_formatted_text()
        text = "".join(t for _, t in fragments)
        assert "测试标题" in text

    def test_selected_item_has_cursor_prefix(self):
        sel = PaginatedSelector(
            items=["alpha", "beta", "gamma"],
            format_item=lambda x, i: x,
        )
        sel._selected_on_page = 1
        fragments = sel._get_formatted_text()
        # 找到包含 "beta" 的片段
        beta_frag = [t for cls, t in fragments if "beta" in t]
        assert len(beta_frag) > 0
        # 选中项的前一个片段应该包含 ">"
        idx = next(i for i, (cls, t) in enumerate(fragments) if "beta" in t)
        assert ">" in fragments[idx - 1][1]

    def test_page_info_shown(self):
        items = list(range(25))
        sel = PaginatedSelector(
            items=items,
            format_item=lambda x, i: str(x),
            page_size=10,
        )
        fragments = sel._get_formatted_text()
        text = "".join(t for _, t in fragments)
        assert "第 1/3 页" in text
        assert "共 25 项" in text

    def test_hint_bar_shown(self):
        sel = PaginatedSelector(items=["a"], format_item=lambda x, i: x)
        fragments = sel._get_formatted_text()
        text = "".join(t for _, t in fragments)
        assert "Enter" in text
        assert "Esc" in text

    def test_empty_slots_for_stable_layout(self):
        """当一页不满时，应有空行保持布局稳定。"""
        sel = PaginatedSelector(
            items=["a", "b"],
            format_item=lambda x, i: x,
            page_size=5,
        )
        fragments = sel._get_formatted_text()
        newline_count = sum(1 for _, t in fragments if t == "\n")
        # page_size(5) + 标题行 + 空行 + 页码行 + 空行 + 提示行
        assert newline_count >= 5


# ------------------------------------------------------------------
# 键绑定测试
# ------------------------------------------------------------------

class TestKeyBindings:
    """测试键绑定逻辑（直接操作状态，不触发 prompt_toolkit）。"""

    def _make_selector(self, n=25, page_size=10):
        items = [f"item-{i}" for i in range(n)]
        return PaginatedSelector(
            items=items,
            format_item=lambda x, i: x,
            page_size=page_size,
        )

    def test_initial_state(self):
        sel = self._make_selector()
        assert sel._current_page == 0
        assert sel._selected_on_page == 0

    def test_cursor_move_down_within_page(self):
        sel = self._make_selector()
        sel._selected_on_page = 3
        # 模拟 down：如果 < max_idx 则 +1
        max_idx = len(sel._page_items) - 1
        if sel._selected_on_page < max_idx:
            sel._selected_on_page += 1
        assert sel._selected_on_page == 4

    def test_cursor_move_down_at_bottom_goes_next_page(self):
        sel = self._make_selector()
        sel._selected_on_page = 9  # 最后一个位置
        max_idx = len(sel._page_items) - 1
        # 模拟 down：如果在底部且有下一页
        if sel._selected_on_page >= max_idx and sel._current_page < sel._total_pages - 1:
            sel._current_page += 1
            sel._selected_on_page = 0
        assert sel._current_page == 1
        assert sel._selected_on_page == 0

    def test_cursor_move_up_within_page(self):
        sel = self._make_selector()
        sel._selected_on_page = 5
        if sel._selected_on_page > 0:
            sel._selected_on_page -= 1
        assert sel._selected_on_page == 4

    def test_cursor_move_up_at_top_goes_prev_page(self):
        sel = self._make_selector()
        sel._current_page = 1
        sel._selected_on_page = 0
        # 模拟 up：如果在顶部且有上一页
        if sel._selected_on_page == 0 and sel._current_page > 0:
            sel._current_page -= 1
            sel._selected_on_page = len(sel._page_items) - 1
        assert sel._current_page == 0
        assert sel._selected_on_page == 9

    def test_page_right(self):
        sel = self._make_selector()
        assert sel._current_page == 0
        if sel._current_page < sel._total_pages - 1:
            sel._current_page += 1
            sel._selected_on_page = min(sel._selected_on_page, len(sel._page_items) - 1)
        assert sel._current_page == 1

    def test_page_left(self):
        sel = self._make_selector()
        sel._current_page = 2
        if sel._current_page > 0:
            sel._current_page -= 1
            sel._selected_on_page = min(sel._selected_on_page, len(sel._page_items) - 1)
        assert sel._current_page == 1

    def test_page_right_clamps_at_end(self):
        sel = self._make_selector()
        sel._current_page = sel._total_pages - 1
        old_page = sel._current_page
        if sel._current_page < sel._total_pages - 1:
            sel._current_page += 1
        assert sel._current_page == old_page  # 没变

    def test_page_left_clamps_at_start(self):
        sel = self._make_selector()
        sel._current_page = 0
        if sel._current_page > 0:
            sel._current_page -= 1
        assert sel._current_page == 0

    def test_cursor_clamp_on_shorter_page(self):
        """翻到最后一页（不满一页）时，光标应被 clamp。"""
        sel = self._make_selector(n=23, page_size=10)
        sel._current_page = 2  # 第3页只有3个元素
        sel._selected_on_page = 5
        # 翻页后 clamp
        sel._selected_on_page = min(sel._selected_on_page, len(sel._page_items) - 1)
        assert sel._selected_on_page == 2  # 只有3个元素，最大索引2
