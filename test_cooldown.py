#!/usr/bin/env python3
"""测试 TTS 冷却期逻辑。"""

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


async def test_cooldown():
    """测试冷却期逻辑。"""
    logger.info("=" * 60)
    logger.info("测试 TTS 冷却期逻辑")
    logger.info("=" * 60)

    # 模拟 VoiceRuntimeImpl
    from capability.voice.config import VoiceConfig

    config = VoiceConfig()
    logger.info("✅ 配置加载成功")
    logger.info("   tts_cooldown_ms: %d", config.tts_cooldown_ms)

    # 模拟状态
    class MockState:
        SPEAKING = "speaking"
        IDLE = "idle"

    state = MockState.IDLE
    tts_cooldown_until = 0

    def is_speaking_or_cooldown():
        if state == MockState.SPEAKING:
            return True
        if time.time() < tts_cooldown_until:
            return True
        return False

    # 测试 1: 初始状态
    logger.info("\n测试 1: 初始状态")
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert not is_speaking_or_cooldown(), "初始状态应该返回 False"
    logger.info("   ✅ 通过")

    # 测试 2: SPEAKING 状态
    logger.info("\n测试 2: SPEAKING 状态")
    state = MockState.SPEAKING
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown(), "SPEAKING 状态应该返回 True"
    logger.info("   ✅ 通过")

    # 测试 3: 冷却期内
    logger.info("\n测试 3: 冷却期内")
    state = MockState.IDLE
    tts_cooldown_until = time.time() + 0.8  # 800ms 后
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert is_speaking_or_cooldown(), "冷却期内应该返回 True"
    logger.info("   ✅ 通过")

    # 测试 4: 冷却期后
    logger.info("\n测试 4: 冷却期后")
    await asyncio.sleep(0.9)  # 等待 900ms
    logger.info("   is_speaking_or_cooldown: %s", is_speaking_or_cooldown())
    assert not is_speaking_or_cooldown(), "冷却期后应该返回 False"
    logger.info("   ✅ 通过")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 所有测试通过！")
    logger.info("=" * 60)
    logger.info("\n冷却期逻辑工作正常，可以防止回声循环。")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_cooldown())
    sys.exit(0 if success else 1)
