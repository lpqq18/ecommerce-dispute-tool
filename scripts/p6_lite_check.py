from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def result(name: str, status: str, detail: str = "", severity: str = "info") -> dict:
    return {"name": name, "status": status, "severity": severity, "detail": detail}


def run_git(*args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, (completed.stdout or completed.stderr or "").strip()


def check_git() -> list[dict]:
    checks = []
    code, inside = run_git("rev-parse", "--is-inside-work-tree")
    checks.append(result("git repository", "pass" if code == 0 and inside == "true" else "fail", inside, "blocker"))

    code, branch = run_git("branch", "--show-current")
    checks.append(result("git branch main", "pass" if code == 0 and branch == "main" else "warn", branch or "unknown", "warn"))

    code, remote = run_git("remote", "get-url", "origin")
    checks.append(result("git remote origin", "pass" if code == 0 and remote else "fail", remote, "blocker"))

    code, status = run_git("status", "--short")
    if code != 0:
        checks.append(result("git working tree", "fail", status, "blocker"))
    elif status:
        checks.append(result("git working tree", "warn", "Uncommitted changes exist. Commit before production deployment.", "warn"))
    else:
        checks.append(result("git working tree", "pass", "Clean working tree."))
    return checks


def check_release_bundle() -> list[dict]:
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
        "docs/P6_LITE_VALIDATION.md",
    ]
    checks = [result("dist directory", "pass" if DIST.exists() else "fail", str(DIST), "blocker")]
    for item in required:
        path = DIST / item
        checks.append(result(f"release file: {item}", "pass" if path.exists() else "fail", str(path), "blocker"))
    return checks


def check_lite_gates() -> list[dict]:
    import server

    config = server.runtime_config()
    checks = [
        result("privacy redaction", "pass" if config["privacy"]["redaction_enabled"] else "fail", json.dumps(config["privacy"]), "blocker"),
        result("runtime secrets hidden", "pass" if "OPENAI_API_KEY" not in json.dumps(config) else "fail", json.dumps(config), "blocker"),
    ]
    if not config["ocr"]["require_real"]:
        checks.append(result("real OCR not enabled", "skip", "P6-lite intentionally skips real OCR. Keep as follow-up.", "warn"))
    if not config["ocr"]["external_configured"] and config["ocr"]["provider"] != "paddle":
        checks.append(result("real OCR provider missing", "skip", "No OCR_API_URL or paddle provider in local env. Keep as follow-up.", "warn"))
    if not config["ai"]["openai_configured"]:
        checks.append(result("OpenAI key missing", "warn", "Local env has no OPENAI_API_KEY. Demo/rule fallback may be used.", "warn"))
    if not config["observability"]["webhook_configured"]:
        checks.append(result("external observability webhook missing", "warn", "Local observability logs still work; external platform not configured.", "warn"))
    if config["storage"]["driver"] == "json":
        checks.append(result("json storage", "warn", "JSON storage is acceptable for MVP/lite validation, not long-term production.", "warn"))
    return checks


def main() -> int:
    checks = []
    checks.extend(check_git())
    checks.extend(check_release_bundle())
    checks.extend(check_lite_gates())

    blockers = [item for item in checks if item["status"] == "fail" and item["severity"] == "blocker"]
    warnings = [item for item in checks if item["status"] in {"warn", "skip"}]
    summary = {
        "phase": "P6-lite",
        "status": "blocked" if blockers else "pass_with_warnings" if warnings else "pass",
        "blockers": len(blockers),
        "warnings": len(warnings),
        "checks": checks,
        "follow_ups": [
            "Configure real OCR provider and OCR_REQUIRE_REAL=1.",
            "Add real screenshots under test_samples/real_cases and run OCR regression.",
            "Configure ADMIN_TOKEN in Vercel before exposing admin logs.",
            "Commit and push current changes before expecting Vercel production to update.",
            "Verify public URL and WeChat access after deployment.",
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
