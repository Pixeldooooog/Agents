import { describe, expect, test } from "bun:test";
import {
  createSdkControlSuccessResponse,
  SDKStructuredIO,
  SdkControlRequestCancelledError,
  SdkControlRequestError,
  SdkControlStreamClosedError,
  SdkStructuredIo,
  type SdkControlRequestMessage
} from "@agents/core/sdk";

describe("SDK structured IO", () => {
  test("queues control requests and resolves successful responses", async () => {
    const io = new SdkStructuredIo();
    const result = io.sendRequest({
      subtype: "initialize",
      systemPrompt: "system"
    }, {
      requestId: "request_1",
      responseValidator: (payload) => String(payload.model || "")
    });

    expect(await io.nextOutboundMessage()).toEqual({
      type: "control_request",
      requestId: "request_1",
      request: {
        subtype: "initialize",
        systemPrompt: "system"
      }
    });
    expect(io.pendingCount).toBe(1);

    await io.receive(createSdkControlSuccessResponse("request_1", { model: "claude" }));

    expect(await result).toBe("claude");
    expect(io.pendingCount).toBe(0);
  });

  test("validates structured IO stdin and stdout boundaries", async () => {
    const io = new SdkStructuredIo();

    expect(() => io.write({
      type: "update_environment_variables",
      variables: { SDK_BOUNDARY_TEST: "1" }
    } as any)).toThrow("update_environment_variables is not a valid SDK stdout message");
    await expect(io.receive({
      type: "control_cancel_request",
      requestId: "cancel_1"
    } as any)).rejects.toThrow("control_cancel_request is not a valid SDK stdin message");
  });

  test("tracks permission requests, cancellation, and duplicate tool responses", async () => {
    const sentPermissionRequests: SdkControlRequestMessage[] = [];
    const resolvedRequestIds: string[] = [];
    const io = new SdkStructuredIo({
      onControlRequestSent: (request) => sentPermissionRequests.push(request),
      onControlRequestResolved: (requestId) => resolvedRequestIds.push(requestId)
    });
    const result = io.sendRequest({
      subtype: "can_use_tool",
      toolName: "filesystem.read",
      input: { path: "note.txt" },
      toolUseId: "tool_1"
    }, { requestId: "permission_1" });

    expect((await io.nextOutboundMessage() as SdkControlRequestMessage).request.subtype).toBe("can_use_tool");
    expect(io.getPendingPermissionRequests()).toHaveLength(1);
    expect(sentPermissionRequests).toHaveLength(1);

    await io.receive(createSdkControlSuccessResponse("permission_1", { behavior: "allow", toolUseId: "tool_1" }));

    expect(await result).toEqual({ behavior: "allow", toolUseId: "tool_1" });
    expect(resolvedRequestIds).toEqual(["permission_1"]);
    expect(await io.receive(createSdkControlSuccessResponse("permission_1", { toolUseId: "tool_1" }))).toBeUndefined();
    expect(await io.receive(createSdkControlSuccessResponse("permission_legacy_1", { toolUseID: "tool_1" }))).toBeUndefined();
    expect(await io.receive(createSdkControlSuccessResponse("permission_snake_1", { tool_use_id: "tool_1" }))).toBeUndefined();
  });

  test("rejects canceled, errored, and closed pending control requests", async () => {
    const cancelIo = new SdkStructuredIo();
    const canceled = cancelIo.sendRequest({ subtype: "interrupt" }, { requestId: "cancel_1" });
    await cancelIo.nextOutboundMessage();
    await cancelIo.cancelRequest("cancel_1");
    expect(await cancelIo.nextOutboundMessage()).toEqual({ type: "control_cancel_request", requestId: "cancel_1" });
    await expect(canceled).rejects.toBeInstanceOf(SdkControlRequestCancelledError);

    const errorIo = new SdkStructuredIo();
    const errored = errorIo.sendRequest({ subtype: "get_settings" }, { requestId: "error_1" });
    await errorIo.nextOutboundMessage();
    await errorIo.receive({ type: "control_response", response: { subtype: "error", requestId: "error_1", error: "denied" } });
    await expect(errored).rejects.toBeInstanceOf(SdkControlRequestError);

    const closeIo = new SdkStructuredIo();
    const closed = closeIo.sendRequest({ subtype: "mcp_status" }, { requestId: "close_1" });
    await closeIo.nextOutboundMessage();
    closeIo.close();
    await expect(closed).rejects.toBeInstanceOf(SdkControlStreamClosedError);
    expect(await closeIo.nextOutboundMessage()).toBeUndefined();
  });

  test("validates injected control responses before resolving pending requests", async () => {
    const io = new SdkStructuredIo();
    const result = io.sendRequest({ subtype: "get_settings" }, { requestId: "settings_1" });
    await io.nextOutboundMessage();

    await expect(io.injectControlResponse({ type: "keep_alive" } as any))
      .rejects.toThrow("injectControlResponse expects a control_response message");
    await io.injectControlResponse(createSdkControlSuccessResponse("settings_1", { model: "mock" }));

    expect(await io.nextOutboundMessage()).toEqual({ type: "control_cancel_request", requestId: "settings_1" });
    expect(await result).toEqual({ model: "mock" });
  });

  test("routes unexpected responses through the configured handler", async () => {
    const unexpectedRequestIds: string[] = [];
    const io = new SdkStructuredIo({
      replayControlResponses: true,
      onUnexpectedResponse: (response) => unexpectedRequestIds.push(response.response.requestId)
    });
    const response = createSdkControlSuccessResponse("missing_1", { ok: true });

    expect(await io.receive(response)).toEqual(response);
    expect(unexpectedRequestIds).toEqual(["missing_1"]);
  });

  test("keeps protocol flow isolated from handler failures", async () => {
    const io = new SdkStructuredIo({
      replayControlResponses: true,
      onControlRequestSent: async () => {
        throw new Error("sent hook failed");
      },
      onControlRequestResolved: async () => {
        throw new Error("resolved hook failed");
      },
      onUnexpectedResponse: async () => {
        throw new Error("unexpected hook failed");
      }
    });
    const result = io.sendRequest({
      subtype: "can_use_tool",
      toolName: "filesystem.read",
      input: { path: "note.txt" },
      toolUseId: "tool_2"
    }, { requestId: "permission_2" });

    expect((await io.nextOutboundMessage() as SdkControlRequestMessage).request.subtype).toBe("can_use_tool");

    const response = createSdkControlSuccessResponse("permission_2", { behavior: "allow", toolUseId: "tool_2" });

    expect(await io.receive(response)).toEqual(response);
    expect(await result).toEqual({ behavior: "allow", toolUseId: "tool_2" });
    expect(io.pendingCount).toBe(0);

    const unexpectedResponse = createSdkControlSuccessResponse("missing_3", { ok: true });

    expect(await io.receive(unexpectedResponse)).toEqual(unexpectedResponse);
  });

  test("accepts src-origin replay user messages as a control response replay alias", async () => {
    const io = new SdkStructuredIo({ replayUserMessages: true });
    const result = io.sendRequest({ subtype: "get_settings" }, { requestId: "settings_1" });
    await io.nextOutboundMessage();

    const response = createSdkControlSuccessResponse("settings_1", { model: "mock" });

    expect(await io.receive(response)).toEqual(response);
    expect(await result).toEqual({ model: "mock" });

    const explicitIo = new SdkStructuredIo();
    explicitIo.setReplayControlResponses(true);
    const unexpectedResponse = createSdkControlSuccessResponse("missing_2", { ok: true });

    expect(await explicitIo.receive(unexpectedResponse)).toEqual(unexpectedResponse);
  });

  test("mirrors Python-style structured IO API names", async () => {
    const sentPermissionRequests: SdkControlRequestMessage[] = [];
    const resolvedRequestIds: string[] = [];
    const unexpectedRequestIds: string[] = [];
    const io = new SDKStructuredIO({
      replay_user_messages: true,
      on_control_request_sent: (request) => sentPermissionRequests.push(request),
      on_control_request_resolved: (requestId) => resolvedRequestIds.push(requestId)
    });

    expect(io.closed).toBe(false);
    expect(io.replay_user_messages).toBe(true);
    io.set_unexpected_response_handler((response) => unexpectedRequestIds.push(response.response.requestId));

    const permissionResult = io.send_request({
      subtype: "can_use_tool",
      toolName: "filesystem.read",
      input: { path: "note.txt" },
      toolUseId: "tool_python_1"
    }, {
      request_id: "permission_python_1",
      response_validator: (payload) => String(payload.behavior || "")
    });

    expect(await io.next_stdout_message()).toMatchObject({
      type: "control_request",
      requestId: "permission_python_1",
      request: { subtype: "can_use_tool" }
    });
    expect(io.pending_count).toBe(1);
    expect(io.get_pending_permission_requests()).toHaveLength(1);
    expect(sentPermissionRequests.map((request) => request.requestId)).toEqual(["permission_python_1"]);

    const permissionResponse = createSdkControlSuccessResponse("permission_python_1", {
      behavior: "allow",
      toolUseId: "tool_python_1"
    });

    expect(await io.receive(permissionResponse)).toEqual(permissionResponse);
    expect(await permissionResult).toBe("allow");
    expect(io.pending_count).toBe(0);
    expect(resolvedRequestIds).toEqual(["permission_python_1"]);

    const unexpectedResponse = createSdkControlSuccessResponse("missing_python_1", { ok: true });

    expect(await io.receive(unexpectedResponse)).toEqual(unexpectedResponse);
    expect(unexpectedRequestIds).toEqual(["missing_python_1"]);

    io.write({ type: "keep_alive" });
    expect(io.drain_stdout_messages()).toEqual([{ type: "keep_alive" }]);

    const injectedResult = io.send_request({ subtype: "get_settings" }, { request_id: "settings_python_1" });
    await io.next_stdout_message();
    await io.inject_control_response(createSdkControlSuccessResponse("settings_python_1", { model: "mock" }));

    expect(await io.next_stdout_message()).toEqual({
      type: "control_cancel_request",
      requestId: "settings_python_1"
    });
    expect(await injectedResult).toEqual({ model: "mock" });

    const cancelledResult = io.send_request({ subtype: "interrupt" }, { request_id: "cancel_python_1" });
    await io.next_stdout_message();
    await io.cancel_request("cancel_python_1");

    await expect(cancelledResult).rejects.toBeInstanceOf(SdkControlRequestCancelledError);
    io.close();
    expect(io.closed).toBe(true);
  });
});
