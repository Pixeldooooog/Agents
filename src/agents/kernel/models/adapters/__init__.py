from agents.kernel.models.adapters.claude import ClaudeMessagesAdapter
from agents.kernel.models.adapters.gemini import GeminiGenerateContentAdapter
from agents.kernel.models.adapters.openai_chat import OpenAIChatCompletionsAdapter
from agents.kernel.models.adapters.openai_responses import OpenAIResponsesAdapter


_ADAPTERS = {
    "openai-chat": OpenAIChatCompletionsAdapter,
    "openai-responses": OpenAIResponsesAdapter,
    "claude-messages": ClaudeMessagesAdapter,
    "gemini": GeminiGenerateContentAdapter,
}


def adapter_for_protocol(protocol: str):
    from agents.kernel.models.constants import normalize_protocol

    standard = normalize_protocol(protocol)
    cls = _ADAPTERS.get(standard)
    if cls is None:
        raise ValueError("unsupported model protocol: %s" % protocol)
    return cls()
