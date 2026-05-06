from agents.interfaces.server.http import responses


class RecordingLogger:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args)

    def error(self, message, *args):
        self.messages.append(message % args)


def test_response_logging_does_not_dump_success_payload(monkeypatch):
    logger = RecordingLogger()
    monkeypatch.setattr(responses, "logger", logger)

    responses.ok(responses.Resp(data={"secret": "model output"}))

    assert logger.messages
    assert "model output" not in logger.messages[0]
    assert "secret" not in logger.messages[0]


def test_response_logging_does_not_dump_failure_detail(monkeypatch):
    logger = RecordingLogger()
    monkeypatch.setattr(responses, "logger", logger)

    responses.fail(responses.Resp(code="500", detail={"secret": "tool result"}, http_status=500))

    assert logger.messages
    assert "tool result" not in logger.messages[0]
    assert "secret" not in logger.messages[0]
