import re

"""
PII检测与脱敏
职责：检测并脱敏用户输入中的个人身份信息（PII）
使用场景：用户输入文本后，先经过此函数脱敏再进入Agent处理
"""

_ID_CARD_PATTERN = re.compile(
    r'(?<!\d)'
    r'[1-9]\d{5}'
    r'(?:19|20)\d{2}'
    r'(?:0[1-9]|1[0-2])'
    r'(?:0[1-9]|[12]\d|3[01])'
    r'\d{3}'
    r'[\dXx]'
    r'(?!\d)'
)


def mask_pii(text):
    return _ID_CARD_PATTERN.sub('***', text)
