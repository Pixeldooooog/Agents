from __future__ import annotations

import re
from typing import Any


LEFT_SINGLE_CURLY_QUOTE = "\u2018"
RIGHT_SINGLE_CURLY_QUOTE = "\u2019"
LEFT_DOUBLE_CURLY_QUOTE = "\u201c"
RIGHT_DOUBLE_CURLY_QUOTE = "\u201d"

DESANITIZATIONS = {
    "<fnr>": "<function_results>",
    "<n>": "<name>",
    "</n>": "</name>",
    "<o>": "<output>",
    "</o>": "</output>",
    "<e>": "<error>",
    "</e>": "</error>",
    "<s>": "<system>",
    "</s>": "</system>",
    "<r>": "<result>",
    "</r>": "</result>",
    "< META_START >": "<META_START>",
    "< META_END >": "<META_END>",
    "< EOT >": "<EOT>",
    "< META >": "<META>",
    "< SOS >": "<SOS>",
    "\n\nH:": "\n\nHuman:",
    "\n\nA:": "\n\nAssistant:",
}


def required_string(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise ValueError("%s is required" % key)
    return value


def required_text(value: Any, key: str) -> str:
    text = str(value or "")
    if not text:
        raise ValueError("%s is required" % key)
    return text


def find_actual_text(content: str, needle: str) -> str | None:
    if needle in content:
        return needle
    normalized_needle = normalize_quotes(needle)
    normalized_content = normalize_quotes(content)
    index = normalized_content.find(normalized_needle)
    if index < 0:
        return None
    return content[index : index + len(needle)]


def normalize_edit_strings(content: str, old_text: str, new_text: str) -> tuple[str, str]:
    if find_actual_text(content, old_text) is not None:
        return old_text, new_text
    desanitized_old_text, replacements = desanitize_match_string(old_text)
    if not replacements:
        return old_text, new_text
    if find_actual_text(content, desanitized_old_text) is None:
        return old_text, new_text
    desanitized_new_text = new_text
    for source, target in replacements:
        desanitized_new_text = desanitized_new_text.replace(source, target)
    return desanitized_old_text, desanitized_new_text


def reject_editing_previous_new_text(old_text: str, previous_new_texts: list[str]) -> None:
    old_text_to_check = re.sub(r"\n+$", "", str(old_text))
    if not old_text_to_check:
        return
    for previous_new_text in previous_new_texts:
        if old_text_to_check in previous_new_text:
            raise ValueError("Cannot edit file: old_text is a substring of a new_text from a previous edit.")


def preserve_quote_style(old_text: str, actual_old_text: str, new_text: str) -> str:
    if old_text == actual_old_text:
        return new_text
    output = str(new_text)
    if LEFT_DOUBLE_CURLY_QUOTE in actual_old_text or RIGHT_DOUBLE_CURLY_QUOTE in actual_old_text:
        output = apply_curly_double_quotes(output)
    if LEFT_SINGLE_CURLY_QUOTE in actual_old_text or RIGHT_SINGLE_CURLY_QUOTE in actual_old_text:
        output = apply_curly_single_quotes(output)
    return output


def edit_target_and_replacement(content: str, old_text: str, new_text: str) -> tuple[str, str]:
    if new_text or old_text.endswith("\n") or old_text.endswith("\r\n"):
        return old_text, new_text
    if old_text + "\r\n" in content:
        return old_text + "\r\n", new_text
    if old_text + "\n" in content:
        return old_text + "\n", new_text
    return old_text, new_text


def normalize_quotes(text: str) -> str:
    return (
        str(text)
        .replace(LEFT_SINGLE_CURLY_QUOTE, "'")
        .replace(RIGHT_SINGLE_CURLY_QUOTE, "'")
        .replace(LEFT_DOUBLE_CURLY_QUOTE, '"')
        .replace(RIGHT_DOUBLE_CURLY_QUOTE, '"')
    )


def desanitize_match_string(text: str) -> tuple[str, list[tuple[str, str]]]:
    result = str(text)
    replacements: list[tuple[str, str]] = []
    for source, target in DESANITIZATIONS.items():
        updated = result.replace(source, target)
        if updated != result:
            replacements.append((source, target))
            result = updated
    return result, replacements


def apply_curly_double_quotes(text: str) -> str:
    chars = list(str(text))
    result: list[str] = []
    for index, char in enumerate(chars):
        if char == '"':
            result.append(LEFT_DOUBLE_CURLY_QUOTE if is_opening_quote_context(chars, index) else RIGHT_DOUBLE_CURLY_QUOTE)
        else:
            result.append(char)
    return "".join(result)


def apply_curly_single_quotes(text: str) -> str:
    chars = list(str(text))
    result: list[str] = []
    for index, char in enumerate(chars):
        if char != "'":
            result.append(char)
            continue
        previous = chars[index - 1] if index > 0 else ""
        next_char = chars[index + 1] if index < len(chars) - 1 else ""
        if previous.isalpha() and next_char.isalpha():
            result.append(RIGHT_SINGLE_CURLY_QUOTE)
        else:
            result.append(LEFT_SINGLE_CURLY_QUOTE if is_opening_quote_context(chars, index) else RIGHT_SINGLE_CURLY_QUOTE)
    return "".join(result)


def is_opening_quote_context(chars: list[str], index: int) -> bool:
    if index == 0:
        return True
    return chars[index - 1] in {" ", "\t", "\n", "\r", "(", "[", "{", "\u2014", "\u2013"}
