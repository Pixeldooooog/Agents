import type { Message } from "../types/runtimeTypes.js";
import type { ModelTurn } from "../types/modelTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { postJson } from "./modelHttp.js";
import { modelUsageFromGemini } from "./modelUsage.js";

export async function geminiComplete(config: ModelClientConfig, messages: Message[]): Promise<ModelTurn> {
  const endpoint = `/models/${encodeURIComponent(config.model)}:generateContent?key=${encodeURIComponent(config.apiKey)}`;
  const contents = messages
    .filter((item) => item.role !== "system")
    .map((item) => ({
      role: item.role === "assistant" ? "model" : "user",
      parts: [{ text: item.content }]
    }));
  const systemText = messages
    .filter((item) => item.role === "system")
    .map((item) => item.content)
    .join("\n\n");
  const payload = await postJson(config, endpoint, {
    contents,
    systemInstruction: { parts: [{ text: systemText }] }
  }, false);
  return {
    content: String(payload.candidates?.[0]?.content?.parts?.map((part: { text?: string }) => part.text || "").join("") || ""),
    tool_calls: [],
    usage: modelUsageFromGemini(payload.usageMetadata)
  };
}
