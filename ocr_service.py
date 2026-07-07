from __future__ import annotations

import base64
import os
import tempfile
import time
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime
    requests = None


OCR_PROVIDER = os.getenv("OCR_PROVIDER", "auto").strip().lower()
OCR_API_URL = os.getenv("OCR_API_URL", "").strip()
OCR_API_TOKEN = os.getenv("OCR_API_TOKEN", "").strip()
BAIDU_OCR_API_KEY = os.getenv("BAIDU_OCR_API_KEY", "").strip()
BAIDU_OCR_SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY", "").strip()
BAIDU_OCR_ENDPOINT = os.getenv("BAIDU_OCR_ENDPOINT", "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic").strip()
OCR_TIMEOUT_SECONDS = int(os.getenv("OCR_TIMEOUT_SECONDS", "60"))
OCR_REQUIRE_REAL = os.getenv("OCR_REQUIRE_REAL", "0").strip() == "1"
OCR_MIN_TEXT_CHARS = int(os.getenv("OCR_MIN_TEXT_CHARS", "0"))

_PADDLE_ENGINE = None
_BAIDU_TOKEN = {"value": "", "expires_at": 0}


def run_ocr(images: list[dict]) -> dict:
    started = time.perf_counter()
    warnings = []
    provider = resolve_provider()

    try:
        if provider == "external":
            result = run_external_ocr(images)
        elif provider == "baidu":
            result = run_baidu_ocr(images)
        elif provider == "paddle":
            result = run_paddle_ocr(images)
        else:
            result = run_demo_ocr(images, "未配置 OCR_API_URL，且未启用本地 PaddleOCR。")
    except Exception as exc:
        if OCR_PROVIDER in ("external", "baidu", "paddle"):
            raise RuntimeError(f"OCR 解析失败：{exc}") from exc
        warnings.append(f"OCR 自动模式未能启用真实识别：{exc}")
        result = run_demo_ocr(images, warnings[-1])

    result.setdefault("warnings", [])
    result["warnings"].extend(warnings)
    result["duration_ms"] = max(1, int((time.perf_counter() - started) * 1000))
    result["summary"] = summarize_ocr(result)
    result["text"] = "\n".join(item.get("text", "") for item in result.get("images", []) if item.get("text")).strip()
    validate_ocr_result(result)
    return result


def resolve_provider() -> str:
    if OCR_PROVIDER in ("external", "baidu", "paddle", "demo"):
        return OCR_PROVIDER
    if BAIDU_OCR_API_KEY and BAIDU_OCR_SECRET_KEY:
        return "baidu"
    if OCR_API_URL:
        return "external"
    return "demo"


def validate_ocr_result(result: dict) -> None:
    text_length = len(result.get("text") or "")
    if OCR_REQUIRE_REAL and not result.get("real_ocr"):
        raise RuntimeError("OCR_REQUIRE_REAL=1, but real OCR is not configured or did not run.")
    if OCR_REQUIRE_REAL and OCR_MIN_TEXT_CHARS and text_length < OCR_MIN_TEXT_CHARS:
        raise RuntimeError(f"OCR text is too short: {text_length} chars, expected at least {OCR_MIN_TEXT_CHARS}.")
    if OCR_MIN_TEXT_CHARS and text_length < OCR_MIN_TEXT_CHARS:
        result.setdefault("warnings", []).append(f"OCR text is short: {text_length}/{OCR_MIN_TEXT_CHARS} chars.")


