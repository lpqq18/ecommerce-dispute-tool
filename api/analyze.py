from pathlib import Path
from typing import List
import sys

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import MAX_IMAGES, MAX_UPLOAD_BYTES, analyze_images  # noqa: E402


app = FastAPI()


async def handle_analyze(images: List[UploadFile] = File(...)):
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传 1 张截图。")
    if len(images) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail="最多上传 5 张截图。")

    normalized = []
    total_size = 0
    for image in images:
        if image.content_type not in ("image/png", "image/jpeg", "image/webp"):
            raise HTTPException(status_code=400, detail="仅支持 PNG、JPG、WebP 图片。")
        content = await image.read()
        total_size += len(content)
        if total_size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="图片总大小不能超过 25MB。")
        normalized.append({"mime": image.content_type, "bytes": content, "filename": image.filename})

    try:
        return JSONResponse(analyze_images(normalized))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/")
async def analyze_root(images: List[UploadFile] = File(...)):
    return await handle_analyze(images)


@app.post("/api/analyze")
async def analyze_api(images: List[UploadFile] = File(...)):
    return await handle_analyze(images)
