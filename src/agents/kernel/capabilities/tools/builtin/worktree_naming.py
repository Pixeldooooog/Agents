from __future__ import annotations

import re
import uuid
from pathlib import Path


MAX_WORKTREE_SLUG_LENGTH = 64
VALID_WORKTREE_SLUG_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_worktree_slug(slug: str) -> None:
    value = str(slug or "")
    if len(value) > MAX_WORKTREE_SLUG_LENGTH:
        raise ValueError("Invalid worktree name: must be %d characters or fewer" % MAX_WORKTREE_SLUG_LENGTH)
    for segment in value.split("/"):
        if segment in {"", ".", ".."}:
            raise ValueError('Invalid worktree name "%s": must not contain empty, "." or ".." path segments' % value)
        if not VALID_WORKTREE_SLUG_SEGMENT.match(segment):
            raise ValueError(
                'Invalid worktree name "%s": each "/"-separated segment must contain only letters, digits, dots, underscores, and dashes'
                % value
            )


def worktree_request(
    name: str,
    *,
    pr_number: int | None,
    pr_number_alias: int | None = None,
) -> tuple[str, int | None]:
    value = str(name or "").strip()
    parsed_pr_number = _parse_pr_reference(value) if value else None
    explicit_pr_number = _explicit_pr_number(pr_number, pr_number_alias)
    if parsed_pr_number is not None and explicit_pr_number is not None and parsed_pr_number != explicit_pr_number:
        raise ValueError("Conflicting pull request references: name=%s pr_number=%s" % (value, explicit_pr_number))
    resolved_pr_number = explicit_pr_number if explicit_pr_number is not None else parsed_pr_number
    if resolved_pr_number is not None:
        return worktree_slug("pr-%d" % resolved_pr_number), resolved_pr_number
    return worktree_slug(value), None


def worktree_slug(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        value = "worktree-%s" % uuid.uuid4().hex[:8]
    validate_worktree_slug(value)
    return value


def worktree_branch_name(slug: str) -> str:
    return "worktree-%s" % flatten_worktree_slug(slug)


def worktree_path_for(repo_root: Path, slug: str) -> Path:
    return (repo_root / ".agents" / "worktrees" / flatten_worktree_slug(slug)).resolve()


def flatten_worktree_slug(slug: str) -> str:
    return slug.replace("/", "+")


def _positive_pr_number(value: int | None) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number <= 0:
        raise ValueError("pr_number must be a positive integer")
    return number


def _explicit_pr_number(pr_number: int | None, pr_number_alias: int | None) -> int | None:
    snake = _positive_pr_number(pr_number)
    camel = _positive_pr_number(pr_number_alias)
    if snake is not None and camel is not None and snake != camel:
        raise ValueError("Conflicting pull request numbers: pr_number=%s prNumber=%s" % (snake, camel))
    return snake if snake is not None else camel


def _parse_pr_reference(value: str) -> int | None:
    text = str(value or "").strip()
    url_match = re.match(r"^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)/?(?:[?#].*)?$", text, flags=re.IGNORECASE)
    if url_match:
        return int(url_match.group(1))
    hash_match = re.match(r"^#(\d+)$", text)
    if hash_match:
        return int(hash_match.group(1))
    return None
