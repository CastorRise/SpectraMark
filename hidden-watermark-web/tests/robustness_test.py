"""Explicit robustness checks; run with: pytest tests/robustness_test.py -v."""

import io

import numpy as np
import pytest
from PIL import Image, ImageEnhance

from tests.helpers import natural_test_image
from watermark.decoder import detect_watermark
from watermark.encoder import embed_watermark

MESSAGE = "Robust 隐藏水印 日本語 123"


def png_roundtrip(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return Image.open(buffer).copy()


def jpeg_roundtrip(image, quality):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality, subsampling=0)
    buffer.seek(0)
    return Image.open(buffer).copy()


@pytest.fixture(scope="module")
def encoded():
    return embed_watermark(natural_test_image(1024, 1024), MESSAGE, strength="strong").image


def assert_message(image):
    result = detect_watermark(image)
    assert result.valid and result.message == MESSAGE


def test_no_processing(encoded):
    assert_message(encoded)


def test_png_resave(encoded):
    assert_message(png_roundtrip(encoded))


@pytest.mark.parametrize("quality", [100, 95, 90, 85, 80])
def test_jpeg(encoded, quality):
    result = detect_watermark(jpeg_roundtrip(encoded, quality))
    expected = quality >= 85
    assert result.valid is expected
    if expected:
        assert result.message == MESSAGE


@pytest.mark.parametrize("scale", [1.0, 0.9, 0.75, 0.5])
def test_resize_documented(encoded, scale):
    resized = encoded.resize(
        (round(encoded.width * scale), round(encoded.height * scale)), Image.Resampling.LANCZOS
    )
    result = detect_watermark(resized)
    assert result.valid is (scale == 1.0)


@pytest.mark.parametrize("factor", [0.95, 1.05])
def test_brightness(encoded, factor):
    result = detect_watermark(ImageEnhance.Brightness(encoded).enhance(factor))
    assert result.valid and result.message == MESSAGE


@pytest.mark.parametrize("factor", [0.95, 1.05])
def test_contrast(encoded, factor):
    result = detect_watermark(ImageEnhance.Contrast(encoded).enhance(factor))
    assert result.valid and result.message == MESSAGE


def test_light_gaussian_noise(encoded):
    rng = np.random.default_rng(123)
    array = np.asarray(encoded).astype(np.float32)
    noisy = Image.fromarray(
        np.clip(array + rng.normal(0, 1.2, array.shape), 0, 255).astype(np.uint8)
    )
    result = detect_watermark(noisy)
    assert result.valid and result.message == MESSAGE
