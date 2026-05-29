#!/usr/bin/env python3
"""测试 TTS 功能的独立脚本。"""

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


async def test_tts():
    """测试 TTS 合成和播放。"""
    logger.info("=" * 60)
    logger.info("TTS 功能测试")
    logger.info("=" * 60)

    # 1. 检查 API Key
    api_key = os.environ.get("ALI_API_KEY", "")
    if not api_key:
        logger.error("❌ ALI_API_KEY 环境变量未设置")
        return False
    logger.info("✅ ALI_API_KEY 已设置: %s...", api_key[:10])

    # 2. 创建 TTS 客户端
    try:
        from capability.voice.tts.cosyvoice_client import CosyVoiceClient
        tts_client = CosyVoiceClient(
            api_key=api_key,
            model="cosyvoice-v3-flash",
            voice="longanyang",  # v3 音色
            sample_rate=24000,
        )
        logger.info("✅ TTS 客户端创建成功")
    except Exception as exc:
        logger.error("❌ TTS 客户端创建失败: %s", exc)
        return False

    # 3. 测试合成
    test_text = "你好，我是 Brix 语音助手。"
    logger.info("🔊 开始合成测试文本: '%s'", test_text)

    try:
        chunk_count = 0
        byte_count = 0
        async for chunk in tts_client.synthesize(test_text):
            if chunk:
                chunk_count += 1
                byte_count += len(chunk)
                if chunk_count <= 3:
                    logger.info("  收到音频 chunk %d: %d bytes", chunk_count, len(chunk))

        if chunk_count == 0:
            logger.error("❌ TTS 未产生任何音频数据")
            return False

        logger.info("✅ TTS 合成成功: %d chunks, %d bytes", chunk_count, byte_count)

    except Exception as exc:
        logger.error("❌ TTS 合成失败: %s", exc, exc_info=True)
        return False

    # 4. 测试播放（可选）
    logger.info("")
    logger.info("是否测试音频播放？(需要 PyAudio)")
    logger.info("运行: python -c \"import pyaudio; print('PyAudio OK')\" 检查安装")

    try:
        import pyaudio
        logger.info("✅ PyAudio 已安装")

        # 创建简单的播放测试
        logger.info("🔊 尝试播放测试音...")
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True,
        )

        # 生成简单的正弦波测试音
        import numpy as np
        duration = 0.5  # 0.5秒
        frequency = 440  # A4 音符
        t = np.linspace(0, duration, int(24000 * duration), endpoint=False)
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
    logger.info("TTS 测试完成")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_tts())
    sys.exit(0 if success else 1)
