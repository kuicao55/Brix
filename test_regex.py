#!/usr/bin/env python3
"""测试正则表达式对中文字符的影响。"""

import re


def test_regex():
    """测试正则表达式。"""
    # 测试文本
    text = "嘿！老大！🙌"
    print(f"原文: {text}")
    print(f"原文长度: {len(text)}")
    print()

    # 逐个字符分析
    print("逐个字符分析:")
    for i, char in enumerate(text):
        code_point = ord(char)
        print(f"  {i}: '{char}' U+{code_point:04X} ({code_point})")
    print()

    # 测试正则表达式
    emoji_pattern = re.compile(
        r'[\U0001F600-\U0001F64F'  # emoticons
        r'\U0001F300-\U0001F5FF'  # symbols & pictographs
        r'\U0001F680-\U0001F6FF'  # transport & map
        r'\U0001F1E0-\U0001F1FF'  # flags
        r'\U00002702-\U000027B0'
        r'\U000024C2-\U0001F251'
        r'\U0001f926-\U0001f937'
        r'\U0001F900-\U0001F9FF'  # supplemental symbols
        r'\U0001FA00-\U0001FA6F'  # chess symbols
        r'\U0001FA70-\U0001FAFF'  # symbols extended-A
        r'\U00002600-\U000026FF'  # misc symbols
        r'\U00002700-\U000027BF'  # dingbats
        r'\U0000FE00-\U0000FE0F'  # variation selectors
        r'\U0000200D'  # zero width joiner
        r'\U00002B50'  # star
        r'\U0000231A-\U0000231B'  # watch, hourglass
        r'\U000023E9-\U000023F3'  # media controls
        r'\U000023F8-\U000023FA'  # media controls
        r'\U000025AA-\U000025AB'  # squares
        r'\U000025B6'  # play button
        r'\U000025C0'  # reverse button
        r'\U000025FB-\U000025FE'  # squares
        r'\U00002614-\U00002615'  # umbrella, coffee
        r'\U00002648-\U00002653'  # zodiac
        r'\U0000267F'  # wheelchair
        r'\U00002693'  # anchor
        r'\U000026A1'  # lightning
        r'\U000026AA-\U000026AB'  # circles
        r'\U000026BD-\U000026BE'  # soccer, baseball
        r'\U000026C4-\U000026C5'  # snowman, sun
        r'\U000026CE'  # ophiuchus
        r'\U000026D4'  # no entry
        r'\U000026EA'  # church
        r'\U000026F2-\U000026F3'  # fountain, golf
        r'\U000026F5'  # sailboat
        r'\U000026FA'  # tent
        r'\U000026FD'  # fuel pump
        r'\U00002702'  # scissors
        r'\U00002705'  # check mark
        r'\U00002708-\U0000270D'  # various
        r'\U0000270F'  # pencil
        r'\U00002712'  # black nib
        r'\U00002714'  # check mark
        r'\U00002716'  # multiplication
        r'\U0000271D'  # latin cross
        r'\U00002721'  # star of david
        r'\U00002728'  # sparkles
        r'\U00002733-\U00002734'  # eight spoked asterisk
        r'\U00002744'  # snowflake
        r'\U00002747'  # sparkle
        r'\U0000274C'  # cross mark
        r'\U0000274E'  # cross mark
        r'\U00002753-\U00002755'  # question marks
        r'\U00002757'  # exclamation
        r'\U00002763-\U00002764'  # heart exclamation, heart
        r'\U00002795-\U00002797'  # plus, minus, divide
        r'\U000027A1'  # arrow
        r'\U000027B0'  # curly loop
        r']+',
        re.UNICODE
    )

    print("正则表达式匹配:")
    for i, char in enumerate(text):
        if emoji_pattern.match(char):
            print(f"  {i}: '{char}' U+{ord(char):04X} - 匹配 (会被删除)")
        else:
            print(f"  {i}: '{char}' U+{ord(char):04X} - 不匹配 (会保留)")
    print()

    # 测试清理
    result = emoji_pattern.sub('', text)
    print(f"清理后: '{result}'")
    print(f"清理后长度: {len(result)}")


if __name__ == "__main__":
    test_regex()
