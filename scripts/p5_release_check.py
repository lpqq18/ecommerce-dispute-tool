from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DIST = ROOT / "dist"
REAL_CASE_DIR = ROOT / "test_samples" / "real_cases"


def result(name: str, status: str, detail: str = "", severity: str = "info") -> dict:
    return {"name": name, "status": status, "severity": severity, "detail": detail}


def check_required_files() -> list[dict]:
    required = [
        "index.html",
        "app.js",
        "styles.css",
        "server.py",
        "case_store.py",
        "ocr_service.py",
        "evidence_engine.py",
        "workflow_engine.py",
        "observability.py",
        "privacy_guard.py",
        "storage_adapter.py",
        "api/analyze.py",
        "vercel.json",
        ".env.example",
    ]
    checks = []
    for item in required:
        path = ROOT / item
        checks.append(result(f"required file: {item}", "pass" if path.exists() else "fail", str(path), "blocker" if not path.exists() else "info"))
    return checks


def check_dist() -> list[dict]:
    required = [
        "index.html",
        "app.js",
        "styles.css",
        "server.py",
        "case_store.py",
        "ocr_service.py",
        "evidence_engine.py",
        "workflow_engine.py",
        "observability.py",
        "privacy_guard.py",
        "storage_adapter.py",
        "api/analyze.py",
        "docs/P4_PRODUCTION_READINESS.md",
        "docs/P5_RELEASE_VALIDATION.md",
    ]
    checks = [result("dist directory", "pass" if DIST.exists() else "fail", str(DIST), "blocker" if not DIST.exists() else "info")]
    for item in required:
        path = DIST / item
        checks.append(result(f"dist file: {item}", "pass" if path.exists() else "fail", str(path), "blocker" if not path.exists() else "info"))
    return checks


def check_vercel_config() -> list[dict]:
    config_path = ROOT / "vercel.json"
    if not config_path.exists():
        return [result("vercel config", "fail", "vercel.json missing", "blocker")]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    checks = [
        result("vercel buildCommand", "pass" if config.get("buildCommand") == "npm run build" else "fail", str(config.get("buildCommand")), "blocker"),
        result("vercel outputDirectory", "pass" if config.get("outputDirectory") == "dist" else "fail", str(config.get("outputDirectory")), "blocker"),
    ]
    headers = config.get("headers") or []
    has_no_store = any(
        header.get("source") == "/api/(.*)"
        and any(item.get("key", "").lower() == "cache-control" and "no-store" in item.get("value", "") for item in header.get("headers", []))
        for header in headers
    )
    checks.append(result("vercel api no-store header", "pass" if has_no_store else "warn", "Cache-Control no-store for /api/(.*)", "warn"))
    return checks


def check_runtime_config() -> list[dict]:
    import server

    config = server.runtime_config()
    checks = [
        result("privacy redaction enabled", "pass" if config["privacy"]["redaction_enabled"] else "fail", json.dumps(config["privacy"]), "blocker"),
        result("storage driver", "pass" if config["storage"]["driver"] == "json" else "warn", json.dumps(config["storage"]), "warn"),
        result("runtime has no secrets", "pass" if "OPENAI_API_KEY" not in json.dumps(config) else "fail", json.dumps(config), "blocker"),
    ]
    if not config["ocr"]["require_real"]:
        checks.append(result("real OCR enforcement", "warn", "OCR_REQUIRE_REAL is not enabled in current environment.", "warn"))
    else:
        checks.append(result("real OCR enforcement", "pass", "OCR_REQUIRE_REAL enabled."))
    if not config["ocr"]["external_configured"] and config["ocr"]["provider"] != "paddle":
        checks.append(result("real OCR provider", "warn", "No external OCR URL and provider is not paddle.", "warn"))
    else:
        checks.append(result("real OCR provider", "pass", json.dumps(config["ocr"])))
    if not os.getenv("ADMIN_TOKEN"):
        checks.append(result("admin token", "warn", "ADMIN_TOKEN is not set in current local environment.", "warn"))
    else:
        checks.append(result("admin token", "pass", "ADMIN_TOKEN configured."))
    return checks


def check_secret_scan() -> list[dict]:
    suspicious = []
    patterns = [
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
        re.compile(r"vercel_[A-Za-z0-9_]{20,}", re.I),
        re.compile(r"(?i)(api[_-]?key|token|password)\s*=\s*[\"'][^\"']{16,}[\"']"),
    ]
    include_ext = {".py", ".js", ".html", ".css", ".json", ".md", ".example"}
    skip_parts = {".git", "dist", "__pycache__", "deploy", "deploy_packages", "backups"}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix not in include_ext and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in patterns:
            if pattern.search(text):
                suspicious.append(str(path.relative_to(ROOT)))
                break
    status = "pass" if not suspicious else "fail"
    return [result("secret scan", status, ", ".join(suspicious) if suspicious else "No hardcoded secrets detected.", "blocker" if suspicious else "info")]


def check_real_case_samples() -> list[dict]:
    if not REAL_CASE_DIR.exists():
        return [result("real screenshot regression samples", "skip", "test_samples/real_cases not found. Add real screenshots here for final OCR regression.", "warn")]
    images = [
        path
        for path in REAL_CASE_DIR.rglob("*")
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if not images:
        return [result("real screenshot regression samples", "skip", "No screenshots found under test_samples/real_cases.", "warn")]
    return [result("real screenshot regression samples", "pass", f"{len(images)} screenshot(s) found.")]


def main() -> int:
    checks = []
    checks.extend(check_required_files())
    checks.extend(check_dist())
    checks.extend(check_vercel_config())
    checks.extend(check_runtime_config())
    checks.extend(check_secret_scan())
    checks.extend(check_real_case_samples())

    blockers = [item for item in checks if item["status"] == "fail" and item["severity"] == "blocker"]
    warnings = [item for item in checks if item["status"] in {"warn", "skip"}]
    summary = {
        "phase": "P5",
        "status": "blocked" if blockers else "pass_with_warnings" if warnings else "pass",
        "blockers": len(blockers),
        "warnings": len(warnings),
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
