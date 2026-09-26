import pytest

from watermark.ecc import ECCError
from watermark.protocol import (
    MAX_CHARACTERS,
    SYNC,
    IntegrityError,
    NotWatermarked,
    ProtocolError,
    build_packet,
    parse_packet,
)


@pytest.mark.parametrize("message", ["hello", "隐藏水印", "日本語テスト", "mark 🔐🌊"])
def test_protocol_utf8_roundtrip(message):
    assert parse_packet(build_packet(message)).message == message


def test_empty_and_oversized_messages_are_rejected():
    with pytest.raises(ProtocolError):
        build_packet("")
    with pytest.raises(ProtocolError):
        build_packet("x" * (MAX_CHARACTERS + 1))
    with pytest.raises(ProtocolError):
        build_packet("界" * 64 + "🔐" * 17)


def test_magic_and_sync_errors_are_rejected():
    packet = bytearray(build_packet("test"))
    packet[0] ^= 0xFF
    with pytest.raises(NotWatermarked):
        parse_packet(bytes(packet))


def test_ecc_repairs_limited_damage():
    packet = bytearray(build_packet("ECC 修复测试"))
    start = len(SYNC)
    for offset in (2, 11, 25, 49, 73, 101, 127, 145):
        packet[start + offset] ^= 0x55
    assert parse_packet(bytes(packet)).message == "ECC 修复测试"


def test_ecc_rejects_excessive_damage():
    packet = bytearray(build_packet("ECC failure"))
    start = len(SYNC)
    for offset in range(0, 48, 2):
        packet[start + offset] ^= 0xA7
    with pytest.raises((ECCError, IntegrityError, ProtocolError)):
        parse_packet(bytes(packet))


def test_crc_rejects_validly_encoded_tamper():
    from watermark.ecc import decode_ecc, encode_ecc

    packet = build_packet("CRC test")
    raw = bytearray(decode_ecc(packet[len(SYNC) :]))
    raw[12] ^= 1
    tampered = SYNC + encode_ecc(bytes(raw))
    with pytest.raises(IntegrityError):
        parse_packet(tampered)
