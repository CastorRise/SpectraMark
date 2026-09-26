from __future__ import annotations

from reedsolo import ReedSolomonError, RSCodec

ECC_BYTES = 32
DATA_CHUNK_BYTES = 136
CODEWORD_BYTES = DATA_CHUNK_BYTES + ECC_BYTES
_CODEC = RSCodec(ECC_BYTES)


class ECCError(ValueError):
    pass


def encode_ecc(data: bytes) -> bytes:
    if len(data) % DATA_CHUNK_BYTES:
        raise ValueError("ECC input must use complete fixed-size chunks")
    return b"".join(
        bytes(_CODEC.encode(data[offset : offset + DATA_CHUNK_BYTES]))
        for offset in range(0, len(data), DATA_CHUNK_BYTES)
    )


def decode_ecc(encoded: bytes) -> bytes:
    if len(encoded) % CODEWORD_BYTES:
        raise ECCError("Invalid ECC codeword length")
    decoded = bytearray()
    try:
        for offset in range(0, len(encoded), CODEWORD_BYTES):
            block = encoded[offset : offset + CODEWORD_BYTES]
            result = _CODEC.decode(block)
            decoded.extend(bytes(result[0]))
    except ReedSolomonError as exc:
        raise ECCError("Reed-Solomon recovery failed") from exc
    return bytes(decoded)
