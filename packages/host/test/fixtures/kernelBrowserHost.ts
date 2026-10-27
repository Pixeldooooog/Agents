/** Local-only browser acceptance fixture. All writes live in a temporary workspace. */
import { mkdtemp, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { designReviewContent, unsafeMarkdownContent } from "./designReviewContent.js";
import { createHostServices } from "../../src/services/hostServices.js";
import { createAgentHttpServer } from "../../src/http/agentHttpServer.js";

const root = await mkdtemp(path.join(tmpdir(), "kevin-browser-kernel-"));
await symlink(path.resolve(import.meta.dir, "../../../../apps"), path.join(root, "apps"));
const provider = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
  const body = await request.json();
  const messages = body.messages as { role: string; content: string }[];
  const text = messages.findLast(message => message.role === "user")?.content || "";
  if (text.includes("fail")) return new Response("fixture failure", { status: 503 });
  if (text.includes("slow")) return new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode('data: {"choices":[{"index":0,"delta":{"content":"等待取消"},"finish_reason":null}]}\n\n'));
  } }), { headers: { "content-type": "text/event-stream" } });
  const answer = text.includes("design-review") ? designReviewContent : text.includes("unsafe-markdown") ? unsafeMarkdownContent : "验收完成";
  const write = text.includes("approval") && !messages.some(message => message.role === "tool");
  const call = { id: "fixture-write", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "browser-result.txt", content: "browser-approved" }) } };
  if (!body.stream) return Response.json({ choices: [{ message: write ? { content: "准备写入文件", tool_calls: [call] } : { content: answer } }] });
  const delta = write ? { content: "准备写入文件", tool_calls: [{ index: 0, ...call }] } : { content: answer };
  return new Response(`data: ${JSON.stringify({ choices: [{ index: 0, delta, finish_reason: null }] })}\n\ndata: ${JSON.stringify({ choices: [{ index: 0, delta: {}, finish_reason: write ? "tool_calls" : "stop" }] })}\n\ndata: [DONE]\n\n`, { headers: { "content-type": "text/event-stream" } });
} });
const services = await createHostServices(root);
services.settings.host.accessToken = "";
services.settings.agent.protocol = "openai-chat";
services.settings.agent.enabledTools = ["filesystem.write"];
services.settings.models.openai = { ...services.settings.models.openai, model: "fixture", apiKey: "fixture", baseUrl: `http://127.0.0.1:${provider.port}/v1` };
const host = createAgentHttpServer(services);
host.listen(Number(process.env.KEVIN_BROWSER_TEST_PORT || 5189), "127.0.0.1", () => console.log(`browser fixture workspace: ${root}`));
for (const signal of ["SIGTERM", "SIGINT"] as const) process.once(signal, () => {
  void (async () => { host.closeAllConnections(); host.close(); await services.close(); await provider.stop(true); await rm(root, { recursive: true, force: true }); process.exit(0); })();
});
