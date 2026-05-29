#!/usr/bin/env python3
"""直接测试 API Key 和 CosyVoice 服务。"""

import asyncio
import json
import logging
import sys
import uuid

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

API_KEY = "sk-1a44d0b5f716416b886d074310a3a9e5"
WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


async def test_cosyvoice():
    """测试 CosyVoice 服务。"""
    logger.info("=" * 60)
    logger.info("测试 CosyVoice API Key 和服务")
    logger.info("=" * 60)
    logger.info("API Key: %s...", API_KEY[:15])
    logger.info("WebSocket URL: %s", WS_URL)
    logger.info("")

    task_id = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
        logger.info("1. 连接 WebSocket...")
        async with websockets.connect(
            WS_URL,
            additional_headers=headers,
            max_size=2**24,
            open_timeout=10,
        ) as ws:
            logger.info("   ✅ WebSocket 连接成功")

            logger.info("2. 发送 run-task...")
            run_msg = {
                "header": {
                    "action": "run-task",
                    "task_id": task_id,
                    "streaming": "duplex",
                },
                "payload": {
                    "task_group": "audio",
                    "task": "tts",
                    "function": "SpeechSynthesizer",
                    "model": "cosyvoice-v3-flash",
                    "parameters": {
                        "text_type": "PlainText",
                        "voice": "longanyang",
                        "format": "pcm",
                        "sample_rate": 24000,
                    },
                    "input": {},
                },
            }
            await ws.send(json.dumps(run_msg))
            logger.info("   ✅ run-task 已发送")

            logger.info("3. 等待 task-started...")
            resp = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(resp)
            event = data.get("header", {}).get("event", "")
            logger.info("   收到事件: %s", event)

            if event == "task-started":
                logger.info("   ✅ 任务已启动")

                logger.info("4. 发送测试文本...")
                continue_msg = {
                    "header": {
                        "action": "continue-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "input": {
                            "text": "你好",
                        },
                    },
                }
                await ws.send(json.dumps(continue_msg))
                logger.info("   ✅ 文本已发送")

                logger.info("5. 发送 finish-task...")
                finish_msg = {
                    "header": {
                        "action": "finish-task",
                        "task_id": task_id,
                        "streaming": "duplex",
                    },
                    "payload": {
                        "input": {},
                    },
                }
                await ws.send(json.dumps(finish_msg))
                logger.info("   ✅ finish-task 已发送")

                logger.info("6. 等待音频数据...")
                audio_chunks = 0
                audio_bytes = 0

                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    except asyncio.TimeoutError:
                        logger.warning("   ⚠️  等待超时")
                        break

                    if isinstance(msg, bytes):
                        audio_chunks += 1
                        audio_bytes += len(msg)
                        if audio_chunks <= 2:
                            logger.info("   收到音频 chunk %d: %d bytes", audio_chunks, len(msg))
                    else:
                        data = json.loads(msg)
                        event = data.get("header", {}).get("event", "")

                        if event == "task-finished":
                            logger.info("   ✅ 任务完成")
                            break
                        elif event == "task-failed":
                            error_code = data.get("header", {}).get("error_code", "")
                            error_msg = data.get("header", {}).get("error_message", "")
                            logger.error("   ❌ 任务失败: %s - %s", error_code, error_msg)
                            return False
                        elif event == "result-generated":
                            continue

                logger.info("")
                logger.info("=" * 60)
                logger.info("测试结果")
                logger.info("=" * 60)
                logger.info("音频 chunks: %d", audio_chunks)
                logger.info("音频 bytes: %d", audio_bytes)

                if audio_chunks > 0:
                    logger.info("✅ CosyVoice 服务正常工作！")
                    return True
                else:
                    logger.error("❌ 未收到音频数据")
                    return False

            elif event == "task-failed":
                error_code = data.get("header", {}).get("error_code", "")
                error_msg = data.get("header", {}).get("error_message", "")
                logger.error("   ❌ 任务启动失败: %s - %s", error_code, error_msg)
                return False
            else:
                logger.error("   ❌ 未知事件: %s", event)
                return False

    except websockets.exceptions.InvalidStatusCode as exc:
        logger.error("❌ WebSocket 连接被拒绝: %s", exc)
        logger.error("   可能原因: API Key 无效或没有权限")
        return False
    except Exception as exc:
        logger.error("❌ 测试失败: %s", exc, exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(test_cosyvoice())
    if success:
        logger.info("")
        logger.info("🎉 API Key 和 CosyVoice 服务都正常！")
        logger.info("问题可能在 Brix 的 TTS 流程中，而不是 API 本身。")
    else:
        logger.info("")
        logger.info("❌ API Key 或 CosyVoice 服务有问题。")
        logger.info("请检查：")
        logger.info("1. API Key 是否有权限访问 CosyVoice")
        logger.info("2. 账户余额是否充足")
        logger.info("3. CosyVoice 服务是否已开通")

    sys.exit(0 if success else 1)
