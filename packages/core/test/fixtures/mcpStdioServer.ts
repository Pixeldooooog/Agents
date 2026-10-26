import { createInterface } from "node:readline";
// Real subprocess fixture: no global fetch substitution, no production credentials.
for await (const line of createInterface({ input: process.stdin })) {
  const request = JSON.parse(line);
  if (request.id === undefined) continue;
  let result: unknown;
  if (request.method === "initialize") result = { protocolVersion: "2025-03-26", capabilities: { tools: {}, resources: {}, prompts: {} }, serverInfo: { name: "fixture", version: "1" } };
  else if (request.method === "tools/list") result = { tools: [{ name: "echo", description: "Echo text", inputSchema: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: false } }] };
  else if (request.method === "tools/call") result = { content: [{ type: "text", text: request.params.arguments.text }], isError: request.params.arguments.text === "fail" };
  else if (request.method === "resources/list") result = { resources: [{ uri: "fixture://intro", name: "Intro" }] };
  else if (request.method === "resources/read") result = { contents: [{ uri: request.params.uri, text: "resource body" }] };
  else if (request.method === "prompts/list") result = { prompts: [{ name: "greet" }] };
  else if (request.method === "prompts/get") result = { messages: [{ role: "user", content: { type: "text", text: "hello" } }] };
  else { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: request.id, error: { code: -32601, message: "unknown method" } }) + "\n"); continue; }
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id: request.id, result }) + "\n");
}
