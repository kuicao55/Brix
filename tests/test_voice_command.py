"""/voice 命令测试。"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from capability.command.builtin.voice import VoiceCommand
from capability.command.base import CommandResultType


def test_voice_command_meta():
    """/voice 命令有正确的 meta 信息。"""
    cmd = VoiceCommand(voice_runtime=None)
    meta = cmd.meta
    assert meta.name == "voice"
    assert "语音" in meta.description or "voice" in meta.description.lower()


@pytest.mark.asyncio
async def test_voice_command_starts_voice():
    """/voice 命令启动语音模式，传入 continuous=False。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.tts_playback_mode = "pyaudio"

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("", ctx)

    mock_runtime.start.assert_called_once_with(continuous=False)
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_stops_voice():
    """/voice 命令停止已运行的语音模式。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = True
    mock_runtime.stop = AsyncMock()

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("", ctx)

    mock_runtime.stop.assert_called_once()
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_no_runtime():
    """/voice 命令在无 VoiceRuntime 时提示用户。"""
    cmd = VoiceCommand(voice_runtime=None)
    ctx = MagicMock()
    result = await cmd.execute("", ctx)

    assert result.type == CommandResultType.NONE
    ctx.ui.print.assert_called_once()
    assert "未启用" in str(ctx.ui.print.call_args)


@pytest.mark.asyncio
async def test_voice_command_continuous_flag():
    """/voice --continuous 启用连续对话模式，传入 continuous=True。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.tts_playback_mode = "afplay_pcm"

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("--continuous", ctx)

    mock_runtime.start.assert_called_once_with(continuous=True)
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_prints_playback_mode_warning():
    """/voice 启动后应提示 TTS 播放后端模式。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.tts_playback_mode = "none"

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    await cmd.execute("", ctx)

    warning_calls = [c for c in ctx.ui.print.call_args_list if "播放不可用" in str(c)]
    assert len(warning_calls) == 1


@pytest.mark.asyncio
async def test_voice_command_start_error():
    """/voice 命令在 start() 异常时打印错误而非崩溃。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock(side_effect=RuntimeError("麦克风权限被拒绝"))

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("", ctx)

    assert result.type == CommandResultType.NONE
    error_calls = [c for c in ctx.ui.print.call_args_list if "失败" in str(c)]
    assert len(error_calls) > 0


@pytest.mark.asyncio
async def test_voice_command_stop_error():
    """/voice 命令在 stop() 异常时打印错误而非崩溃。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = True
    mock_runtime.stop = AsyncMock(side_effect=RuntimeError("音频设备断开"))

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("", ctx)

    assert result.type == CommandResultType.NONE
    error_calls = [c for c in ctx.ui.print.call_args_list if "失败" in str(c)]
    assert len(error_calls) > 0


@pytest.mark.asyncio
async def test_voice_command_input_only():
    """/voice --input-only 仅启用语音输入。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.set_mode = MagicMock()
    mock_runtime.reset_mode = MagicMock()
    mock_runtime.input_enabled = True
    mock_runtime.output_enabled = False

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("--input-only", ctx)

    mock_runtime.set_mode.assert_called_once_with(input_enabled=True, output_enabled=False)
    mock_runtime.start.assert_called_once_with(continuous=False)
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_output_only():
    """/voice --output-only 仅启用语音输出。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.set_mode = MagicMock()
    mock_runtime.reset_mode = MagicMock()
    mock_runtime.input_enabled = False
    mock_runtime.output_enabled = True

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("--output-only", ctx)

    mock_runtime.set_mode.assert_called_once_with(input_enabled=False, output_enabled=True)
    mock_runtime.start.assert_called_once_with(continuous=False)
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_input_output_mutual_exclusivity():
    """/voice --input-only --output-only 互斥校验。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    result = await cmd.execute("--input-only --output-only", ctx)

    # 不应调用 start
    mock_runtime.start.assert_not_called()
    # 应打印互斥错误
    warning_calls = [c for c in ctx.ui.print.call_args_list if "不能同时" in str(c)]
    assert len(warning_calls) == 1
    assert result.type == CommandResultType.NONE


@pytest.mark.asyncio
async def test_voice_command_no_flags_resets_mode():
    """/voice 无参数时恢复默认模式。"""
    mock_runtime = MagicMock()
    mock_runtime.is_running = False
    mock_runtime.start = AsyncMock()
    mock_runtime.set_mode = MagicMock()
    mock_runtime.reset_mode = MagicMock()
    mock_runtime.input_enabled = True
    mock_runtime.output_enabled = True

    cmd = VoiceCommand(voice_runtime=mock_runtime)
    ctx = MagicMock()
    await cmd.execute("", ctx)

    mock_runtime.reset_mode.assert_called_once()
    mock_runtime.start.assert_called_once_with(continuous=False)
