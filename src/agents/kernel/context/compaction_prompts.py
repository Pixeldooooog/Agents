from __future__ import annotations

from agents.kernel.schema import Message


NO_TOOLS_PREAMBLE = """CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

- Do NOT use filesystem, shell, browser, MCP, or ANY other tool.
- You already have all the context you need in the conversation below.
- Your entire response must be plain text: an <analysis> block followed by a <summary> block.
"""


COMPACT_SUMMARY_PROMPT = """Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.
This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing development work without losing context.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis process:

1. Chronologically analyze each message and section of the conversation.
2. Identify the user's explicit requests, your approach, key decisions, files, code sections, errors, and fixes.
3. Pay special attention to user feedback and current pending work.

Your summary should include:

1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Current Work
9. Optional Next Step
"""


NO_TOOLS_TRAILER = (
    "\n\nREMINDER: Do NOT call any tools. Respond with plain text only: "
    "an <analysis> block followed by a <summary> block."
)


def compact_summary_system_prompt() -> str:
    return "You are a helpful AI assistant tasked with summarizing conversations."


def compact_summary_user_prompt(messages: list[Message], *, custom_instructions: str = "") -> str:
    prompt = "%s\n\n%s" % (NO_TOOLS_PREAMBLE, COMPACT_SUMMARY_PROMPT)
    if custom_instructions.strip():
        prompt += "\n\nAdditional Instructions:\n%s" % custom_instructions.strip()
    prompt += "\n\nConversation to summarize:\n\n%s" % _transcript(messages)
    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(summary: str) -> str:
    text = str(summary or "")
    text = _strip_tagged_section(text, "analysis")
    extracted = _extract_tagged_section(text, "summary")
    if extracted is not None:
        text = "Summary:\n%s" % extracted.strip()
    return "\n\n".join(part.strip() for part in text.split("\n\n") if part.strip())


def _transcript(messages: list[Message]) -> str:
    lines: list[str] = []
    for message in messages:
        text = " ".join(message.content_text().split())
        if not text and message.tool_calls:
            text = "tool calls: %s" % ", ".join(call.name for call in message.tool_calls)
        if not text:
            continue
        lines.append("%s: %s" % (message.role, text))
    return "\n".join(lines)


def _strip_tagged_section(text: str, tag: str) -> str:
    start = text.find("<%s>" % tag)
    end = text.find("</%s>" % tag)
    if start == -1 or end == -1 or end < start:
        return text
    return text[:start] + text[end + len(tag) + 3 :]


def _extract_tagged_section(text: str, tag: str) -> str | None:
    start_token = "<%s>" % tag
    end_token = "</%s>" % tag
    start = text.find(start_token)
    end = text.find(end_token)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start + len(start_token) : end]
