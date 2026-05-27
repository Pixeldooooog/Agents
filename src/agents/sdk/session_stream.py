from __future__ import annotations

import inspect
from typing import Any, AsyncIterator

from agents.kernel.schema import RuntimeEvent


async def iter_session_stream(
    session: Any,
    text: str,
    *,
    run_id: str,
    user_message_id: str = "",
) -> AsyncIterator[RuntimeEvent]:
    kwargs: dict[str, Any] = {"run_id": run_id}
    if user_message_id and _stream_accepts_user_message_id(session):
        kwargs["user_message_id"] = user_message_id
    async for event in session.stream(text, **kwargs):
        yield event


def _stream_accepts_user_message_id(session: Any) -> bool:
    try:
        parameters = inspect.signature(session.stream).parameters
    except (TypeError, ValueError):
        return False
    if "user_message_id" in parameters:
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
