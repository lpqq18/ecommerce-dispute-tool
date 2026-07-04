from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_redaction() -> None:
    os.environ["CASE_DATA_DIR"] = tempfile.mkdtemp(prefix="ecommerce-p4-redaction-")
    os.environ["PRIVACY_REDACTION_ENABLED"] = "1"

    import case_store

    case_id = case_store.create_case(
        [{"filename": "order_13800138000.png", "mime": "image/png", "bytes": b"xx"}]
    )["id"]
    text = (
        "buyer phone 13800138000 order_id: ABC1234567890 "
        "tracking SF1234567890 email buyer@example.com "
        "address Hangzhou Westlake Road No 101"
    )

    case_store.set_case_ocr(case_id, {"real_ocr": True, "provider": "unit", "text": text, "images": [{"text": text}]})
    case_store.log_ai(case_id, text, text, text, 88)
    case_store.log_system("info", "privacy_test", text, case_id)
    case_store.log_observability(
        case_id,
        {
            "trace_id": "trace-test",
            "observation_id": "obs-test",
            "node_id": "ocr",
            "name": "OCR",
            "status": "success",
            "input": text,
            "output": text,
            "error": "",
            "metadata": {"raw": text},
            "timestamp": 1,
        },
    )

    blob = json.dumps(
        {
            "case": case_store.get_case(case_id),
            "ai": case_store.list_logs("ai", case_id),
            "system": case_store.list_logs("system", case_id),
            "observability": case_store.list_logs("observability", case_id),
        },
        ensure_ascii=False,
    )

    assert "13800138000" not in blob
    assert "ABC1234567890" not in blob
    assert "SF1234567890" not in blob
    assert "buyer@example.com" not in blob
    assert "[REDACTED_PHONE]" in blob
    assert "[REDACTED_EMAIL]" in blob
    assert "[REDACTED_ORDER]" in blob or "[REDACTED_TRACKING]" in blob


def test_require_real_ocr() -> None:
    os.environ["OCR_REQUIRE_REAL"] = "1"
    os.environ["OCR_PROVIDER"] = "demo"

    import ocr_service

    importlib.reload(ocr_service)
    try:
        ocr_service.run_ocr([{"filename": "demo.png", "mime": "image/png", "bytes": b"xx"}])
    except RuntimeError as exc:
        assert "OCR_REQUIRE_REAL=1" in str(exc)
    else:
        raise AssertionError("OCR_REQUIRE_REAL=1 should reject demo OCR mode.")


def main() -> None:
    test_redaction()
    test_require_real_ocr()
    print("P4 smoke tests passed.")


if __name__ == "__main__":
    main()
