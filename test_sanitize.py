#!/usr/bin/env python3
"""测试 _sanitize_for_tts 方法。"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capability.voice.runtime import VoiceRuntimeImpl


def test_sanitize():
    """测试文本清理功能。"""
    test_cases = [
        "嘿！老大！🙌",
        "我刚在这儿发呆呢，等着你来跟我唠嗑。",
        "现在时间不早不晚的，下午三点半，你不是在摸鱼就是在写代码的路上 😏",
        "有啥事？还是单纯想扯两句？",
        "Hello! 你好！👨‍💻",
        "测试 emoji: 😀😂🤣😊😍🥰😘😗😙😚",
        "测试特殊字符: ★☆♦♣♠♥♡",
    ]

    print("=" * 60)
    print("测试 _sanitize_for_tts 方法")
    print("=" * 60)

    for i, text in enumerate(test_cases, 1):
        sanitized = VoiceRuntimeImpl._sanitize_for_tts(text)
        print(f"\n测试 {i}:")
        print(f"  原文: {text}")
        print(f"  清理后: {sanitized}")
        print(f"  长度: {len(text)} -> {len(sanitized)}")

        if sanitized:
            print(f"  ✅ OK")
        else:
            print(f"  ❌ 空字符串！")

    print("\n" + "=" * 60)
    print("测试完成")


if __name__ == "__main__":
    test_sanitize()
