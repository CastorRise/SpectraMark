from __future__ import annotations

import numpy as np
from PIL import Image


def natural_test_image(width=768, height=768, seed=7) -> Image.Image:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width]
    base = np.empty((height, width, 3), dtype=np.float32)
    base[:, :, 0] = 72 + 110 * x / width + 28 * np.sin(y / 19)
    base[:, :, 1] = 58 + 120 * y / height + 24 * np.cos(x / 23)
    base[:, :, 2] = 110 + 65 * np.sin((x + y) / 37)
    texture = rng.normal(0, 13, base.shape)
    # Geometric regions approximate edges and natural mid-frequency detail.
    circles = ((x - width * 0.34) ** 2 + (y - height * 0.42) ** 2) < (width * 0.16) ** 2
    base[circles] += np.array([45, -16, 18])
    stripes = ((x // 18 + y // 27) % 2) == 0
    base[stripes] += np.array([8, 5, -6])
    return Image.fromarray(np.clip(base + texture, 0, 255).astype(np.uint8), "RGB")


def plain_images(size=512):
    y, x = np.mgrid[0:size, 0:size]
    gradient = np.stack((x / size * 255, y / size * 255, (x + y) / (2 * size) * 255), axis=2)
    rng = np.random.default_rng(99)
    noise = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    return [
        Image.new("RGB", (size, size), (118, 142, 165)),
        Image.fromarray(gradient.astype(np.uint8), "RGB"),
        Image.fromarray(noise, "RGB"),
        natural_test_image(size, size),
    ]
