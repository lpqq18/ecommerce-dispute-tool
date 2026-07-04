from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os


STORAGE_DRIVER = os.getenv("CASE_STORE_DRIVER", "json").strip().lower()
DATA_DIR = Path(os.getenv("CASE_DATA_DIR") or ("/tmp/ecommerce-dispute-tool" if os.getenv("VERCEL") else "data"))
STORE_PATH = DATA_DIR / "case_store.json"


class JsonCaseStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self, empty_store: dict) -> dict:
        if not self.path.exists():
            return deepcopy(empty_store)
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return deepcopy(empty_store)

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def info(self) -> dict:
        return {
            "driver": "json",
            "path": str(self.path),
            "ephemeral": str(self.path).replace("\\", "/").startswith("/tmp/"),
        }


def get_store_adapter() -> JsonCaseStore:
    if STORAGE_DRIVER != "json":
        raise RuntimeError(f"Unsupported CASE_STORE_DRIVER={STORAGE_DRIVER}. Current P4 build ships json adapter only.")
    return JsonCaseStore(STORE_PATH)


def storage_info() -> dict:
    return get_store_adapter().info()
