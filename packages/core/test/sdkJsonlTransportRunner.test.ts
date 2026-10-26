import { describe, expect, test } from "bun:test";
import {
  createSdkControlSuccessResponse,
  decodeSdkJsonlLine,
  encodeSdkJsonlMessage,
  SdkStdinDecodeError,
  SdkJsonlTransportRunner,
  SdkQueueJsonlTransport,
  SdkStructuredIo,
  type SdkMessage,
  type SdkWireMessage
} from "@kevin/core/sdk";

describe("SDK JSONL transport runner", () => {
  test("emits accepted inbound wire messages", async () => {
    const transport = new SdkQueueJsonlTransport();
    const observed: SdkWireMessage[] = [];
    const runner = new SdkJsonlTransportRunner(transport, { onInboundMessage: (message) => observed.push(message) });
    const userMessage: SdkMessage = {
      type: "user_message",
      uuid: "message_1",
      sessionId: "session_1",
      content: "hello"
    };
    const received = collectMessages(runner.messages());

    transport.send(encodeSdkJsonlMessage(userMessage));
    transport.closeInput();

    expect(await received).toEqual([userMessage]);
    expect(observed).toEqual([userMessage]);
    await runner.wait();
    expect(transport.isClosed).toBe(true);
  });

  test("pumps structured IO outbound messages and resolves inbound control responses", async () => {
    const transport = new SdkQueueJsonlTransport();
    const structuredIo = new SdkStructuredIo();
    const runner = new SdkJsonlTransportRunner(transport, { structuredIo });
    runner.start();

    const result = structuredIo.sendRequest({ subtype: "get_settings" }, { requestId: "settings_1" });
    const outboundLine = await transport.receive();
    expect(decodeSdkJsonlLine(String(outboundLine).trim())).toEqual({
      type: "control_request",
      requestId: "settings_1",
      request: { subtype: "get_settings" }
    });

    transport.send(encodeSdkJsonlMessage(createSdkControlSuccessResponse("settings_1", { model: "mock" })));
    expect(await result).toEqual({ model: "mock" });

    transport.closeInput();
    await runner.wait();
  });

  test("reports JSONL decode errors through messages, wait, and onError", async () => {
    const transport = new SdkQueueJsonlTransport();
    const errors: unknown[] = [];
    const runner = new SdkJsonlTransportRunner(transport, { onError: (error) => errors.push(error) });
    const waitError = runner.wait().then(() => undefined, (error) => error);
    const receivedError = collectMessages(runner.messages()).then(() => undefined, (error) => error);

    transport.send("{broken\n");

    expect(await receivedError).toBeInstanceOf(SdkStdinDecodeError);
    expect(await waitError).toBeInstanceOf(SdkStdinDecodeError);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toBeInstanceOf(SdkStdinDecodeError);
    expect(transport.isClosed).toBe(true);
  });

  test("closes the transport and structured IO explicitly", async () => {
    const transport = new SdkQueueJsonlTransport();
    const structuredIo = new SdkStructuredIo();
    const runner = new SdkJsonlTransportRunner(transport, { structuredIo });
    runner.start();
    structuredIo.write({
      type: "control_response",
      response: {
        subtype: "success",
        requestId: "queued_1",
        response: { ok: true }
      }
    });

    await runner.close();

    expect(decodeSdkJsonlLine(String(await transport.receive()).trim())).toMatchObject({
      type: "control_response",
      response: {
        requestId: "queued_1"
      }
    });
    expect(transport.isClosed).toBe(true);
    expect(structuredIo.isClosed).toBe(true);
  });

  test("leaves caller-owned transports open when configured", async () => {
    const transport = new SdkQueueJsonlTransport();
    const runner = new SdkJsonlTransportRunner(transport, { closeTransport: false });
    const received = collectMessages(runner.messages());

    transport.closeInput();

    expect(await received).toEqual([]);
    await runner.wait();
    expect(transport.isClosed).toBe(false);
    transport.close();
  });
});

async function collectMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}
