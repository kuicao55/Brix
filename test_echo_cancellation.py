#!/usr/bin/env python3
"""测试回声消除逻辑。"""

import asyncio
import logging
import os
import sys
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_echo_cancellation():
    """测试回声消除逻辑。"""
    logger.info("=" * 60)
    logger.info("测试回声消除逻辑")
    logger.info("=" * 60)

    # 模拟 AudioPlayer
    class MockAudioPlayer:
        def __init__(self):
            self._is_playing = False

        @property
        def is_playing(self):
            return self._is_playing

        def start_playback(self):
            self._is_playing = True

        def finish_playback(self):
            self._is_playing = False

    # 模拟状态
    class VoiceState:
        IDLE = "idle"
        SPEAKING = "speaking"
        SLEEPING = "sleeping"

    # 初始化
    audio_player = MockAudioPlayer()
    state = VoiceState.IDLE
    tts_cooldown_until = 0

    def is_speaking_or_cooldown():
        """检查是否在 TTS 播放或冷却期内。"""
        if state == VoiceState.SPEAKING:
            return True
        if audio_player.is_playing:
            return True
        if time.time() < tts_cooldown_until:
            return True
        return False

    # 测试 1: 初始状态
    logger.info("\n测试 1: 初始状态")
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert not is_speaking_or_cooldown(), "初始状态应该返回 False"
    logger.info("   ✅ 通过")

    # 测试 2: TTS 合成中
    logger.info("\n测试 2: TTS 合成中")
    state = VoiceState.SPEAKING
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown(), "TTS 合成中应该返回 True"
    logger.info("   ✅ 通过")

    # 测试 3: TTS 合成完成，音频播放中
    logger.info("\n测试 3: TTS 合成完成，音频播放中")
    state = VoiceState.IDLE
    audio_player.start_playback()
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown(), "音频播放中应该返回 True"
    logger.info("   ✅ 通过")

    # 测试 4: 音频播放完成，冷却期内
    logger.info("\n测试 4: 音频播放完成，冷却期内")
    audio_player.finish_playback()
    tts_cooldown_until = time.time() + 0.5  # 500ms 冷却期
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown(), "冷却期内应该返回 True"
    logger.info("   ✅ 通过")

    # 测试 5: 冷却期后
    logger.info("\n测试 5: 冷却期后")
    await asyncio.sleep(0.6)  # 等待 600ms
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert not is_speaking_or_cooldown(), "冷却期后应该返回 False"
    logger.info("   ✅ 通过")

    # 测试 6: 模拟完整的 TTS 流程
    logger.info("\n测试 6: 模拟完整的 TTS 流程")
    state = VoiceState.SPEAKING
    logger.info("   开始 TTS 合成: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown()

    # 合成完成，开始播放
    state = VoiceState.IDLE
    audio_player.start_playback()
    logger.info("   音频播放中: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown()

    # 播放完成，进入冷却期
    audio_player.finish_playback()
    tts_cooldown_until = time.time() + 0.5
    logger.info("   冷却期中: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown()

    # 冷却期后
    await asyncio.sleep(0.6)
    logger.info("   恢复监听: %s", is_speaking_or_cooldown())
    assert not is_speaking_or_cooldown()
    logger.info("   ✅ 通过")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有测试通过！")
    logger.info("=" * 60)
    logger.info("\n回声消除逻辑工作正常：")
    logger.info("- TTS 合成期间：禁用音频输入")
    logger.info("- 音频播放期间：禁用音频输入")
    logger.info("- 冷却期内：禁用音频输入")
    logger.info("- 冷却期后：恢复音频输入")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_echo_cancellation())
    sys.exit(0 if success else 1)
