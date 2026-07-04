from __future__ import annotations

import json
import os
import time
import uuid

from case_store import log_observability
from privacy_guard import redact_value

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime
    requests = None


OBSERVABILITY_ENABLED = os.getenv("OBSERVABILITY_ENABLED", "1").strip() != "0"
OBSERVABILITY_WEBHOOK_URL = os.getenv("OBSERVABILITY_WEBHOOK_URL", "").strip()
OBSERVABILITY_WEBHOOK_TOKEN = os.getenv("OBSERVABILITY_WEBHOOK_TOKEN", "").strip()
OBSERVABILITY_TIMEOUT_SECONDS = int(os.getenv("OBSERVABILITY_TIMEOUT_SECONDS", "8"))
OBSERVABILITY_MAX_FIELD_CHARS = int(os.getenv("OBSERVABILITY_MAX_FIELD_CHARS", "4000"))


def new_trace_id(case_id: str) -> str:
    return f"trace-{case_id}-{uuid.uuid4().hex[:10]}"


def new_observation_id(node_id: str) -> str:
    return f"obs-{node_id}-{uuid.uuid4().hex[:10]}"


def record_observation(
    case_id: str,
    trace_id: str,
    node_id: str,
    name: str,
    status: str,
    duration_ms: int = 0,
    input_payload=None,
    output_payload=None,
    error: str = "",
    metadata: dict | None = None,
    confidence: int | None = None,
) -> dict:
    if not OBSERVABILITY_ENABLED:
        return {}

    event = {
        "type": "observation",
        "trace_id": trace_id,
        "observation_id": new_observation_id(node_id),
        "case_id": case_id,
        "node_id": node_id,
        "name": name,
        "status": status,
        "duration_ms": max(1, int(duration_ms or 0)),
        "input": compact_value(redact_value(input_payload)),
        "output": compact_value(redact_value(output_payload)),
        "error": compact_value(redact_value(error)),
        "metadata": compact_value(redact_value(metadata or {})),
        "confidence": confidence,
        "timestamp": int(time.time() * 1000),
        "external_delivery": "not_configured",
    }

    if OBSERVABILITY_WEBHOOK_URL:
        event["external_delivery"] = deliver_event(event)

    log_observability(case_id, event)
    return event


def record_trace_summary(case_id: str, trace_id: str, status: str, duration_ms: int, metadata: dict | None = None) -> dict:
    return record_observation(
        case_id=case_id,
        trace_id=trace_id,
        node_id="workflow",
        name="工作流汇总",
        status=status,
        duration_ms=duration_ms,
        input_payload={},
        output_payload=metadata or {},
        metadata={"kind": "trace_summary"},
    )


def deliver_event(event: dict) -> str:
    if requests is None:
        return "failed:requests_missing"
    headers = {"Content-Type": "application/json"}
    if OBSERVABILITY_WEBHOOK_TOKEN:
        headers["Authorization"] = f"Bearer {OBSERVABILITY_WEBHOOK_TOKEN}"
    try:
        response = requests.post(OBSERVABILITY_WEBHOOK_URL, json=event, headers=headers, timeout=OBSERVABILITY_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            return f"failed:http_{response.status_code}"
        return "delivered"
    except Exception as exc:  # pragma: no cover - network dependent
        return f"failed:{type(exc).__name__}"


def compact_value(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return trim_string(str(value)) if isinstance(value, str) else value
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return trim_string(text)


def trim_string(value: str) -> str:
    if len(value) <= OBSERVABILITY_MAX_FIELD_CHARS:
        return value
    return value[:OBSERVABILITY_MAX_FIELD_CHARS] + f"...[truncated {len(value) - OBSERVABILITY_MAX_FIELD_CHARS} chars]"
