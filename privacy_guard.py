from __future__ import annotations

from copy import deepcopy
import os
import re


REDACTION_ENABLED = os.getenv("PRIVACY_REDACTION_ENABLED", "1").strip() != "0"
MAX_REDACTED_TEXT_CHARS = int(os.getenv("PRIVACY_MAX_TEXT_CHARS", "12000"))

SENSITIVE_PATTERNS = [
    ("phone", re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")),
    ("id_card", re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("tracking_number", re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]{10,24}(?![A-Za-z0-9]))(?=[A-Za-z0-9]*\d)(?:YT|SF|JD|STO|YTO|ZTO|EMS|HTKY|DBL|JT|JNT)?[A-Za-z0-9]{10,24}(?![A-Za-z0-9])")),
    ("order_id", re.compile(r"(?i)(订单号|订单编号|order[_\s-]?id|order\s*no\.?)\s*[:：#]?\s*[A-Za-z0-9-]{6,32}")),
    ("address", re.compile(r"[\u4e00-\u9fa5]{2,}(?:省|市|区|县|镇|乡|街道|路|巷|弄|号楼|单元|室)[\u4e00-\u9fa50-9A-Za-z\-#（）()]{2,80}")),
]

TOKEN_MAP = {
    "phone": "[REDACTED_PHONE]",
    "id_card": "[REDACTED_ID]",
    "email": "[REDACTED_EMAIL]",
    "tracking_number": "[REDACTED_TRACKING]",
    "order_id": "[REDACTED_ORDER]",
    "address": "[REDACTED_ADDRESS]",
}


def redact_text(value: str) -> str:
    if not REDACTION_ENABLED or not value:
        return value
    text = str(value)
    for kind, pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(TOKEN_MAP[kind], text)
    if len(text) > MAX_REDACTED_TEXT_CHARS:
        return text[:MAX_REDACTED_TEXT_CHARS] + f"...[truncated {len(text) - MAX_REDACTED_TEXT_CHARS} chars]"
    return text


def redact_value(value):
    if not REDACTION_ENABLED:
        return deepcopy(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, bytes):
        return f"[REDACTED_BINARY:{len(value)} bytes]"
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"bytes", "content", "image", "image_bytes", "raw_image", "payload"}:
                redacted[key] = "[REDACTED_BINARY]"
            else:
                redacted[key] = redact_value(item)
        return redacted
    return redact_text(str(value))


def redact_filename(filename: str) -> str:
    return redact_text(filename or "")
