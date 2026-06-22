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
            description="开启/关闭语音交互模式。支持 --input-only、--output-only、--continuous",
            type=CommandType.SYSTEM,
        )

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if self._voice_runtime is None:
            if context.ui:
                context.ui.print("语音模块未启用。请在配置中设置 voice.enabled = true", style="warning")
            else:
                print("语音模块未启用。请在配置中设置 voice.enabled = true")
            return CommandResult(type=CommandResultType.NONE)

        # 解析参数
        continuous = "--continuous" in args
        input_only = "--input-only" in args
        output_only = "--output-only" in args

        # 互斥校验
        if input_only and output_only:
            if context.ui:
                context.ui.print("--input-only 和 --output-only 不能同时使用", style="warning")
            else:
                print("--input-only 和 --output-only 不能同时使用")
            return CommandResult(type=CommandResultType.NONE)

        try:
            if self._voice_runtime.is_running:
                await self._voice_runtime.stop()
                if context.ui:
                    context.ui.print("语音模式已关闭", style="muted")
                else:
                    print("语音模式已关闭")
            else:
                # 根据标志决定启用模式
                if input_only:
                    self._voice_runtime.set_mode(input_enabled=True, output_enabled=False)
                elif output_only:
                    self._voice_runtime.set_mode(input_enabled=False, output_enabled=True)
                else:
                    # 恢复默认（从配置）
                    self._voice_runtime.reset_mode()

                await self._voice_runtime.start(continuous=continuous)
                mode_desc = self._describe_mode(
                    self._voice_runtime.input_enabled,
                    self._voice_runtime.output_enabled,
                    continuous,
                )
                if context.ui:
                    context.ui.print(f"语音模式已开启 ({mode_desc})", style="success")
                else:
                    print(f"语音模式已开启 ({mode_desc})")

                # TTS 状态提示
                if self._voice_runtime.output_enabled:
                    playback_mode = getattr(self._voice_runtime, "tts_playback_mode", "unknown")
                    tts_ready = getattr(self._voice_runtime, "tts_available", False)
                    if context.ui:
                        context.ui.print(f"TTS 状态: ready={tts_ready}, playback={playback_mode}", style="muted")
                        if playback_mode == "none":
                            context.ui.print("TTS 播放不可用：未检测到可用 TTS client 或音频后端", style="warning")
                    else:
                        print(f"TTS 状态: ready={tts_ready}, playback={playback_mode}")
                else:
                    if context.ui:
                        context.ui.print("TTS 已禁用（仅语音输入模式）", style="muted")
                    else:
                        print("TTS 已禁用（仅语音输入模式）")

        except Exception as exc:
            if context.ui:
                context.ui.print(f"语音操作失败: {exc}", style="error")
            else:
                print(f"语音操作失败: {exc}")

        return CommandResult(type=CommandResultType.NONE)

    @staticmethod
    def _describe_mode(input_enabled: bool, output_enabled: bool, continuous: bool) -> str:
        """描述当前语音模式。"""
        parts = []
        if input_enabled:
            parts.append("STT")
        if output_enabled:
            parts.append("TTS")
        mode = "+".join(parts) if parts else "未知"
        if continuous:
            mode += " 连续对话"
        return mode
