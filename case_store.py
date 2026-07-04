from __future__ import annotations

from copy import deepcopy
import threading
import time
import uuid

from privacy_guard import redact_filename, redact_value
from storage_adapter import get_store_adapter, storage_info

STORE_ADAPTER = get_store_adapter()
LOCK = threading.RLock()
MAX_PAGE_LIMIT = 100

EMPTY_STORE = {
    "cases": {},
    "logs": {
        "user": [],
        "system": [],
        "ai": [],
        "observability": [],
    },
}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def read_store() -> dict:
    with LOCK:
        data = STORE_ADAPTER.read(EMPTY_STORE)
        data.setdefault("cases", {})
        data.setdefault("logs", {})
        data["logs"].setdefault("user", [])
        data["logs"].setdefault("system", [])
        data["logs"].setdefault("ai", [])
        data["logs"].setdefault("observability", [])
        return data


def write_store(data: dict) -> None:
    with LOCK:
        STORE_ADAPTER.write(data)


def update_store(mutator):
    with LOCK:
        data = read_store()
        result = mutator(data)
        write_store(data)
        return result


def public_case(case: dict | None) -> dict | None:
    return deepcopy(case) if case else None


def file_metadata(images: list[dict]) -> list[dict]:
    files = []
    for index, image in enumerate(images):
        name = redact_filename(image.get("filename") or f"evidence-image-{index + 1}")
        mime = image.get("mime") or "application/octet-stream"
        content = image.get("bytes") or b""
        files.append(
            {
                "name": name,
                "type": mime,
                "url": "",
                "size": len(content),
            }
        )
    return files


def create_case(images: list[dict] | None = None) -> dict:
    case_id = f"CASE-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
    timestamp = now_ms()
    case = {
        "id": case_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "status": "queued",
        "files": file_metadata(images or []),
        "ocr_result": None,
        "result": None,
        "raw_result": None,
        "trace": {
            "case_id": case_id,
            "steps": [],
        },
        "workflow_state": {
            "current_node": "",
            "attempt": 0,
            "last_error": "",
        },
    }

    def mutate(data):
        data["cases"][case_id] = case
        return public_case(case)

    return update_store(mutate)


def paginate(items: list[dict], limit: int = 50, offset: int = 0) -> dict:
    limit = max(1, min(MAX_PAGE_LIMIT, int(limit or 50)))
    offset = max(0, int(offset or 0))
    total = len(items)
    return {
        "items": items[offset : offset + limit],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }


def list_cases(limit: int = 50, offset: int = 0) -> dict:
    data = read_store()
    cases = [public_case(item) for item in data["cases"].values()]
    sorted_cases = sorted(cases, key=lambda item: item.get("created_at", 0), reverse=True)
    return paginate(sorted_cases, limit, offset)


def get_case(case_id: str) -> dict | None:
    data = read_store()
    return public_case(data["cases"].get(case_id))


def update_case(case_id: str, **fields) -> dict | None:
    def mutate(data):
        case = data["cases"].get(case_id)
        if not case:
            return None
        case.update(fields)
        case["updated_at"] = now_ms()
        return public_case(case)

    return update_store(mutate)


def attach_files(case_id: str, images: list[dict]) -> dict | None:
    def mutate(data):
        case = data["cases"].get(case_id)
        if not case:
            return None
        case["files"] = file_metadata(images)
        case["updated_at"] = now_ms()
        return public_case(case)

    return update_store(mutate)


def set_case_ocr(case_id: str, ocr_result: dict) -> dict | None:
    return update_case(case_id, ocr_result=redact_value(ocr_result))


def update_case_status(case_id: str, status: str) -> dict | None:
    return update_case(case_id, status=status)


def set_case_workflow_state(case_id: str, current_node: str = "", attempt: int = 0, last_error: str = "") -> dict | None:
    return update_case(
        case_id,
        workflow_state={
            "current_node": current_node,
            "attempt": attempt,
            "last_error": last_error,
        },
    )


def normalize_duration(duration_ms: int) -> int:
    if duration_ms <= 0:
        return 1
    return int(duration_ms)


