"""Manual benchmark used to select the default method/channel.

Run: python -m tests.benchmark_algorithms
"""

import io

import numpy as np
from PIL import Image

from tests.helpers import natural_test_image
from watermark.encoder import embed_watermark
from watermark.metrics import image_metrics
from watermark.protocol import PACKET_BITS, parse_packet
from watermark.transform import PROFILES, extract_bits


def jpeg(image, quality):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality, subsampling=0)
    buffer.seek(0)
    return Image.open(buffer).copy()


def main():
    source = natural_test_image(1024, 1024)
    message = "隐藏水印测试 123 ABC 日本語"
    print("method,channel,png,psnr,ssim,jpeg100,jpeg95,jpeg90,jpeg85,jpeg80")
    for method in ("qim", "relation"):
        for channel in ("Y", "Cb", "Cr"):
            result = embed_watermark(
                source, message, strength="balanced", channel=channel, method=method
            )
            psnr, ssim = image_metrics(source, result.image)

            def configured_decode(image):
                bits = extract_bits(
                    np.asarray(image.convert("RGB")),
                    PACKET_BITS,
                    PROFILES["balanced"],
                    channel,
                    method,
                )
                try:
                    return (
                        parse_packet(np.packbits(bits, bitorder="big").tobytes()).message == message
                    )
                except Exception:
                    return False

            png_ok = configured_decode(result.image)
            values = []
            for quality in (100, 95, 90, 85, 80):
                values.append("PASS" if configured_decode(jpeg(result.image, quality)) else "FAIL")
            print(f"{method},{channel},{png_ok},{psnr},{ssim}," + ",".join(values))


if __name__ == "__main__":
    main()
