"""通用分页选择器 TUI 组件。

纯 UI 组件，不依赖任何业务逻辑。可被任意命令复用。
"""

from __future__ import annotations

import math
from typing import Callable, Generic, TypeVar

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import BaseStyle, Style

__all__ = ["PaginatedSelector"]

_T = TypeVar("_T")
E = KeyPressEvent

# 样式定义
PAGINATED_STYLE = Style.from_dict(
    {
        "paginated.title": "bold",
        "paginated.selected": "bold ansigreen",
        "paginated.item": "",
        "paginated.info": "ansibrightblack",
        "paginated.hint": "ansibrightblack",
        "paginated.cursor": "bold ansicyan",
    }
)


class PaginatedSelector(Generic[_T]):
    """带分页的交互式选择器。

    用法::

        selector = PaginatedSelector(
            items=[...],
            format_item=lambda item, idx: f"{item.name}",
            page_size=10,
            title="选择一个项目",
        )
        result = await selector.prompt_async()
    """

    def __init__(
        self,
        *,
        items: list[_T],
        format_item: Callable[[_T, int], str],
        page_size: int = 10,
        title: str = "选择一个项目",
        style: BaseStyle | None = None,
    ) -> None:
        self._items = items
        self._format_item = format_item
        self._page_size = page_size
        self._title = title
        self._style = style or PAGINATED_STYLE

        # 游标状态
        self._current_page: int = 0
        self._selected_on_page: int = 0

    @property
    def _total_pages(self) -> int:
        if not self._items:
            return 1
        return math.ceil(len(self._items) / self._page_size)

    @property
    def _page_start(self) -> int:
        return self._current_page * self._page_size

    @property
    def _page_items(self) -> list[_T]:
        return self._items[self._page_start : self._page_start + self._page_size]

    @property
    def _global_index(self) -> int:
        return self._page_start + self._selected_on_page

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------

    def _get_formatted_text(self) -> list[tuple[str, str]]:
        """生成当前页的格式化文本片段。"""
        fragments: list[tuple[str, str]] = []

        # 标题
        fragments.append(("class:paginated.title", f"  {self._title}\n"))
        fragments.append(("", "\n"))

        # 条目
        page_items = self._page_items
        for i, item in enumerate(page_items):
            global_idx = self._page_start + i + 1  # 1-based 显示
            label = self._format_item(item, global_idx - 1)

            if i == self._selected_on_page:
                fragments.append(("class:paginated.cursor", " > "))
                fragments.append(("class:paginated.selected", f"{global_idx}. {label}\n"))
            else:
                fragments.append(("", "   "))
                fragments.append(("class:paginated.item", f"{global_idx}. {label}\n"))

        # 补齐空行（保持布局稳定）
        for _ in range(self._page_size - len(page_items)):
            fragments.append(("", "\n"))

        # 页码信息
        total = len(self._items)
        page_info = f"  第 {self._current_page + 1}/{self._total_pages} 页  (共 {total} 项)"
        fragments.append(("class:paginated.info", page_info + "\n"))
        fragments.append(("", "\n"))

        # 操作提示
        hint = "  [↑↓] 上下  [←→] 翻页  [Enter] 确认  [Esc] 取消"
        fragments.append(("class:paginated.hint", hint + "\n"))

        return fragments

    # ------------------------------------------------------------------
    # 键绑定
    # ------------------------------------------------------------------

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _up(event: E) -> None:
            if self._selected_on_page > 0:
                self._selected_on_page -= 1
            elif self._current_page > 0:
                self._current_page -= 1
                self._selected_on_page = len(self._page_items) - 1

        @kb.add("down")
        @kb.add("j")
        def _down(event: E) -> None:
            max_idx = len(self._page_items) - 1
            if self._selected_on_page < max_idx:
                self._selected_on_page += 1
            elif self._current_page < self._total_pages - 1:
                self._current_page += 1
                self._selected_on_page = 0

        @kb.add("left")
        @kb.add("pageup")
        def _left(event: E) -> None:
            if self._current_page > 0:
                self._current_page -= 1
                self._selected_on_page = min(
                    self._selected_on_page, len(self._page_items) - 1
                )

        @kb.add("right")
        @kb.add("pagedown")
        def _right(event: E) -> None:
            if self._current_page < self._total_pages - 1:
                self._current_page += 1
                self._selected_on_page = min(
                    self._selected_on_page, len(self._page_items) - 1
                )

        @kb.add("home")
        def _home(event: E) -> None:
            self._current_page = 0
            self._selected_on_page = 0

        @kb.add("end")
        def _end(event: E) -> None:
            self._current_page = self._total_pages - 1
            self._selected_on_page = len(self._page_items) - 1

        @kb.add("enter", eager=True)
        def _accept(event: E) -> None:
            event.app.exit(result=self._items[self._global_index])

        @kb.add("escape")
        @kb.add("q")
        def _cancel(event: E) -> None:
            event.app.exit(result=None)

        @kb.add("c-c")
        def _interrupt(event: E) -> None:
            event.app.exit(result=None)

        # 数字键快速跳转（1-9）
        for num in range(1, 10):

            def _make_handler(n: int) -> None:
                def _handler(event: E) -> None:
                    idx = n - 1
                    if idx < len(self._page_items):
                        self._selected_on_page = idx

                kb.add(str(n))(_handler)

            _make_handler(num)

        return kb

    # ------------------------------------------------------------------
    # Application 构建
    # ------------------------------------------------------------------

    def _create_application(self) -> Application[_T | None]:
        control = FormattedTextControl(
            self._get_formatted_text,
            focusable=True,
            key_bindings=self._build_key_bindings(),
        )
        window = Window(
            content=control,
            height=Dimension(
                preferred=self._page_size + 5  # 条目 + 标题 + 空行 + 页码 + 提示
            ),
        )
        layout = Layout(window)
        return Application(
            layout=layout,
            full_screen=False,
            style=self._style,
            mouse_support=False,
        )

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def prompt(self) -> _T | None:
        """同步选择。返回选中项，取消返回 None。"""
        return self._create_application().run()

    async def prompt_async(self) -> _T | None:
        """异步选择。返回选中项，取消返回 None。"""
        return await self._create_application().run_async()
