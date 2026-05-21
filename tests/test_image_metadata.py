from __future__ import annotations

from agents.kernel.capabilities.tools.builtin.image_metadata import (
    detect_image_media_type,
    image_dimensions,
)


def test_detects_common_image_dimensions():
    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02"
        b"\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
    )
    gif = b"GIF89a" + (4).to_bytes(2, "little") + (5).to_bytes(2, "little")
    jpeg = (
        b"\xff\xd8"
        b"\xff\xe0\x00\x04xx"
        b"\xff\xc0\x00\x11\x08"
        b"\x00\x07"
        b"\x00\x06"
        b"\x00" * 10
    )

    assert detect_image_media_type(png) == "image/png"
    assert image_dimensions(png, "image/png") == _dimensions(2, 3)
    assert detect_image_media_type(gif) == "image/gif"
    assert image_dimensions(gif, "image/gif") == _dimensions(4, 5)
    assert detect_image_media_type(jpeg) == "image/jpeg"
    assert image_dimensions(jpeg, "image/jpeg") == _dimensions(6, 7)


def test_detects_webp_dimension_variants():
    vp8x = _webp_vp8x(8, 9)
    vp8 = _webp_vp8(10, 11)
    vp8l = _webp_vp8l(12, 13)

    assert detect_image_media_type(vp8x) == "image/webp"
    assert image_dimensions(vp8x, "image/webp") == _dimensions(8, 9)
    assert detect_image_media_type(vp8) == "image/webp"
    assert image_dimensions(vp8, "image/webp") == _dimensions(10, 11)
    assert detect_image_media_type(vp8l) == "image/webp"
    assert image_dimensions(vp8l, "image/webp") == _dimensions(12, 13)


def test_unknown_non_empty_image_defaults_to_png_without_dimensions():
    data = b"not really an image"

    assert detect_image_media_type(data) == "image/png"
    assert image_dimensions(data, "image/png") is None


def _dimensions(width: int, height: int) -> dict[str, int]:
    return {
        "originalWidth": width,
        "originalHeight": height,
        "displayWidth": width,
        "displayHeight": height,
    }


def _webp_vp8x(width: int, height: int) -> bytes:
    return (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8X"
        + (10).to_bytes(4, "little")
        + b"\x00\x00\x00\x00"
        + (width - 1).to_bytes(3, "little")
        + (height - 1).to_bytes(3, "little")
    )


def _webp_vp8(width: int, height: int) -> bytes:
    return (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8 "
        + (10).to_bytes(4, "little")
        + b"\x00\x00\x00"
        + b"\x9d\x01\x2a"
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
    )


def _webp_vp8l(width: int, height: int) -> bytes:
    bits = (width - 1) | ((height - 1) << 14)
    return (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8L"
        + (5).to_bytes(4, "little")
        + b"\x2f"
        + bits.to_bytes(4, "little")
    )
