from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Strength = Literal["low", "balanced", "strong"]
Method = Literal["qim", "relation"]
Channel = Literal["Y", "Cb", "Cr"]


@dataclass(frozen=True)
class StrengthProfile:
    name: Strength
    qim_step: float
    relation_threshold: float
    repetition: int


@dataclass(frozen=True)
class Capacity:
    available_blocks: int
    writable_bits: int
    max_payload_bytes: int
    recommended_max_characters: int
    sufficient: bool


@dataclass
class EmbedResult:
    image: object
    message: str
    protocol_version: int
    width: int
    height: int
    strength: Strength
    channel: Channel
    method: Method


@dataclass(frozen=True)
class DetectionResult:
    found: bool
    valid: bool
    damaged: bool = False
    message: Optional[str] = None
    protocol_version: Optional[int] = None
    crc_valid: bool = False
    ecc_valid: bool = False
    strength: Optional[Strength] = None
    channel: Optional[Channel] = None
    method: Optional[Method] = None
    sync_errors: Optional[int] = None
