#!/usr/bin/env python3
"""测试完整的语音流程。"""

import asyncio
import logging
import os
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_voice_flow():
    """测试完整的语音流程。"""
    logger.info("=" * 60)
    logger.info("测试完整语音流程")
    logger.info("=" * 60)

    # 1. 加载配置
    from config.loader import load_config
    config = load_config()
    logger.info("✅ 配置加载成功")

    # 2. 创建 VoiceConfig
    from capability.voice.config import VoiceConfig
    voice_cfg = VoiceConfig.from_dict(config)
    logger.info("✅ VoiceConfig 创建成功")
    logger.info("   TTS 模型: %s", voice_cfg.tts_model)
    logger.info("   TTS 音色: %s", voice_cfg.tts_voice)

    # 3. 创建 TTS 客户端
    from capability.voice.tts.cosyvoice_client import create_cosyvoice_client
    tts_client = create_cosyvoice_client(config)

    if tts_client is None:
        logger.error("❌ TTS 客户端创建失败")
        return False

    logger.info("✅ TTS 客户端创建成功")

    # 4. 测试文本清理
    from capability.voice.runtime import VoiceRuntimeImpl
    test_text = "嘿！老大！🙌 我刚在这儿发呆呢，等着你来跟你唠嗑。"
    sanitized = VoiceRuntimeImpl._sanitize_for_tts(test_text)
    logger.info("✅ 文本清理测试:")
    logger.info("   原文: %s", test_text)
    logger.info("   清理后: %s", sanitized)

    if not sanitized:
        logger.error("❌ 文本清理后为空")
        return False

    # 5. 测试 TTS 合成
    logger.info("🔊 测试 TTS 合成...")
    try:
        chunk_count = 0
        byte_count = 0
        async for chunk in tts_client.synthesize(sanitized):
            if chunk:
                chunk_count += 1
                byte_count += len(chunk)

        if chunk_count == 0:
            logger.error("❌ TTS 未产生音频")
            return False

        logger.info("✅ TTS 合成成功: %d chunks, %d bytes", chunk_count, byte_count)

    except Exception as exc:
        logger.error("❌ TTS 合成失败: %s", exc, exc_info=True)
        return False

    # 6. 测试音频播放
    logger.info("🔊 测试音频播放...")
    try:
        import pyaudio
        import numpy as np

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=voice_cfg.tts_sample_rate,
            output=True,
        )

        # 生成测试音
        duration = 0.3
        frequency = 440
        t = np.linspace(0, duration, int(voice_cfg.tts_sample_rate * duration), endpoint=False)
        audio_data = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)

        stream.write(audio_data.tobytes())
        stream.stop_stream()
        stream.close()
        pa.terminate()
        logger.info("✅ 音频播放测试成功")

    except ImportError:
        logger.warning("⚠️  PyAudio 未安装，跳过播放测试")
    except Exception as exc:
        logger.warning("⚠️  音频播放测试失败: %s", exc)

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ 所有测试通过！")
    logger.info("=" * 60)
    logger.info("")
    logger.info("现在可以运行 'brix' 并使用 '/voice' 命令测试语音功能了。")
    logger.info("如果仍有问题，请运行: BRIX_LOG_LEVEL=INFO brix")

    return True


if __name__ == "__main__":
    success = asyncio.run(test_voice_flow())
    sys.exit(0 if success else 1)
