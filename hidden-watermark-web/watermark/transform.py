from __future__ import annotations

from collections.abc import Sequence
from typing import Dict, List, Tuple

import cv2
import numpy as np
import pywt
from PIL import Image
from scipy.fft import dctn, idctn

from .block_selector import BLOCK_SIZE, activity_factors, deterministic_indices
from .models import Capacity, Channel, Method, StrengthProfile
from .protocol import MAX_CHARACTERS, MAX_PAYLOAD_BYTES, PACKET_BITS

PROFILES: Dict[str, StrengthProfile] = {
    "low": StrengthProfile("low", qim_step=18.0, relation_threshold=13.0, repetition=1),
    "balanced": StrengthProfile("balanced", qim_step=27.0, relation_threshold=20.0, repetition=2),
    "strong": StrengthProfile("strong", qim_step=36.0, relation_threshold=28.0, repetition=3),
}

CHANNEL_INDEX = {"Y": 0, "Cr": 1, "Cb": 2}
COEFF_A = (1, 2)
COEFF_B = (2, 1)


def _block_count_for_shape(width: int, height: int) -> int:
    band_h, band_w = height // 2, width // 2
    per_band = (band_h // BLOCK_SIZE) * (band_w // BLOCK_SIZE)
    return per_band * 3


def calculate_capacity(image_or_size, strength: str = "balanced") -> Capacity:
    if isinstance(image_or_size, Image.Image):
        width, height = image_or_size.size
    else:
        width, height = image_or_size
    profile = PROFILES[strength]
    blocks = _block_count_for_shape(width, height)
    writable = blocks // profile.repetition
    sufficient = writable >= PACKET_BITS
    return Capacity(
        available_blocks=blocks,
        writable_bits=writable,
        max_payload_bytes=MAX_PAYLOAD_BYTES if sufficient else 0,
        recommended_max_characters=MAX_CHARACTERS if sufficient else 0,
        sufficient=sufficient,
    )


def _to_blocks(band: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
    h = (band.shape[0] // BLOCK_SIZE) * BLOCK_SIZE
    w = (band.shape[1] // BLOCK_SIZE) * BLOCK_SIZE
    blocks = (
        band[:h, :w]
        .reshape(h // BLOCK_SIZE, BLOCK_SIZE, w // BLOCK_SIZE, BLOCK_SIZE)
        .transpose(0, 2, 1, 3)
        .reshape(-1, BLOCK_SIZE, BLOCK_SIZE)
    )
    return blocks.copy(), (h, w)


def _from_blocks(blocks: np.ndarray, shape: Tuple[int, int], original: np.ndarray) -> np.ndarray:
    h, w = shape
    rebuilt = (
        blocks.reshape(h // BLOCK_SIZE, w // BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
        .transpose(0, 2, 1, 3)
        .reshape(h, w)
    )
    output = original.copy()
    output[:h, :w] = rebuilt
    return output


def _prepare(channel: np.ndarray):
    ll, details = pywt.dwt2(channel.astype(np.float32), "haar")
    factor_base = activity_factors(ll)
    coeff_sets: List[np.ndarray] = []
    shapes: List[Tuple[int, int]] = []
    originals: List[np.ndarray] = []
    factors: List[np.ndarray] = []
    for band in details:
        blocks, shape = _to_blocks(band)
        coeff_sets.append(dctn(blocks, axes=(-2, -1), norm="ortho"))
        shapes.append(shape)
        originals.append(band)
        factors.append(factor_base[: len(blocks)])
    return ll, details, coeff_sets, shapes, originals, np.concatenate(factors)


def _split_values(values: np.ndarray, coeff_sets: Sequence[np.ndarray], coord) -> None:
    offset = 0
    for coeff in coeff_sets:
        count = len(coeff)
        coeff[:, coord[0], coord[1]] = values[offset : offset + count]
        offset += count


def embed_bits(
    rgb: np.ndarray,
    bits: np.ndarray,
    profile: StrengthProfile,
    channel_name: Channel = "Cb",
    method: Method = "qim",
) -> np.ndarray:
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    index = CHANNEL_INDEX[channel_name]
    ll, details, coeff_sets, shapes, originals, factors = _prepare(ycc[:, :, index])
    total = sum(len(c) for c in coeff_sets)
    repeated = np.tile(bits.astype(np.uint8), profile.repetition)
    positions = deterministic_indices(total, len(repeated), rgb.shape[1], rgb.shape[0])
    a = np.concatenate([c[:, COEFF_A[0], COEFF_A[1]] for c in coeff_sets])
    local = factors[positions]

    if method == "qim":
        steps = profile.qim_step * local
        current = a[positions]
        q = np.rint(current / steps).astype(np.int64)
        mismatch = (q & 1) != repeated
        lower = q - 1
        upper = q + 1
        choose_upper = np.abs(upper * steps - current) < np.abs(lower * steps - current)
        q[mismatch] = np.where(choose_upper[mismatch], upper[mismatch], lower[mismatch])
        a[positions] = q * steps
    else:
        b = np.concatenate([c[:, COEFF_B[0], COEFF_B[1]] for c in coeff_sets])
        threshold = profile.relation_threshold * local
        av, bv = a[positions], b[positions]
        sign = np.where(repeated == 1, 1.0, -1.0)
        signed_difference = sign * (av - bv)
        correction = np.maximum(0.0, threshold - signed_difference)
        a[positions] = av + sign * correction / 2.0
        b[positions] = bv - sign * correction / 2.0
        _split_values(b, coeff_sets, COEFF_B)
    _split_values(a, coeff_sets, COEFF_A)

    rebuilt_details = []
    for coeff, shape, original in zip(coeff_sets, shapes, originals):
        blocks = idctn(coeff, axes=(-2, -1), norm="ortho")
        rebuilt_details.append(_from_blocks(blocks, shape, original))
    restored = pywt.idwt2((ll, tuple(rebuilt_details)), "haar")
    ycc[:, :, index] = restored[: rgb.shape[0], : rgb.shape[1]]
    return cv2.cvtColor(np.clip(ycc, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)


def extract_bits(
    rgb: np.ndarray,
    bit_count: int,
    profile: StrengthProfile,
    channel_name: Channel = "Cb",
    method: Method = "qim",
) -> np.ndarray:
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    index = CHANNEL_INDEX[channel_name]
    _, _, coeff_sets, _, _, factors = _prepare(ycc[:, :, index])
    prepared = (
        np.concatenate([c[:, COEFF_A[0], COEFF_A[1]] for c in coeff_sets]),
        np.concatenate([c[:, COEFF_B[0], COEFF_B[1]] for c in coeff_sets]),
        factors,
        rgb.shape[1],
        rgb.shape[0],
    )
    return extract_prepared(prepared, bit_count, profile, method)


def prepare_extraction(rgb: np.ndarray, channel_name: Channel):
    ycc = cv2.cvtColor(rgb, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    index = CHANNEL_INDEX[channel_name]
    _, _, coeff_sets, _, _, factors = _prepare(ycc[:, :, index])
    return (
        np.concatenate([c[:, COEFF_A[0], COEFF_A[1]] for c in coeff_sets]),
        np.concatenate([c[:, COEFF_B[0], COEFF_B[1]] for c in coeff_sets]),
        factors,
        rgb.shape[1],
        rgb.shape[0],
    )


def extract_prepared(prepared, bit_count: int, profile: StrengthProfile, method: Method):
    a, b, factors, width, height = prepared
    total = len(a)
    count = bit_count * profile.repetition
    positions = deterministic_indices(total, count, width, height)
    if method == "qim":
        steps = profile.qim_step * factors[positions]
        raw = (np.rint(a[positions] / steps).astype(np.int64) & 1).astype(np.uint8)
    else:
        raw = (a[positions] > b[positions]).astype(np.uint8)
    copies = raw.reshape(profile.repetition, bit_count)
    return (copies.sum(axis=0) >= (profile.repetition // 2 + 1)).astype(np.uint8)
