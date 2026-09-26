import io
import time

from fastapi.testclient import TestClient

from app import app
from tests.helpers import natural_test_image
from web import api
from web.config import APP_VERSION, EXPIRY_SECONDS, MAX_PIXELS, MAX_UPLOAD_BYTES

client = TestClient(app)
MESSAGE = "隐藏水印测试 123 ABC 日本語"


def image_bytes(fmt="PNG"):
    buffer = io.BytesIO()
    natural_test_image(768, 768).save(buffer, fmt, quality=96)
    return buffer.getvalue()


def test_status_and_home():
    assert client.get("/").status_code == 200
    response = client.get("/api/status")
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == APP_VERSION == app.version
    assert payload["limits"]["max_upload_bytes"] == MAX_UPLOAD_BYTES
    assert payload["limits"]["max_pixels"] == MAX_PIXELS


def test_lifespan_runs_cleanup_on_start_and_shutdown(monkeypatch):
    calls = []
    monkeypatch.setattr(api.store, "cleanup", lambda: calls.append(time.time()))

    with TestClient(app) as lifespan_client:
        assert lifespan_client.get("/api/status").status_code == 200

    assert len(calls) >= 2


def test_small_image_reports_insufficient_capacity():
    buffer = io.BytesIO()
    natural_test_image(128, 128).save(buffer, "PNG")
    response = client.post(
        "/api/watermark/capacity",
        files={"file": ("small.png", buffer.getvalue(), "image/png")},
        data={"strength": "balanced"},
    )
    assert response.status_code == 200
    assert response.json()["sufficient"] is False


def test_complete_png_api_flow():
    response = client.post(
        "/api/watermark/embed",
        files={"file": ("source.png", image_bytes(), "image/png")},
        data={
            "message": MESSAGE,
            "strength": "balanced",
            "output_format": "png",
            "jpeg_quality": "95",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["integrity_verified"] is True
    downloaded = client.get(f"/api/download/{payload['download_id']}")
    assert downloaded.status_code == 200
    detected = client.post(
        "/api/watermark/detect",
        files={"file": ("watermarked.png", downloaded.content, "image/png")},
    )
    assert detected.status_code == 200
    assert detected.json()["message"] == MESSAGE


def test_jpeg_upload_and_verified_jpeg_output():
    capacity = client.post(
        "/api/watermark/capacity",
        files={"file": ("source.jpg", image_bytes("JPEG"), "image/jpeg")},
        data={"strength": "balanced"},
    )
    assert capacity.status_code == 200
    assert capacity.json()["sufficient"] is True
    response = client.post(
        "/api/watermark/embed",
        files={"file": ("source.jpeg", image_bytes("JPEG"), "image/jpeg")},
        data={
            "message": "JPEG 自校验",
            "strength": "balanced",
            "output_format": "jpeg",
            "jpeg_quality": "95",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["integrity_verified"] is True


def test_rejects_fake_image_and_long_text():
    bad = client.post(
        "/api/watermark/detect", files={"file": ("fake.jpg", b"not an image", "image/jpeg")}
    )
    assert bad.status_code == 400
    too_long = client.post(
        "/api/watermark/embed",
        files={"file": ("source.png", image_bytes(), "image/png")},
        data={
            "message": "x" * 65,
            "strength": "balanced",
            "output_format": "png",
            "jpeg_quality": "95",
        },
    )
    assert too_long.status_code == 400


def test_download_store_removes_expired_files(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "TEMP_DIR", tmp_path)
    path = tmp_path / "watermarked-expired.png"
    path.write_bytes(b"expired")
    download_store = api.DownloadStore()
    token = download_store.add(path, "result.png")
    download_store._items[token]["created"] = time.time() - EXPIRY_SECONDS - 1

    download_store.cleanup()

    assert not path.exists()
    assert token not in download_store._items
