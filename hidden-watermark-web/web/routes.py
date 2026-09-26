from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from watermark.protocol import MAX_CHARACTERS, MAX_PAYLOAD_BYTES
from web.config import MAX_PIXELS, MAX_UPLOAD_BYTES

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "max_characters": MAX_CHARACTERS,
            "max_payload_bytes": MAX_PAYLOAD_BYTES,
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "max_pixels_mp": MAX_PIXELS // 1_000_000,
        },
    )