def run_external_ocr(images: list[dict]) -> dict:
    if requests is None:
        raise RuntimeError("当前 Python 环境缺少 requests，无法调用外部 OCR 服务。")
    if not OCR_API_URL:
        raise RuntimeError("未配置 OCR_API_URL。")

    files = []
    try:
        for index, image in enumerate(images):
            filename = image.get("filename") or f"image-{index + 1}.jpg"
            files.append(("images", (filename, image.get("bytes") or b"", image.get("mime") or "application/octet-stream")))
        headers = {}
        if OCR_API_TOKEN:
            headers["Authorization"] = f"Bearer {OCR_API_TOKEN}"
        response = requests.post(OCR_API_URL, files=files, headers=headers, timeout=OCR_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            raise RuntimeError(f"外部 OCR 服务返回 {response.status_code}: {response.text[:500]}")
        payload = response.json()
    finally:
        files.clear()

    return normalize_ocr_payload(payload, provider="external")


def get_baidu_access_token() -> str:
    if not BAIDU_OCR_API_KEY or not BAIDU_OCR_SECRET_KEY:
        raise RuntimeError("未配置 BAIDU_OCR_API_KEY 或 BAIDU_OCR_SECRET_KEY。")
    if _BAIDU_TOKEN["value"] and time.time() < _BAIDU_TOKEN["expires_at"] - 300:
        return _BAIDU_TOKEN["value"]
    response = requests.post(
        "https://aip.baidubce.com/oauth/2.0/token",
        params={
            "grant_type": "client_credentials",
            "client_id": BAIDU_OCR_API_KEY,
            "client_secret": BAIDU_OCR_SECRET_KEY,
        },
        timeout=OCR_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"百度 OCR token 获取失败 {response.status_code}: {response.text[:500]}")
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"百度 OCR token 响应缺少 access_token: {payload}")
    _BAIDU_TOKEN["value"] = token
    _BAIDU_TOKEN["expires_at"] = time.time() + int(payload.get("expires_in") or 2592000)
    return token


