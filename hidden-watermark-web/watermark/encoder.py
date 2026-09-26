from __future__ import annotations

import numpy as np
from PIL import Image

from .models import Channel, EmbedResult, Method, Strength
from .protocol import VERSION, build_packet
from .transform import PROFILES, calculate_capacity, embed_bits


class CapacityError(ValueError):
    pass


def embed_watermark(
    image: Image.Image,
    message: str,
    strength: Strength = "balanced",
    channel: Channel = "Cr",
    method: Method = "relation",
) -> EmbedResult:
    if strength not in PROFILES:
        raise ValueError("不支持的水印强度。")
    capacity = calculate_capacity(image, strength)
    if not capacity.sufficient:
        raise CapacityError("当前图片容量不足，无法写入该长度的水印。")
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    rgb_image = image.convert("RGB")
    packet = build_packet(message, flags={"low": 1, "balanced": 2, "strong": 3}[strength])
    bits = np.unpackbits(np.frombuffer(packet, dtype=np.uint8), bitorder="big")
    encoded = embed_bits(np.asarray(rgb_image), bits, PROFILES[strength], channel, method)
    output = Image.fromarray(encoded, mode="RGB")
    if alpha is not None:
        output.putalpha(alpha)
    return EmbedResult(
        image=output,
        message=message,
        protocol_version=VERSION,
        width=output.width,
        height=output.height,
        strength=strength,
        channel=channel,
        method=method,
    )
