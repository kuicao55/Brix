"""VoiceRuntime Protocol — CLI 只通过此接口与语音模块交互。"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class VoiceRuntime(Protocol):
    """语音运行时协议。

    启动后，语音文本通过 on_voice_input 注册的回调注入 Brix 主系统。
    状态变化通过 on_state_change 回调通知。
    """

    async def start(self, continuous: bool = False) -> None:
        """启动语音 pipeline（麦克风采集、VAD、STT 全链路）。"""
        ...

    async def stop(self) -> None:
        """停止语音 pipeline，释放音频资源。"""
        ...

    @property
    def is_running(self) -> bool:
        """当前是否在运行。"""
        ...

    @property
    def input_enabled(self) -> bool:
        """语音输入是否启用（STT）。"""
        ...

    @property
    def output_enabled(self) -> bool:
        """语音输出是否启用（TTS）。"""
        ...

    def set_mode(self, input_enabled: bool | None = None, output_enabled: bool | None = None) -> None:
        """设置语音输入/输出模式（None 表示不改变）。下次 start() 时生效。"""
        ...

    def reset_mode(self) -> None:
        """恢复到配置文件中的默认模式。"""
        ...

    def on_voice_input(self, callback: Callable[[str], None]) -> None:
        """注册回调：语音识别出最终文本后调用。文本已过 LLM Cleanup。"""
        ...

    def on_state_change(self, callback: Callable[[str], None]) -> None:
        """注册回调：状态变化（listening / speaking / idle / error）。"""
        ...

    def on_interim_text(self, callback: Callable[[str], None]) -> None:
        """注册回调：interim 转录结果（说话过程中实时更新）。"""
        ...

    def feed_response_text(self, text: str) -> None:
        """将 LLM 回复文本送入 TTS 合成。"""
        ...
