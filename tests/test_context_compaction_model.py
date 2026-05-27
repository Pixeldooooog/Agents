import asyncio

from agents.kernel.context.compaction_model import ModelContextCompactor
from agents.kernel.context.window import ContextWindowManager
from agents.kernel.schema import Message, ModelResponse


class RecordingModelClient:
    def __init__(self, text: str | Exception):
        self.text = text
        self.requests = []

    async def async_complete(self, request_data):
        self.requests.append(request_data)
        if isinstance(self.text, Exception):
            raise self.text
        return ModelResponse(message=Message.from_text("assistant", self.text))


def test_model_context_compactor_builds_src_origin_style_summary_request():
    client = RecordingModelClient("<analysis>draft</analysis><summary>Keep the architecture split.</summary>")
    compactor = ModelContextCompactor(client, protocol="scripted", model="compact-model")
    messages = [
        Message.from_text("user", "old request " * 80),
        Message.from_text("assistant", "old answer " * 80),
        Message.from_text("user", "recent request"),
    ]

    compaction = asyncio.run(compactor.acompact(messages, max_context_tokens=20, target_tokens=8))

    assert compaction.summary == "Summary:\nKeep the architecture split."
    assert compaction.summary_source == "model"
    assert compaction.dropped_messages == 2
    assert compaction.kept_messages == [messages[-1]]
    request = client.requests[0]
    assert request.model == "compact-model"
    assert request.metadata["query_source"] == "compact"
    assert request.metadata["is_compaction"] is True
    assert "Respond with TEXT ONLY" in request.messages[1].content_text()
    assert "old request" in request.messages[1].content_text()


def test_model_context_compactor_falls_back_to_heuristic_summary():
    client = RecordingModelClient(RuntimeError("network unavailable"))
    compactor = ModelContextCompactor(client, protocol="scripted", model="compact-model")
    messages = [
        Message.from_text("user", "old request " * 80),
        Message.from_text("assistant", "old answer " * 80),
        Message.from_text("user", "recent request"),
    ]

    compaction = asyncio.run(compactor.acompact(messages, max_context_tokens=20, target_tokens=8))

    assert compaction.summary_source == "heuristic_fallback"
    assert "Prior conversation summary" in compaction.summary
    assert compaction.kept_messages == [messages[-1]]


def test_context_window_async_fit_uses_model_compactor():
    client = RecordingModelClient("<summary>Older work was summarized.</summary>")
    manager = ContextWindowManager(
        max_context_tokens=30,
        compaction_target_tokens=8,
        compactor=ModelContextCompactor(client, protocol="scripted", model="compact-model"),
    )
    messages = [
        Message.from_text("system", "Base instructions."),
        Message.from_text("user", "old request " * 80),
        Message.from_text("assistant", "old answer " * 80),
        Message.from_text("user", "recent request"),
    ]

    fitted = asyncio.run(manager.afit(messages))

    assert fitted[0].role == "system"
    assert fitted[1].content_text() == "Summary:\nOlder work was summarized."
    assert fitted[-1] == messages[-1]
