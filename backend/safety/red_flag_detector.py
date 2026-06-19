import re

"""
红旗紧急检测
职责：检测用户的自杀意图或紧急医疗状况，触发安全中断
使用场景：每条用户消息进入系统时，先经过此检测，触发红旗则立即中断流程
"""

_SUICIDE_PATTERNS = [
    r'自杀',
    r'不想活[了啦]',
    r'死了算了',
    r'活不下去[了啦]?',
    r'结束.*生命',
    r'农药.*(?:喝|吃|吞|服)',
    r'(?:喝|吃|吞|服).*农药',
]

_EXCLUSION_TERMS = [
    '小说',
    '梵高',
    '遗书',
    '传记',
    '电影',
    '电视剧',
]


def detect_red_flag(state):
    messages = state.get('messages', [])
    content = ''
    for msg in reversed(messages):
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            break

    for term in _EXCLUSION_TERMS:
        if term in content:
            return {'red_flag_raised': False, 'red_flag_level': None}

    for pattern in _SUICIDE_PATTERNS:
        if re.search(pattern, content):
            return {'red_flag_raised': True, 'red_flag_level': 'CRITICAL'}

    return {'red_flag_raised': False, 'red_flag_level': None}
