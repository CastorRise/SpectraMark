from __future__ import annotations

import hashlib

import numpy as np

BLOCK_SIZE = 4


def deterministic_indices(total: int, count: int, width: int, height: int) -> np.ndarray:
    if count > total:
        raise ValueError("Not enough transform blocks")
    seed_bytes = hashlib.blake2b(
        f"hidden-watermark:v1:{width}x{height}".encode(), digest_size=8
    ).digest()
    seed = int.from_bytes(seed_bytes, "big")
    return np.random.default_rng(seed).permutation(total)[:count]


def activity_factors(ll_band: np.ndarray) -> np.ndarray:
    """Stable LL-band texture estimate used for gentle adaptive strength.

    Selection itself remains dimension-seeded so small pixel changes cannot reorder
    the complete payload. LL activity only changes the local step within a narrow
    range, favoring textured areas without making decoding position-dependent.
    """
    h = (ll_band.shape[0] // BLOCK_SIZE) * BLOCK_SIZE
    w = (ll_band.shape[1] // BLOCK_SIZE) * BLOCK_SIZE
    blocks = (
        ll_band[:h, :w]
        .reshape(h // BLOCK_SIZE, BLOCK_SIZE, w // BLOCK_SIZE, BLOCK_SIZE)
        .transpose(0, 2, 1, 3)
        .reshape(-1, BLOCK_SIZE, BLOCK_SIZE)
    )
    std = blocks.std(axis=(1, 2))
    return 0.92 + 0.16 * np.tanh(std / 36.0)
