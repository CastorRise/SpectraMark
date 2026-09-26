from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from .ecc import CODEWORD_BYTES, DATA_CHUNK_BYTES, decode_ecc, encode_ecc

MAGIC = b"HWMK\x89\r\n\x1a"
SYNC = bytes.fromhex("d3916af03c5aa5c7690f96e1c33c5aa5")
VERSION = 1
MAX_CHARACTERS = 64
MAX_PAYLOAD_BYTES = 256
HEADER_SIZE = len(MAGIC) + 1 + 1 + 2
RAW_FRAME_SIZE = DATA_CHUNK_BYTES * 2
ENCODED_FRAME_SIZE = CODEWORD_BYTES * 2
PACKET_SIZE = len(SYNC) + ENCODED_FRAME_SIZE
PACKET_BITS = PACKET_SIZE * 8


class ProtocolError(ValueError):
    pass


class NotWatermarked(ProtocolError):
    pass


class UnsupportedVersion(ProtocolError):
    pass


class IntegrityError(ProtocolError):
    pass


@dataclass(frozen=True)
class DecodedPacket:
    message: str
    version: int
    flags: int
    crc_valid: bool
    ecc_valid: bool


def validate_message(message: str) -> bytes:
    if not message:
        raise ProtocolError("水印内容不能为空。")
    if len(message) > MAX_CHARACTERS:
        raise ProtocolError(f"水印内容不能超过 {MAX_CHARACTERS} 个字符。")
    payload = message.encode("utf-8")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError(f"水印内容的 UTF-8 数据不能超过 {MAX_PAYLOAD_BYTES} 字节。")
    return payload


def build_packet(message: str, flags: int = 0) -> bytes:
    payload = validate_message(message)
    header = MAGIC + bytes((VERSION, flags & 0xFF)) + struct.pack(">H", len(payload))
    padded_payload = payload.ljust(MAX_PAYLOAD_BYTES, b"\x00")
    checksum = zlib.crc32(header + payload) & 0xFFFFFFFF
    raw = header + padded_payload + struct.pack(">I", checksum)
    if len(raw) != RAW_FRAME_SIZE:
        raise AssertionError("Protocol frame has an unexpected size")
    return SYNC + encode_ecc(raw)


def parse_packet(packet: bytes) -> DecodedPacket:
    if len(packet) != PACKET_SIZE:
        raise ProtocolError("Invalid packet size")
    if packet[: len(SYNC)] != SYNC:
        raise NotWatermarked("Synchronization marker not found")
    raw = decode_ecc(packet[len(SYNC) :])
    if raw[: len(MAGIC)] != MAGIC:
        raise NotWatermarked("Magic header mismatch")
    version = raw[len(MAGIC)]
    if version != VERSION:
        raise UnsupportedVersion("Unsupported watermark protocol version")
    flags = raw[len(MAGIC) + 1]
    length = struct.unpack(">H", raw[len(MAGIC) + 2 : HEADER_SIZE])[0]
    if length > MAX_PAYLOAD_BYTES:
        raise IntegrityError("Payload length is outside the protocol limit")
    payload = raw[HEADER_SIZE : HEADER_SIZE + length]
    expected = struct.unpack(">I", raw[-4:])[0]
    actual = zlib.crc32(raw[:HEADER_SIZE] + payload) & 0xFFFFFFFF
    if expected != actual:
        raise IntegrityError("CRC32 mismatch")
    try:
        message = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrityError("Payload is not valid UTF-8") from exc
    validate_message(message)
    return DecodedPacket(message, version, flags, crc_valid=True, ecc_valid=True)
