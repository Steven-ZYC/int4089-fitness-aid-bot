"""Shared UI/video translations; raw device protocol identifiers stay unchanged."""
import json
from pathlib import Path
import re

MESSAGES = json.loads((Path(__file__).parent/'web/locales.json').read_text(encoding='utf-8'))
PATTERNS = [(key, re.compile('^'+re.sub(r'\\\{\d+\\\}', '(.*?)', re.escape(key))+'$'))
            for key in MESSAGES['zh-CN'] if '{0}' in key]


def translate(value, locale='zh-CN'):
    catalog = MESSAGES.get(locale, MESSAGES['zh-CN'])
    if value in catalog:
        return catalog[value]
    for key, pattern in PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            return re.sub(r'\{(\d+)\}', lambda m: translate(match[int(m[1])+1], locale), catalog[key])
    return value