def run_baidu_ocr(images: list[dict]) -> dict:
    if requests is None:
        raise RuntimeError("当前 Python 环境缺少 requests，无法调用百度 OCR 服务。")

    token = get_baidu_access_token()
    normalized_images = []
    warnings = []
    for index, image in enumerate(images):
        filename = image.get("filename") or f"image-{index + 1}.jpg"
        response = requests.post(
            BAIDU_OCR_ENDPOINT,
            params={"access_token": token},
            data={
                "image": base64.b64encode(image.get("bytes") or b"").decode("ascii"),
                "language_type": "CHN_ENG",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=OCR_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"百度 OCR 服务返回 {response.status_code}: {response.text[:500]}")
        payload = response.json()
        if payload.get("error_code"):
            raise RuntimeError(f"百度 OCR 服务错误 {payload.get('error_code')}: {payload.get('error_msg')}")
        words = payload.get("words_result") or []
        blocks = []
        for item in words:
            probability = item.get("probability") if isinstance(item, dict) else None
            blocks.append(
                normalize_block(
                    {
                        "text": item.get("words") or "",
                        "confidence": probability.get("average") if isinstance(probability, dict) else None,
                        "bbox": item.get("location") or [],
                    }
                )
            )
        if not blocks:
            warnings.append(f"{filename} 未识别到文本。")
        normalized_images.append(
            {
                "filename": filename,
                "mime": image.get("mime") or "",
                "blocks": blocks,
                "block_count": len(blocks),
                "text": "\n".join(block["text"] for block in blocks if block.get("text")),
            }
        )

    return {"provider": "baidu", "real_ocr": True, "images": normalized_images, "warnings": warnings}


def run_paddle_ocr(images: list[dict]) -> dict:
    global _PADDLE_ENGINE
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("未安装 paddleocr。请先安装 PaddleOCR，或改用 OCR_API_URL 外部服务。") from exc

    if _PADDLE_ENGINE is None:
        _PADDLE_ENGINE = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    normalized_images = []
    for index, image in enumerate(images):
        suffix = suffix_for_mime(image.get("mime"))
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(image.get("bytes") or b"")
                temp_path = temp_file.name
            raw_result = _PADDLE_ENGINE.ocr(temp_path, cls=True)
            blocks = normalize_paddle_blocks(raw_result)
            normalized_images.append(
                {
                    "filename": image.get("filename") or f"image-{index + 1}{suffix}",
                    "mime": image.get("mime") or "",
                    "blocks": blocks,
                    "block_count": len(blocks),
                    "text": "\n".join(block["text"] for block in blocks if block.get("text")),
                }
            )
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

    return {"provider": "paddle", "real_ocr": True, "images": normalized_images, "warnings": []}


def normalize_paddle_blocks(raw_result) -> list[dict]:
    blocks = []
    pages = raw_result or []
    for page in pages:
        for item in page or []:
            if not item or len(item) < 2:
                continue
            bbox = item[0]
            text_info = item[1]
            text = text_info[0] if text_info else ""
            confidence = text_info[1] if len(text_info) > 1 else None
            blocks.append(normalize_block({"text": text, "confidence": confidence, "bbox": bbox}))
    return blocks


def normalize_ocr_payload(payload: dict, provider: str) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("OCR 服务必须返回 JSON object。")

    raw_images = payload.get("images") or payload.get("results") or []
    if isinstance(raw_images, dict):
        raw_images = [raw_images]
    if not raw_images and (payload.get("blocks") or payload.get("text")):
        raw_images = [payload]

    images = []
    for index, item in enumerate(raw_images):
        blocks = [normalize_block(block) for block in item.get("blocks", [])]
        text = item.get("text") or "\n".join(block.get("text", "") for block in blocks if block.get("text"))
        images.append(
            {
                "filename": item.get("filename") or item.get("name") or f"image-{index + 1}",
                "mime": item.get("mime") or item.get("type") or "",
                "blocks": blocks,
                "block_count": len(blocks),
                "text": text.strip(),
            }
        )

    return {
        "provider": payload.get("provider") or provider,
        "real_ocr": bool(payload.get("real_ocr", True)),
        "images": images,
        "warnings": payload.get("warnings") or [],
    }


def normalize_block(block: dict) -> dict:
    text = str(block.get("text") or block.get("content") or "").strip()
    confidence = block.get("confidence", block.get("score"))
    try:
        confidence = round(float(confidence), 4) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    return {
        "text": text,
        "confidence": confidence,
        "bbox": block.get("bbox") or block.get("box") or block.get("points") or [],
        "role_hint": block.get("role_hint") or block.get("role") or "",
    }


def run_demo_ocr(images: list[dict], reason: str) -> dict:
    return {
        "provider": "demo",
        "real_ocr": False,
        "images": [
            {
                "filename": image.get("filename") or f"image-{index + 1}",
                "mime": image.get("mime") or "",
                "blocks": [],
                "block_count": 0,
                "text": "",
            }
            for index, image in enumerate(images)
        ],
        "warnings": [reason],
    }


def summarize_ocr(result: dict) -> str:
    image_count = len(result.get("images", []))
    block_count = sum(int(item.get("block_count") or len(item.get("blocks", []))) for item in result.get("images", []))
    provider = result.get("provider") or "unknown"
    if result.get("real_ocr"):
        return f"OCR 解析完成：provider={provider}，共 {image_count} 张图，识别 {block_count} 个文本块。"
    warning = "；".join(result.get("warnings") or [])
    return f"OCR 未启用真实识别：provider={provider}，共 {image_count} 张图。{warning}"


def suffix_for_mime(mime: str | None) -> str:
    return {
        "image/png": ".png",
        "image/webp": ".webp",
        "image/jpeg": ".jpg",
    }.get(mime or "", ".jpg")


def ocr_prompt_context(ocr_result: dict | None) -> str:
    if not ocr_result:
        return ""
    if not ocr_result.get("text"):
        return "OCR 原始文本：暂无可用文本。"
    return "OCR 原始文本如下，请优先基于这些文本做证据抽取，不要编造缺失字段：\n" + ocr_result["text"][:12000]
