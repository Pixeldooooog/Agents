from __future__ import annotations

import os
from pathlib import Path


BINARY_SAMPLE_BYTES = 8192
DEFAULT_TEXT_READ_MAX_BYTES = 256 * 1024
DEFAULT_TEXT_READ_MAX_TOKENS = 25000
TEXT_READ_MAX_TOKENS_ENV = "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS"
UTF_16LE_BOM = "utf-16"
UTF_16BE_BOM = "utf-16be-bom"
UTF_16LE_NO_BOM = "utf-16le-no-bom"
UTF_16BE_NO_BOM = "utf-16be-no-bom"
BINARY_FILE_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bin",
    ".bmp",
    ".class",
    ".dmg",
    ".doc",
    ".docx",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".wasm",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


def ensure_text_file_bytes(path: str | Path, data: bytes) -> None:
    detect_text_encoding(path, data)


def detect_text_encoding(path: str | Path, data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return UTF_16LE_BOM
    if data.startswith(b"\xfe\xff"):
        return UTF_16BE_BOM
    if _has_utf8_bom(data):
        return "utf-8-sig"
    if Path(path).suffix.lower() not in BINARY_FILE_EXTENSIONS:
        utf16_encoding = _detect_utf16_without_bom(data)
        if utf16_encoding:
            return utf16_encoding
    if _looks_like_binary_sample(path, data):
        suffix = Path(path).suffix.lower()
        kind = " %s" % suffix if suffix else ""
        raise ValueError(
            "This text tool cannot read binary files. The file appears to be a binary%s file. "
            "Use an appropriate binary analysis tool instead." % kind
        )
    return "utf-8"


def public_encoding_name(encoding: str) -> str:
    normalized = _normalize_encoding(encoding)
    if normalized in {UTF_16LE_BOM, UTF_16LE_NO_BOM, "utf-16le", "utf-16-le", "utf16le"}:
        return "utf-16le"
    if normalized in {UTF_16BE_BOM, UTF_16BE_NO_BOM, "utf-16be", "utf-16-be", "utf16be"}:
        return "utf-16be"
    if normalized in {"utf-8-sig", "utf8-sig"}:
        return "utf-8-sig"
    return "utf-8"


def write_encoding_name(encoding: str) -> str:
    normalized = _normalize_encoding(encoding)
    if normalized in {UTF_16LE_BOM, UTF_16BE_BOM, UTF_16LE_NO_BOM, UTF_16BE_NO_BOM, "utf-8-sig"}:
        return normalized
    if normalized == "utf8-sig":
        return "utf-8-sig"
    if normalized in {"utf-16le", "utf-16-le", "utf-16", "utf16le", "utf16"}:
        return UTF_16LE_BOM
    if normalized in {"utf-16be", "utf-16-be", "utf16be"}:
        return UTF_16BE_NO_BOM
    return "utf-8"


def python_text_codec(encoding: str) -> str:
    normalized = write_encoding_name(encoding)
    if normalized == UTF_16BE_BOM:
        return "utf-16"
    if normalized == UTF_16LE_NO_BOM:
        return "utf-16le"
    if normalized == UTF_16BE_NO_BOM:
        return "utf-16be"
    return normalized


def detect_line_endings(content: str) -> str:
    crlf = content.count("\r\n")
    lf = content.count("\n") - crlf
    if crlf > lf:
        return "crlf"
    if crlf or lf:
        return "lf"
    return "none"


def looks_like_binary_file(path: str | Path, data: bytes) -> bool:
    try:
        detect_text_encoding(path, data)
    except ValueError:
        return True
    return False


def decode_text_bytes(data: bytes, encoding: str) -> str:
    return data.decode(python_text_codec(encoding), errors="replace")


def encode_text_bytes(content: str, encoding: str) -> bytes:
    normalized = write_encoding_name(encoding)
    text = str(content)
    if normalized == UTF_16BE_BOM:
        return b"\xfe\xff" + _strip_leading_bom(text).encode("utf-16be", errors="replace")
    if normalized == UTF_16LE_NO_BOM:
        return text.encode("utf-16le", errors="replace")
    if normalized == UTF_16BE_NO_BOM:
        return text.encode("utf-16be", errors="replace")
    return text.encode(normalized, errors="replace")


def normalize_text_read_max_bytes(max_bytes: int | None) -> int:
    return max(1, min(int(max_bytes or DEFAULT_TEXT_READ_MAX_BYTES), DEFAULT_TEXT_READ_MAX_BYTES))


def normalize_text_read_max_tokens(max_tokens: int | None) -> int:
    return max(1, int(max_tokens or default_text_read_max_tokens()))


def default_text_read_max_tokens() -> int:
    value = os.environ.get(TEXT_READ_MAX_TOKENS_ENV)
    if value:
        try:
            parsed = int(value)
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
    return DEFAULT_TEXT_READ_MAX_TOKENS


def estimate_text_read_tokens(content: str, file_extension: str = "") -> int:
    bytes_per_token = 2 if str(file_extension or "").lstrip(".").lower() in {"json", "jsonl", "jsonc"} else 4
    return round(len(content) / bytes_per_token)


def text_file_too_large_message(size_in_bytes: int, max_size_bytes: int) -> str:
    return (
        "File content (%s) exceeds maximum allowed size (%s). "
        "Use offset and limit parameters to read specific portions of the file, "
        "or search for specific content instead of reading the whole file."
    ) % (format_file_size(size_in_bytes), format_file_size(max_size_bytes))


def text_file_too_many_tokens_message(token_count: int, max_tokens: int) -> str:
    return (
        "File content (%d tokens) exceeds maximum allowed tokens (%d). "
        "Use offset and limit parameters to read specific portions of the file, "
        "or search for specific content instead of reading the whole file."
    ) % (token_count, max_tokens)


def _looks_like_binary_sample(path: str | Path, data: bytes) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix in BINARY_FILE_EXTENSIONS:
        return True
    sample = data[:BINARY_SAMPLE_BYTES]
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 12, 13})
    return control / len(sample) > 0.10


def _has_utf8_bom(data: bytes) -> bool:
    return data.startswith(b"\xef\xbb\xbf")


def _detect_utf16_without_bom(data: bytes) -> str:
    sample = data[:BINARY_SAMPLE_BYTES]
    pair_count = len(sample) // 2
    if pair_count < 2:
        return ""
    even_nuls = sum(1 for index in range(0, pair_count * 2, 2) if sample[index] == 0)
    odd_nuls = sum(1 for index in range(1, pair_count * 2, 2) if sample[index] == 0)
    even_ratio = even_nuls / pair_count
    odd_ratio = odd_nuls / pair_count
    if odd_ratio >= 0.25 and even_ratio <= 0.05:
        return UTF_16LE_NO_BOM
    if even_ratio >= 0.25 and odd_ratio <= 0.05:
        return UTF_16BE_NO_BOM
    return ""


def _normalize_encoding(encoding: str) -> str:
    return str(encoding or "utf-8").lower().replace("_", "-")


def _strip_leading_bom(text: str) -> str:
    return text[1:] if text.startswith("\ufeff") else text


def format_file_size(size_in_bytes: int) -> str:
    size = float(max(0, int(size_in_bytes)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024
