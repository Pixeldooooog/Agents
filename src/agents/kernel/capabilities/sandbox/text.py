from __future__ import annotations

import os
from pathlib import Path


BINARY_SAMPLE_BYTES = 8192
DEFAULT_TEXT_READ_MAX_BYTES = 256 * 1024
DEFAULT_TEXT_READ_MAX_TOKENS = 25000
TEXT_READ_MAX_TOKENS_ENV = "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS"
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
    if _has_utf16_bom(data):
        return "utf-16"
    if _has_utf8_bom(data):
        return "utf-8-sig"
    if _looks_like_binary_sample(path, data):
        suffix = Path(path).suffix.lower()
        kind = " %s" % suffix if suffix else ""
        raise ValueError(
            "This text tool cannot read binary files. The file appears to be a binary%s file. "
            "Use an appropriate binary analysis tool instead." % kind
        )
    return "utf-8"


def public_encoding_name(encoding: str) -> str:
    if encoding == "utf-16":
        return "utf-16le"
    if encoding == "utf-8-sig":
        return "utf-8-sig"
    return "utf-8"


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
    return data.decode(encoding, errors="replace")


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


def _has_utf16_bom(data: bytes) -> bool:
    return data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff")


def _has_utf8_bom(data: bytes) -> bool:
    return data.startswith(b"\xef\xbb\xbf")


def format_file_size(size_in_bytes: int) -> str:
    size = float(max(0, int(size_in_bytes)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % int(size)
            return "%.1f %s" % (size, unit)
        size /= 1024
