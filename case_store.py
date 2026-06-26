from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import threading
import time
import uuid


DATA_DIR = Path(os.getenv("CASE_DATA_DIR") or ("/tmp/ecommerce-dispute-tool" if os.getenv("VERCEL") else "data"))
STORE_PATH = DATA_DIR / "case_store.json"
LOCK = threading.RLock()
MAX_PAGE_LIMIT = 100

EMPTY_STORE = {
    "cases": {},
    "logs": {
        "user": [],
        "system": [],
        "ai": [],
    },
}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def read_store() -> dict:
    with LOCK:
        if not STORE_PATH.exists():
            return deepcopy(EMPTY_STORE)
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(EMPTY_STORE)
        data.setdefault("cases", {})
        data.setdefault("logs", {})
        data["logs"].setdefault("user", [])
        data["logs"].setdefault("system", [])
        data["logs"].setdefault("ai", [])
        return data


def write_store(data: dict) -> None:
    with LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        name = image.get("filename") or f"证据截图 {index + 1}"
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
        "status": "processing",
        "files": file_metadata(images or []),
        "result": None,
        "raw_result": None,
        "trace": {
            "case_id": case_id,
            "steps": [],
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


def normalize_duration(duration_ms: int) -> int:
    if duration_ms <= 0:
        return 1
    return int(duration_ms)


def add_trace_step(case_id: str, step: str, status: str, output: str, duration_ms: int = 0, confidence: int | None = None) -> None:
    trace_step = {
        "step": step,
        "status": status,
        "duration_ms": normalize_duration(duration_ms),
        "output": output,
        "timestamp": now_ms(),
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
        "metadata": metadata or {},
    }
    append_log("user", entry)


def log_system(level: str, step: str, message: str, case_id: str = "", duration_ms: int = 0) -> None:
    entry = {
        "type": "system",
        "level": level,
        "step": step,
        "message": message,
        "case_id": case_id,
        "duration_ms": normalize_duration(duration_ms) if case_id else int(duration_ms or 0),
        "timestamp": now_ms(),
    }
    append_log("system", entry)


def log_ai(case_id: str, input_prompt: str, model_output: str, reasoning: str, confidence: int) -> None:
    entry = {
        "type": "ai",
        "case_id": case_id,
        "input_prompt": input_prompt,
        "model_output": model_output,
        "reasoning": reasoning,
        "confidence": confidence,
        "timestamp": now_ms(),
    }
    append_log("ai", entry)


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
    summary = summarize_result(result)
    return update_case(case_id, status="done", result=summary, raw_result=result)


def mark_case_failed(case_id: str, message: str) -> dict | None:
    return update_case(
        case_id,
        status="failed",
        result={
            "judgment": "证据不足",
            "score": 0,
            "reasoning": message,
            "key_evidence": [],
        },
    )
