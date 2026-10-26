import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentSdkClient, type SdkElicitationRequest, type SdkWireMessage } from "@kevin/core/sdk";
import { JsonStateStore, loadSettings } from "../src/index.js";

describe("SDK interaction control handlers", () => {
  test("routes hook callbacks and elicitations through registered SDK handlers", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-interactions-"));
    try {
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
      client.registerHookCallback("hook_1", (request) => ({
        handled: true,
        input: request.input || {},
        toolUseId: request.toolUseId || ""
      }));
      client.setElicitationHandler((request) => ({
        action: "accept",
        content: {
          server: request.mcpServerName,
          mode: request.mode || "",
          schemaType: String(request.requestedSchema?.type || "")
        }
      }));

      const outputs = await collectWireMessages(client.runWireMessages([
        {
          type: "control_request",
          requestId: "hook_1",
          request: {
            subtype: "hook_callback",
            callbackId: "hook_1",
            input: { ok: true },
            toolUseId: "tool_1"
          }
        },
        {
          type: "control_request",
          requestId: "hook_missing_1",
          request: { subtype: "hook_callback", callbackId: "missing" }
        },
        {
          type: "control_request",
          requestId: "elicitation_1",
          request: {
            subtype: "elicitation",
            mcpServerName: "forms",
            message: "Need a value",
            mode: "form",
            requestedSchema: { type: "object" }
          }
        }
      ]));

      expect(controlPayload(outputs[0])).toEqual({
        handled: true,
        input: { ok: true },
        toolUseId: "tool_1"
      });
      expect(controlPayload(outputs[1])).toEqual({});
      expect(controlPayload(outputs[2])).toEqual({
        action: "accept",
        content: {
          server: "forms",
          mode: "form",
          schemaType: "object"
        }
      });

      client.setElicitationHandler(undefined);
      const defaultCancel = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "elicitation_cancel_1",
        request: { subtype: "elicitation", mcpServerName: "forms", message: "Need a value" }
      }]));
      expect(controlPayload(defaultCancel[0])).toEqual({ action: "cancel" });

      client.setElicitationHandler(() => ({ action: "invalid" as never }));
      const invalid = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "elicitation_invalid_1",
        request: { subtype: "elicitation", mcpServerName: "forms", message: "Need a value" }
      }]));
      expect(invalid[0]).toMatchObject({
        type: "control_response",
        response: {
          subtype: "error",
          requestId: "elicitation_invalid_1",
          error: "elicitation action must be accept, decline, or cancel"
        }
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("normalizes MCP elicitation params through the SDK client handler", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-mcp-elicitations-"));
    try {
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
      const seenRequests: SdkElicitationRequest[] = [];
      client.setElicitationHandler((request) => {
        seenRequests.push(request);
        return {
          action: "accept",
          content: {
            server: request.mcpServerName,
            mode: request.mode,
            id: request.elicitationId,
            schemaType: String(request.requestedSchema?.type || "")
          }
        };
      });

      await expect(client.handleMcpElicitation("forms", {
        message: "Need a value",
        mode: "url",
        url: "https://example.test/form",
        elicitation_id: "ask_1",
        requested_schema: { type: "object" }
      })).resolves.toEqual({
        action: "accept",
        content: {
          server: "forms",
          mode: "url",
          id: "ask_1",
          schemaType: "object"
        }
      });
      expect(seenRequests[0]).toEqual({
        subtype: "elicitation",
        mcpServerName: "forms",
        message: "Need a value",
        mode: "url",
        url: "https://example.test/form",
        elicitationId: "ask_1",
        requestedSchema: { type: "object" }
      });

      await expect(client.handleMcpElicitation("forms", {
        model_dump: () => ({
          message: "Fallback object",
          elicitationId: "ask_2",
          requestedSchema: { type: "string" }
        })
      })).resolves.toMatchObject({
        action: "accept",
        content: {
          server: "forms",
          mode: "form",
          id: "ask_2",
          schemaType: "string"
        }
      });

      client.setElicitationHandler(undefined);
      await expect(client.handleMcpElicitation("forms", { message: "Need a value" })).resolves.toEqual({
        action: "cancel"
      });
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function collectWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

function controlPayload(message: SdkWireMessage): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}
