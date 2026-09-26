from __future__ import annotations

import asyncio
import io
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, TypeVar

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from watermark.decoder import detect_watermark
from watermark.encoder import CapacityError, embed_watermark
from watermark.metrics import image_metrics
from watermark.protocol import MAX_CHARACTERS, MAX_PAYLOAD_BYTES, VERSION
from watermark.transform import PROFILES, calculate_capacity
from web.config import (
    ALLOWED_FORMATS,
    APP_VERSION,
    EXPIRY_SECONDS,
    MAX_PIXELS,
    MAX_UPLOAD_BYTES,
    PROCESSING_CONCURRENCY,
    TEMP_DIR,
)

TEMP_DIR.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
T = TypeVar("T")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DownloadStore:
    def __init__(self):
        self._items: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def cleanup(self):
        cutoff = time.time() - EXPIRY_SECONDS
        with self._lock:
            expired = [key for key, item in self._items.items() if item["created"] < cutoff]
            for key in expired:
                item = self._items.pop(key)
                item["path"].unlink(missing_ok=True)
        for path in TEMP_DIR.glob("watermarked-*.*"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass

    def add(self, path: Path, filename: str) -> str:
        self.cleanup()
        token = str(uuid.uuid4())
        with self._lock:
            self._items[token] = {"path": path, "filename": filename, "created": time.time()}
        return token

    def get(self, token: str):
        self.cleanup()
        try:
            uuid.UUID(token)
        except ValueError as exc:
            raise ApiError("下载链接无效或已过期。", 404) from exc
        with self._lock:
            item = self._items.get(token)
        if not item or not item["path"].is_file():
            raise ApiError("下载链接无效或已过期。", 404)
        return item


store = DownloadStore()
router = APIRouter(prefix="/api")
processing_slots = asyncio.Semaphore(PROCESSING_CONCURRENCY)


async def _run_processing(function: Callable[..., T], *args) -> T:
    """Keep CPU-heavy image work off the event loop and bound peak memory."""
    async with processing_slots:
        return await run_in_threadpool(function, *args)


async def _read_upload(file: UploadFile) -> bytes:
    data = bytearray()
    try:
        while chunk := await file.read(1024 * 1024):
            data.extend(chunk)
            if len(data) > MAX_UPLOAD_BYTES:
                raise ApiError(f"图片文件不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。", 413)
    finally:
        await file.close()
    if not data:
        raise ApiError("请选择要处理的图片。")
    return bytes(data)


def _decode_image(data: bytes):
    try:
        with Image.open(io.BytesIO(data)) as probe:
            image_format = probe.format
            if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) > 1:
                raise ApiError("暂不支持动态图像。")
            if image_format not in ALLOWED_FORMATS:
                raise ApiError("不支持的图片格式，请上传 PNG、JPG 或 JPEG。")
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise ApiError(f"图片不能超过 {MAX_PIXELS // 1_000_000} MP。", 413)
            probe.load()
            image = ImageOps.exif_transpose(probe).copy()
        return image, image_format
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ApiError("图片无法读取或文件已损坏。") from exc


def _safe_stem(filename: str | None) -> str:
    stem = Path(filename or "image").stem
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", stem, flags=re.UNICODE).strip("-")
    return cleaned[:48] or "image"


def _capacity_response(data: bytes, strength: str):
    image, _ = _decode_image(data)
    value = calculate_capacity(image, strength)
    return {
        "width": image.width,
        "height": image.height,
        "available_blocks": value.available_blocks,
        "writable_bits": value.writable_bits,
        "max_payload_bytes": value.max_payload_bytes,
        "recommended_max_characters": value.recommended_max_characters,
        "sufficient": value.sufficient,
    }


