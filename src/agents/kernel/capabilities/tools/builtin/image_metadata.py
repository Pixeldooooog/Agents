from __future__ import annotations


JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
WEBP_CHUNK_TYPE_OFFSET = 12
WEBP_CHUNK_PAYLOAD_OFFSET = 20
WEBP_DIMENSION_MASK = 0x3FFF
WEBP_VP8_START_CODE = b"\x9d\x01\x2a"
WEBP_VP8L_SIGNATURE = 0x2F


def detect_image_media_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png" if data else None


def image_dimensions(data: bytes, media_type: str) -> dict[str, int] | None:
    if media_type == "image/png":
        dimensions = _png_dimensions(data)
    elif media_type == "image/gif":
        dimensions = _gif_dimensions(data)
    elif media_type == "image/jpeg":
        dimensions = _jpeg_dimensions(data)
    elif media_type == "image/webp":
        dimensions = _webp_dimensions(data)
    else:
        dimensions = None
    if dimensions is None:
        return None
    width, height = dimensions
    return {
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": width,
        "displayHeight": height,
    }


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return _positive_dimensions(width, height)


def _gif_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or not (data.startswith(b"GIF87a") or data.startswith(b"GIF89a")):
        return None
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    return _positive_dimensions(width, height)


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    length = len(data)
    while index + 3 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        while index < length and data[index] == 0xFF:
            index += 1
        if index >= length:
            return None
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > length:
            return None
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > length:
            return None
        if marker in JPEG_SOF_MARKERS and segment_length >= 7:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return _positive_dimensions(width, height)
        index += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < WEBP_CHUNK_PAYLOAD_OFFSET
        or data[:4] != b"RIFF"
        or data[8:12] != b"WEBP"
    ):
        return None
    chunk_type = data[WEBP_CHUNK_TYPE_OFFSET:WEBP_CHUNK_TYPE_OFFSET + 4]
    chunk_payload = data[WEBP_CHUNK_PAYLOAD_OFFSET:]
    if chunk_type == b"VP8X":
        return _webp_vp8x_dimensions(chunk_payload)
    if chunk_type == b"VP8 ":
        return _webp_vp8_dimensions(chunk_payload)
    if chunk_type == b"VP8L":
        return _webp_vp8l_dimensions(chunk_payload)
    return None


def _webp_vp8x_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 10:
        return None
    width = int.from_bytes(payload[4:7], "little") + 1
    height = int.from_bytes(payload[7:10], "little") + 1
    return _positive_dimensions(width, height)


def _webp_vp8_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 10 or payload[3:6] != WEBP_VP8_START_CODE:
        return None
    width = int.from_bytes(payload[6:8], "little") & WEBP_DIMENSION_MASK
    height = int.from_bytes(payload[8:10], "little") & WEBP_DIMENSION_MASK
    return _positive_dimensions(width, height)


def _webp_vp8l_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 5 or payload[0] != WEBP_VP8L_SIGNATURE:
        return None
    bits = int.from_bytes(payload[1:5], "little")
    width = (bits & WEBP_DIMENSION_MASK) + 1
    height = ((bits >> 14) & WEBP_DIMENSION_MASK) + 1
    return _positive_dimensions(width, height)


def _positive_dimensions(width: int, height: int) -> tuple[int, int] | None:
    if width <= 0 or height <= 0:
        return None
    return width, height
