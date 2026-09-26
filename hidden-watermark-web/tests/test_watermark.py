from PIL import Image

from tests.helpers import natural_test_image, plain_images
from watermark.decoder import detect_watermark
from watermark.encoder import embed_watermark
from watermark.metrics import image_metrics

MESSAGE = "隐藏水印测试 123 ABC 日本語"


def test_png_disk_roundtrip(tmp_path):
    source = natural_test_image(768, 768)
    encoded = embed_watermark(source, MESSAGE)
    path = tmp_path / "watermarked.png"
    encoded.image.save(path, "PNG")
    reloaded = Image.open(path)
    result = detect_watermark(reloaded)
    assert result.valid is True
    assert result.message == MESSAGE
    psnr, ssim = image_metrics(source, reloaded)
    assert psnr > 34
    assert ssim > 0.96


def test_alpha_channel_is_preserved(tmp_path):
    source = natural_test_image(768, 768).convert("RGBA")
    alpha = Image.linear_gradient("L").resize(source.size)
    source.putalpha(alpha)
    result = embed_watermark(source, "RGBA 水印")
    assert result.image.mode == "RGBA"
    assert result.image.getchannel("A").tobytes() == alpha.tobytes()


def test_plain_images_do_not_false_positive():
    for image in plain_images():
        result = detect_watermark(image)
        assert result.found is False
        assert result.valid is False
