from __future__ import annotations

import math

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


def image_metrics(original: Image.Image, encoded: Image.Image):
    a = np.asarray(original.convert("RGB"), dtype=np.float64)
    b = np.asarray(encoded.convert("RGB"), dtype=np.float64)
    mse = float(np.mean((a - b) ** 2))
    psnr = float("inf") if mse == 0 else 20.0 * math.log10(255.0 / math.sqrt(mse))
    ssim = structural_similarity(a, b, channel_axis=2, data_range=255)
    return round(psnr, 2), round(float(ssim), 6)
