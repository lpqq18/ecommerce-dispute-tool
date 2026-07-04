from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from case_store import add_trace_step, log_system, set_case_workflow_state, update_case_status
from observability import new_trace_id, record_observation, record_trace_summary


@dataclass
class WorkflowNode:
    node_id: str
    label: str
    runner: Callable[[dict], dict]
    max_retries: int = 0


class WorkflowNodeError(RuntimeError):
    pass


def run_workflow(case_id: str, nodes: list[WorkflowNode], state: dict) -> dict:
    started = time.perf_counter()
    trace_id = state.get("observability_trace_id") or new_trace_id(case_id)
    state["observability_trace_id"] = trace_id
    update_case_status(case_id, "processing")
    set_case_workflow_state(case_id, current_node="workflow_start", attempt=0, last_error="")

    try:
        for node in nodes:
            state = run_node(case_id, node, state, trace_id)
    except Exception:
        record_trace_summary(case_id, trace_id, "failed", int((time.perf_counter() - started) * 1000), {"current_state_keys": sorted(state.keys())})
        raise

    set_case_workflow_state(case_id, current_node="workflow_done", attempt=0, last_error="")
    record_trace_summary(case_id, trace_id, "success", int((time.perf_counter() - started) * 1000), {"current_state_keys": sorted(state.keys())})
    return state


def run_node(case_id: str, node: WorkflowNode, state: dict, trace_id: str | None = None) -> dict:
    last_error = ""
    max_attempts = node.max_retries + 1
    trace_id = trace_id or state.get("observability_trace_id") or new_trace_id(case_id)

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        set_case_workflow_state(case_id, current_node=node.node_id, attempt=attempt, last_error=last_error)
        log_system("info", f"{node.node_id}_start", f"{node.label}开始执行", case_id)
        try:
            output = node.runner(state) or {}
            duration_ms = int((time.perf_counter() - started) * 1000)
            state.update(output.get("state") or {})
            add_trace_step(
                case_id,
                node.label,
                "success",
                output.get("message") or f"{node.label}完成",
                duration_ms,
                output.get("confidence"),
                node_id=node.node_id,
                attempt=attempt,
            )
            log_system("info", node.node_id, output.get("message") or f"{node.label}完成", case_id, duration_ms)
            record_observation(
                case_id=case_id,
                trace_id=trace_id,
                node_id=node.node_id,
                name=node.label,
                status="success",
                duration_ms=duration_ms,
                input_payload=node_input_snapshot(state),
                output_payload=output.get("message") or output.get("state") or {},
                metadata={"attempt": attempt, "max_attempts": max_attempts},
                confidence=output.get("confidence"),
            )
            return state
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            last_error = str(exc)
            add_trace_step(
                case_id,
                node.label,
                "failed",
                last_error,
                duration_ms,
                node_id=node.node_id,
                attempt=attempt,
            )
            log_system("error", node.node_id, last_error, case_id, duration_ms)
            record_observation(
                case_id=case_id,
                trace_id=trace_id,
                node_id=node.node_id,
                name=node.label,
                status="failed",
                duration_ms=duration_ms,
                input_payload=node_input_snapshot(state),
                output_payload={},
                error=last_error,
                metadata={"attempt": attempt, "max_attempts": max_attempts},
            )
            if attempt < max_attempts:
                update_case_status(case_id, "retrying")
                set_case_workflow_state(case_id, current_node=node.node_id, attempt=attempt, last_error=last_error)
                log_system("warn", f"{node.node_id}_retry", f"{node.label}失败，准备第 {attempt + 1} 次重试", case_id)
                continue
            set_case_workflow_state(case_id, current_node=node.node_id, attempt=attempt, last_error=last_error)
            raise WorkflowNodeError(f"{node.label}失败：{last_error}") from exc

    raise WorkflowNodeError(f"{node.label}失败：{last_error}")


def node_input_snapshot(state: dict) -> dict:
    return {
        "state_keys": sorted(state.keys()),
        "image_count": len(state.get("images") or []),
        "has_ocr_result": bool(state.get("ocr_result")),
        "has_result": bool(state.get("result")),
    }
