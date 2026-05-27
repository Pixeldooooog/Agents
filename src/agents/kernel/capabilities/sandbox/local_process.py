from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .types import SandboxBackgroundCommand


def decode_process_output(value: bytes, max_bytes: int) -> str:
    truncated = value[: max(1, max_bytes)]
    suffix = "\n[truncated]" if len(value) > len(truncated) else ""
    return truncated.decode("utf-8", errors="replace") + suffix


def terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return


async def collect_background_process(
    *,
    process: asyncio.subprocess.Process,
    output_file: Path,
    handle: SandboxBackgroundCommand,
    timeout_seconds: float,
    max_output_bytes: int,
) -> None:
    async def read_output() -> None:
        stream = process.stdout
        if stream is None:
            return
        with output_file.open("ab") as file_handle:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                file_handle.write(chunk)
                file_handle.flush()
                handle.output_bytes += len(chunk)

    reader = asyncio.create_task(read_output())
    try:
        await asyncio.wait_for(process.wait(), timeout=float(timeout_seconds or 20.0))
    except asyncio.TimeoutError:
        handle.timed_out = True
        handle.status = "timed_out"
        terminate_process(process)
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
    except asyncio.CancelledError:
        handle.status = "killed"
        terminate_process(process)
        await process.wait()
        raise
    except Exception as exc:  # noqa: BLE001 - background command errors are model-visible state.
        handle.status = "error"
        handle.error = str(exc)
    finally:
        await asyncio.gather(reader, return_exceptions=True)
        await close_subprocess_transport(process)
        handle.output_bytes = safe_size(output_file)
        handle.ended_at = time.time()
        if handle.status == "running":
            handle.exit_code = int(process.returncode or 0)
            handle.status = "completed" if handle.exit_code == 0 else "failed"
        elif handle.status in {"timed_out", "killed"}:
            handle.exit_code = int(process.returncode or -1)
        if handle.output_bytes > max_output_bytes:
            pass


async def close_subprocess_transport(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        transport = getattr(process, "_transport", None)
        if transport is not None:
            transport.close()
        await asyncio.sleep(0)


def safe_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0
