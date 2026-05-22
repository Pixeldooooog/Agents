from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Any, Callable

from agents.kernel.capabilities.tools.context import ToolRuntimeContext


LSP_OPERATIONS = (
    "goToDefinition",
    "findReferences",
    "hover",
    "documentSymbol",
    "workspaceSymbol",
    "goToImplementation",
    "prepareCallHierarchy",
    "incomingCalls",
    "outgoingCalls",
)
MAX_LSP_FILE_SIZE_BYTES = 10 * 1024 * 1024

LSP_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": list(LSP_OPERATIONS),
            "description": "Language-server operation to run.",
        },
        "filePath": {"type": "string", "description": "Workspace-relative source file path."},
        "line": {"type": "integer", "minimum": 1, "description": "1-based line number."},
        "character": {"type": "integer", "minimum": 1, "description": "1-based character number."},
    },
    "required": ["operation", "filePath", "line", "character"],
    "additionalProperties": False,
}


async def lsp_query(
    context: ToolRuntimeContext,
    *,
    operation: str,
    filePath: str,
    line: int,
    character: int,
) -> dict[str, Any]:
    if operation not in LSP_OPERATIONS:
        raise ValueError("Unsupported LSP operation: %s" % operation)
    _validate_positive_position(line=line, character=character)
    file_path = str(filePath or "")
    absolute_path, file_size = _validate_lsp_file(context, file_path)
    if file_size > MAX_LSP_FILE_SIZE_BYTES:
        return _lsp_payload(
            operation=operation,
            file_path=file_path,
            result="File too large for LSP analysis (%dMB exceeds 10MB limit)"
            % math.ceil(file_size / (1024 * 1024)),
        )

    provider = context.lsp_provider
    if provider is None:
        return _no_lsp_server_payload(operation=operation, file_path=file_path)

    response = await _query_provider(
        provider,
        operation=operation,
        file_path=file_path,
        absolute_path=absolute_path,
        line=line,
        character=character,
    )
    if response is None:
        return _no_lsp_server_payload(operation=operation, file_path=file_path)
    return _coerce_lsp_response(response, operation=operation, file_path=file_path)


def format_lsp_result(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("result") or "")
    return str(result or "")


def _validate_positive_position(*, line: int, character: int) -> None:
    if line < 1:
        raise ValueError("line must be a positive integer")
    if character < 1:
        raise ValueError("character must be a positive integer")


def _validate_lsp_file(context: ToolRuntimeContext, file_path: str) -> tuple[Path, int]:
    try:
        decision = context.sandbox.authorize_file_read(file_path)
    except PermissionError:
        raise
    if not decision.allowed:
        raise PermissionError(decision.reason or "file read disabled")

    absolute_path = context.sandbox.resolve_workspace_path(file_path)
    try:
        stat = absolute_path.stat()
    except FileNotFoundError as exc:
        raise ValueError("File does not exist: %s" % file_path) from exc
    except OSError as exc:
        raise ValueError("Cannot access file: %s. %s" % (file_path, exc)) from exc
    if not absolute_path.is_file():
        raise ValueError("Path is not a file: %s" % file_path)
    return absolute_path, int(stat.st_size)


async def _query_provider(
    provider: Any,
    *,
    operation: str,
    file_path: str,
    absolute_path: Path,
    line: int,
    character: int,
) -> Any:
    callback = _provider_callback(provider)
    request = {
        "operation": operation,
        "filePath": file_path,
        "file_path": file_path,
        "absolute_path": absolute_path,
        "line": line,
        "character": character,
    }
    result = callback(**_provider_kwargs(callback, request))
    if inspect.isawaitable(result):
        result = await result
    return result


def _provider_callback(provider: Any) -> Callable[..., Any]:
    query = getattr(provider, "query", None)
    if callable(query):
        return query
    if callable(provider):
        return provider
    raise TypeError("LSP provider must expose query(...) or be callable")


def _provider_kwargs(callback: Callable[..., Any], request: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return request
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return request
    return {name: value for name, value in request.items() if name in signature.parameters}


def _coerce_lsp_response(response: Any, *, operation: str, file_path: str) -> dict[str, Any]:
    if isinstance(response, dict):
        payload = _lsp_payload(
            operation=str(response.get("operation") or operation),
            file_path=str(response.get("filePath") or response.get("file_path") or file_path),
            result=str(response.get("result") or ""),
        )
        _copy_optional_int(response, payload, "resultCount")
        _copy_optional_int(response, payload, "fileCount")
        return payload
    return _lsp_payload(operation=operation, file_path=file_path, result=_stringify_response(response))


def _copy_optional_int(source: dict[str, Any], target: dict[str, Any], key: str) -> None:
    if key not in source:
        return
    try:
        target[key] = int(source[key])
    except (TypeError, ValueError):
        return


def _no_lsp_server_payload(*, operation: str, file_path: str) -> dict[str, Any]:
    return _lsp_payload(
        operation=operation,
        file_path=file_path,
        result="No LSP server available for file type: %s" % Path(file_path).suffix,
    )


def _lsp_payload(*, operation: str, file_path: str, result: str) -> dict[str, Any]:
    return {"operation": operation, "result": result, "filePath": file_path}


def _stringify_response(response: Any) -> str:
    if isinstance(response, str):
        return response
    return json.dumps(response, default=str, ensure_ascii=False, sort_keys=True)
