#!/usr/bin/env python3
"""逐个测试正则表达式的每个范围。"""

import re


def test_ranges():
    """测试每个 Unicode 范围。"""
    test_char = '嘿'  # U+563F (22079)
    test_code = ord(test_char)

    print(f"测试字符: '{test_char}' U+{test_code:04X} ({test_code})")
    print()

    ranges = [
        ("emoticons", 0x1F600, 0x1F64F),
        ("symbols & pictographs", 0x1F300, 0x1F5FF),
        ("transport & map", 0x1F680, 0x1F6FF),
        ("flags", 0x1F1E0, 0x1F1FF),
        ("dingbats 1", 0x2702, 0x27B0),
        ("misc 1", 0x24C2, 0x1F251),
        ("supplemental", 0x1f926, 0x1f937),
        ("supplemental symbols", 0x1F900, 0x1F9FF),
        ("chess symbols", 0x1FA00, 0x1FA6F),
        ("symbols extended-A", 0x1FA70, 0x1FAFF),
        ("misc symbols", 0x2600, 0x26FF),
        ("dingbats 2", 0x2700, 0x27BF),
        ("variation selectors", 0xFE00, 0xFE0F),
        ("zero width joiner", 0x200D, 0x200D),
        ("star", 0x2B50, 0x2B50),
    ]

    print("范围检查:")
    for name, start, end in ranges:
        if start <= test_code <= end:
            print(f"  ✅ {name}: U+{start:04X}-U+{end:04X} - 匹配!")
        else:
            print(f"  ❌ {name}: U+{start:04X}-U+{end:04X} - 不匹配")

    print()
    print("问题诊断:")
    print(f"字符码点: {test_code} (0x{test_code:04X})")
    print(f"最大检查范围: 0x1F251 ({0x1F251})")
    print(f"字符是否在最大范围内: {test_code <= 0x1F251}")

    # 测试简化版本的正则表达式
    print()
    print("测试简化正则表达式:")
    simple_pattern = re.compile(
        r'[\U0001F600-\U0001F64F'  # emoticons
        r'\U0001F300-\U0001F5FF'  # symbols & pictographs
        r'\U0001F680-\U0001F6FF'  # transport & map
        r'\U0001F1E0-\U0001F1FF'  # flags
        r']+',
        re.UNICODE
    )

    if simple_pattern.match(test_char):
        print(f"  字符 '{test_char}' 被简化正则匹配")
    else:
        print(f"  字符 '{test_char}' 不被简化正则匹配")


if __name__ == "__main__":
    test_ranges()