def _embed_response(
    data: bytes,
    original_filename: str | None,
    message: str,
    strength: str,
    output_format: str,
    jpeg_quality: int,
):
    image, _ = _decode_image(data)
    try:
        result = embed_watermark(image, message, strength=strength)
    except (CapacityError, ValueError) as exc:
        raise ApiError(str(exc)) from exc

    buffer = io.BytesIO()
    if output_format == "png":
        result.image.save(buffer, format="PNG", compress_level=6)
        media_type, extension = "image/png", "png"
    else:
        result.image.convert("RGB").save(
            buffer, format="JPEG", quality=jpeg_quality, subsampling=0, optimize=True
        )
        media_type, extension = "image/jpeg", "jpg"
    encoded_bytes = buffer.getvalue()
    with Image.open(io.BytesIO(encoded_bytes)) as encoded:
        encoded.load()
        reloaded = encoded.copy()
    verification = detect_watermark(reloaded)
    if not verification.valid or verification.message != message:
        if output_format == "jpeg":
            raise ApiError("JPEG 压缩导致水印无法可靠保存，请提高 JPEG 质量或改用 PNG。", 422)
        raise ApiError("本次水印写入未通过可靠性校验。", 422)

    psnr, ssim = image_metrics(image, reloaded)
    internal_name = f"watermarked-{uuid.uuid4().hex}.{extension}"
    output_path = TEMP_DIR / internal_name
    output_path.write_bytes(encoded_bytes)
    friendly_name = f"{_safe_stem(original_filename)}-watermarked.{extension}"
    try:
        download_id = store.add(output_path, friendly_name)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return {
        "success": True,
        "message": message,
        "protocol_version": VERSION,
        "width": reloaded.width,
        "height": reloaded.height,
        "psnr": psnr,
        "ssim": ssim,
        "output_format": output_format,
        "strength": strength,
        "integrity_verified": True,
        "download_id": download_id,
        "download_url": f"/api/download/{download_id}",
        "media_type": media_type,
    }


def _detect_response(data: bytes):
    image, _ = _decode_image(data)
    result = detect_watermark(image)
    if result.valid:
        return {
            "found": True,
            "valid": True,
            "damaged": False,
            "message": result.message,
            "protocol_version": result.protocol_version,
            "crc_valid": result.crc_valid,
            "ecc_valid": result.ecc_valid,
        }
    if result.damaged:
        return {
            "found": True,
            "valid": False,
            "damaged": True,
            "message": "检测到疑似隐藏水印，但数据已经损坏，无法可靠恢复。",
        }
    return {"found": False, "valid": False, "damaged": False}


@router.get("/status")
async def status():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "protocol_version": VERSION,
        "limits": {
            "max_characters": MAX_CHARACTERS,
            "max_payload_bytes": MAX_PAYLOAD_BYTES,
            "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_pixels": MAX_PIXELS,
            "processing_concurrency": PROCESSING_CONCURRENCY,
        },
    }


@router.post("/watermark/capacity")
async def capacity(file: UploadFile = File(...), strength: str = Form("balanced")):
    if strength not in PROFILES:
        raise ApiError("不支持的水印强度。")
    data = await _read_upload(file)
    return await _run_processing(_capacity_response, data, strength)


@router.post("/watermark/embed")
async def embed(
    file: UploadFile = File(...),
    message: str = Form(...),
    strength: str = Form("balanced"),
    output_format: str = Form("png"),
    jpeg_quality: int = Form(95),
):
    if strength not in PROFILES:
        raise ApiError("不支持的水印强度。")
    output_format = output_format.lower()
    if output_format not in {"png", "jpeg"}:
        raise ApiError("输出格式必须是 PNG 或 JPEG。")
    if jpeg_quality not in {80, 85, 90, 95, 100}:
        raise ApiError("JPEG 质量设置无效。")
    original_filename = file.filename
    data = await _read_upload(file)
    return await _run_processing(
        _embed_response,
        data,
        original_filename,
        message,
        strength,
        output_format,
        jpeg_quality,
    )


@router.post("/watermark/detect")
async def detect(file: UploadFile = File(...)):
    data = await _read_upload(file)
    return await _run_processing(_detect_response, data)


@router.get("/download/{download_id}")
async def download(download_id: str):
    item = store.get(download_id)
    return FileResponse(item["path"], filename=item["filename"])


def api_error_response(exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code, content={"success": False, "detail": exc.message}
    )
