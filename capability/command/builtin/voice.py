"""/voice 命令 — 开启/关闭语音交互模式。"""

from __future__ import annotations

from capability.command.base import (
    Command,
    CommandContext,
    CommandMeta,
    CommandResult,
    CommandResultType,
    CommandType,
)
from capability.voice.protocol import VoiceRuntime


class VoiceCommand(Command):
    """/voice 命令 — 控制语音交互模式。"""

    def __init__(self, voice_runtime: VoiceRuntime | None = None) -> None:
        self._voice_runtime = voice_runtime

    @property
    def meta(self) -> CommandMeta:
        return CommandMeta(
            name="voice",
            description="开启/关闭语音交互模式 (voice input/output)",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if self._voice_runtime is None:
            context.console.print("[yellow]语音模块未启用。请在配置中设置 voice.enabled = true[/]")
            return CommandResult(type=CommandResultType.NONE)

        # 解析参数
        continuous = "--continuous" in args

        try:
            if self._voice_runtime.is_running:
                await self._voice_runtime.stop()
                context.console.print("[dim]语音模式已关闭[/]")
            else:
                await self._voice_runtime.start(continuous=continuous)
                mode = "连续对话" if continuous else "唤醒模式"
                context.console.print(f"[green]语音模式已开启 ({mode})[/]")
                playback_mode = getattr(self._voice_runtime, "tts_playback_mode", "unknown")
                tts_ready = getattr(self._voice_runtime, "tts_available", False)
                context.console.print(f"[dim]TTS 状态: ready={tts_ready}, playback={playback_mode}[/]")
                if playback_mode == "none":
                    context.console.print("[yellow]TTS 播放不可用：未检测到可用 TTS client 或音频后端[/]")
        except Exception as exc:
            context.console.print(f"[red]语音操作失败: {exc}[/]")

        return CommandResult(type=CommandResultType.NONE)
