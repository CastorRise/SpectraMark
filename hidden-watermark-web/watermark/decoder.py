from __future__ import annotations

import numpy as np
from PIL import Image

from .ecc import ECCError
from .models import DetectionResult
from .protocol import (
    PACKET_BITS,
    SYNC,
    ProtocolError,
    parse_packet,
)
from .transform import PROFILES, calculate_capacity, extract_prepared, prepare_extraction


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def detect_watermark(image: Image.Image) -> DetectionResult:
    rgb = np.asarray(image.convert("RGB"))
    sync_bits = np.unpackbits(np.frombuffer(SYNC, dtype=np.uint8), bitorder="big")
    capacities = {strength: calculate_capacity(image, strength).sufficient for strength in PROFILES}
    best_trace = None
    for channel in ("Cb", "Cr", "Y"):
        prepared = prepare_extraction(rgb, channel)
        for method in ("qim", "relation"):
            for strength, profile in PROFILES.items():
                if not capacities[strength]:
                    continue
                bits = extract_prepared(prepared, PACKET_BITS, profile, method)
                sync_errors = _hamming(bits[: len(sync_bits)], sync_bits)
                if best_trace is None or sync_errors < best_trace[0]:
                    best_trace = (sync_errors, strength, channel, method)
                if sync_errors > 34:
                    continue
                packet = np.packbits(bits, bitorder="big").tobytes()
                try:
                    decoded = parse_packet(packet)
                    return DetectionResult(
                        found=True,
                        valid=True,
                        message=decoded.message,
                        protocol_version=decoded.version,
                        crc_valid=True,
                        ecc_valid=True,
                        strength=strength,
                        channel=channel,
                        method=method,
                        sync_errors=sync_errors,
                    )
                except (ECCError, ProtocolError):
                    continue
    if best_trace and best_trace[0] <= 24:
        return DetectionResult(
            found=True,
            valid=False,
            damaged=True,
            strength=best_trace[1],
            channel=best_trace[2],
            method=best_trace[3],
            sync_errors=best_trace[0],
        )
    return DetectionResult(found=False, valid=False)
