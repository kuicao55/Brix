"""模型名 StatusSlot：显示 side model 名称。"""

from __future__ import annotations

from plugins.status_bar import StatusBarState, StyledStatusSlot


class ModelSlot(StyledStatusSlot):
    """在状态栏显示 side model 名称。"""

    @property
    def name(self) -> str:
        return "model"

    def get_text(self, state: StatusBarState) -> str:
        return state.side_model or "side"

    def get_parts(self, state: StatusBarState) -> list[tuple[str, str]]:
        model = state.side_model or "side"
        return [("class:status-bar.model", " {} ".format(model))]