def add_trace_step(
    case_id: str,
    step: str,
    status: str,
    output: str,
    duration_ms: int = 0,
    confidence: int | None = None,
    node_id: str = "",
    attempt: int = 1,
) -> None:
    trace_step = {
        "step": step,
        "status": status,
        "duration_ms": normalize_duration(duration_ms),
        "output": redact_value(output),
        "timestamp": now_ms(),
        "node_id": node_id,
        "attempt": attempt,
    }
    if confidence is not None:
        trace_step["confidence"] = confidence

    def mutate(data):
        case = data["cases"].get(case_id)
        if not case:
            return None
        trace = case.setdefault("trace", {"case_id": case_id, "steps": []})
        trace.setdefault("steps", []).append(trace_step)
        case["updated_at"] = now_ms()
        return None

    update_store(mutate)


def log_user(case_id: str, action: str, metadata: dict | None = None, user_id: str = "local-user") -> None:
    entry = {
        "type": "user",
        "user_id": user_id,
        "case_id": case_id,
        "action": action,
        "timestamp": now_ms(),
        "metadata": redact_value(metadata or {}),
    }
    append_log("user", entry)


def log_system(level: str, step: str, message: str, case_id: str = "", duration_ms: int = 0) -> None:
    entry = {
        "type": "system",
        "level": level,
        "step": step,
        "message": redact_value(message),
        "case_id": case_id,
        "duration_ms": normalize_duration(duration_ms) if case_id else int(duration_ms or 0),
        "timestamp": now_ms(),
    }
    append_log("system", entry)


def log_ai(case_id: str, input_prompt: str, model_output: str, reasoning: str, confidence: int) -> None:
    entry = {
        "type": "ai",
        "case_id": case_id,
        "input_prompt": redact_value(input_prompt),
        "model_output": redact_value(model_output),
        "reasoning": redact_value(reasoning),
        "confidence": confidence,
        "timestamp": now_ms(),
    }
    append_log("ai", entry)


def log_observability(case_id: str, event: dict) -> None:
    entry = {
        "type": "observability",
        "case_id": case_id,
        "trace_id": event.get("trace_id", ""),
        "observation_id": event.get("observation_id", ""),
        "node_id": event.get("node_id", ""),
        "name": event.get("name", ""),
        "status": event.get("status", ""),
        "duration_ms": event.get("duration_ms", 0),
        "external_delivery": event.get("external_delivery", "not_configured"),
        "timestamp": event.get("timestamp", now_ms()),
        "metadata": redact_value(event.get("metadata")),
        "input": redact_value(event.get("input")),
        "output": redact_value(event.get("output")),
        "error": redact_value(event.get("error")),
        "confidence": event.get("confidence"),
    }
    append_log("observability", entry)


def append_log(kind: str, entry: dict) -> None:
    def mutate(data):
        logs = data.setdefault("logs", {}).setdefault(kind, [])
        logs.append(entry)
        data["logs"][kind] = logs[-500:]
        return None

    update_store(mutate)


def list_logs(kind: str, case_id: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    data = read_store()
    logs = data["logs"].get(kind, [])
    if case_id:
        logs = [item for item in logs if item.get("case_id") == case_id]
    sorted_logs = sorted(deepcopy(logs), key=lambda item: item.get("timestamp", 0), reverse=True)
    return paginate(sorted_logs, limit, offset)


def judgement_text(value: str) -> str:
    return {
        "support_buyer": "不支持申诉",
        "support_seller": "支持申诉",
        "insufficient_evidence": "证据不足",
    }.get(value, "证据不足")


def summarize_result(result: dict) -> dict:
    return {
        "judgment": judgement_text(result.get("judgement_direction", "")),
        "score": int(result.get("appeal_win_score") or result.get("risk_score") or 0),
        "reasoning": result.get("score_explanation") or result.get("judgement_reason") or "",
        "key_evidence": result.get("evidence_order") or result.get("risk_reasons") or [],
    }


def mark_case_done(case_id: str, result: dict) -> dict | None:
    safe_result = redact_value(result)
    summary = summarize_result(safe_result)
    return update_case(case_id, status="done", result=summary, raw_result=safe_result)


def mark_case_failed(case_id: str, message: str) -> dict | None:
    return update_case(
        case_id,
        status="failed",
        result={
            "judgment": "璇佹嵁涓嶈冻",
            "score": 0,
            "reasoning": redact_value(message),
            "key_evidence": [],
        },
    )


def get_storage_info() -> dict:
    return storage_info()

