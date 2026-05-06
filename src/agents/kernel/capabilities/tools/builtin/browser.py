from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

from agents.kernel.capabilities.tools.context import ToolRuntimeContext
from agents.kernel.state.artifacts import ArtifactRecord


BROWSER_OPEN_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "HTTP or HTTPS URL to fetch inside the sandbox."},
        "output_path": {
            "type": "string",
            "description": "Workspace-relative file path for the fetched page.",
        },
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 2000000},
    },
    "required": ["url"],
}

BROWSER_DOWNLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "HTTP or HTTPS URL to download inside the sandbox."},
        "path": {"type": "string", "description": "Workspace-relative output file path."},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 20000000},
    },
    "required": ["url"],
}


async def browser_open(
    context: ToolRuntimeContext,
    url: str,
    output_path: str = "",
    max_bytes: int = 200000,
) -> dict[str, Any]:
    requested_path = str(output_path or "")
    blob_location = None
    if not requested_path:
        blob_location = context.allocate_artifact_blob("downloads", "browser-open.html")
        output_path = context.artifact_destination_path(blob_location)
    return await _fetch_to_workspace(
        context,
        url=url,
        output_path=output_path,
        max_bytes=max_bytes,
        text_mode=True,
        artifact_kind="browser_open",
        artifact_role="tool_artifact" if not requested_path else "workspace_output",
        blob_location=blob_location,
    )


async def browser_download(
    context: ToolRuntimeContext,
    url: str,
    path: str = "",
    max_bytes: int = 20000000,
) -> dict[str, Any]:
    requested_path = str(path or "")
    blob_location = None
    if not requested_path:
        blob_location = context.allocate_artifact_blob("downloads", "download.bin")
        path = context.artifact_destination_path(blob_location)
    return await _fetch_to_workspace(
        context,
        url=url,
        output_path=path,
        max_bytes=max_bytes,
        text_mode=False,
        artifact_kind="download",
        artifact_role="tool_artifact" if not requested_path else "workspace_output",
        blob_location=blob_location,
    )


async def _fetch_to_workspace(
    context: ToolRuntimeContext,
    *,
    url: str,
    output_path: str,
    max_bytes: int,
    text_mode: bool,
    artifact_kind: str,
    artifact_role: str,
    blob_location: Any = None,
) -> dict[str, Any]:
    network = context.sandbox.authorize_network()
    if not network.allowed:
        raise PermissionError(network.reason)
    if blob_location is None:
        write = context.sandbox.authorize_file_write(output_path)
        if not write.allowed:
            raise PermissionError(write.reason)
        output_path = context.sandbox.relative_workspace_path(output_path)
    _validate_url(url)
    limit = max(1, min(int(max_bytes or 200000), 20000000))
    script = r"""
import json
import pathlib
import sys
import urllib.request

url = sys.argv[1]
output = pathlib.Path(sys.argv[2])
limit = int(sys.argv[3])
text_mode = sys.argv[4] == "1"
request = urllib.request.Request(url, headers={"User-Agent": "AgentsSandbox/0.1"})
with urllib.request.urlopen(request, timeout=20) as response:
    body = response.read(limit + 1)
    truncated = len(body) > limit
    body = body[:limit]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    payload = {
        "url": url,
        "path": output.as_posix(),
        "status": getattr(response, "status", 0),
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(body),
        "truncated": truncated,
    }
    if text_mode:
        payload["text_preview"] = body[:4000].decode("utf-8", errors="replace")
    sys.stdout.write(json.dumps(payload))
"""
    command = "python3 -c %s %s %s %s %s" % (
        shlex.quote(script),
        shlex.quote(str(url)),
        shlex.quote(str(output_path)),
        shlex.quote(str(limit)),
        "1" if text_mode else "0",
    )
    result = await context.sandbox_client.run_command(command, timeout_seconds=30.0)
    if result.exit_code != 0:
        raise RuntimeError(result.stderr or result.stdout or "browser fetch failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("browser fetch returned invalid JSON") from exc
    await _record_artifact(context, payload, kind=artifact_kind, role=artifact_role, blob_location=blob_location)
    return payload


def _validate_url(url: str) -> None:
    if not str(url).startswith(("http://", "https://")):
        raise ValueError("browser tools only support http:// and https:// URLs")


async def _record_artifact(
    context: ToolRuntimeContext,
    payload: dict[str, Any],
    *,
    kind: str,
    role: str,
    blob_location: Any = None,
) -> None:
    artifact_store = getattr(context, "artifact_store", None)
    workspace = getattr(context, "workspace", None)
    if artifact_store is None or workspace is None:
        return
    output_path = str(payload.get("path") or "")
    if not output_path:
        return
    if blob_location is not None:
        file_path = blob_location.host_path
        uri = blob_location.uri
        workspace_path = ""
    else:
        file_path = workspace.path / output_path
        uri = file_path.as_posix()
        workspace_path = output_path
    try:
        stat = file_path.stat()
        digest = _sha256(file_path)
    except OSError:
        stat = None
        digest = ""
    record = ArtifactRecord.for_workspace(
        workspace,
        run_id=getattr(context, "current_run_id", "") or "manual",
        task_id=getattr(context, "current_task_id", ""),
        tool_call_id=getattr(context, "current_tool_call_id", ""),
        kind=kind,
        role=role,
        storage_backend="local",
        uri=uri,
        workspace_path=workspace_path,
        mime_type=str(payload.get("content_type") or ""),
        size_bytes=int(stat.st_size if stat is not None else payload.get("bytes") or 0),
        sha256=digest,
        metadata={
            "url": str(payload.get("url") or ""),
            "status": str(payload.get("status") or ""),
            "truncated": str(bool(payload.get("truncated"))).lower(),
        },
    )
    await artifact_store.save_artifact(record)
    payload["artifact"] = record.to_dict()
    if blob_location is not None:
        payload["path"] = record.uri


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
