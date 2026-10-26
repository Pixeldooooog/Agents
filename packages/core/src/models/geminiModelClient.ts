import { requireArray, requireRecord } from "./modelProtocolValidation.js";
import { recordArray, recordValue, stringValue } from "./modelProtocolValues.js";
import { ModelProtocolError } from "./modelErrors.js";
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
  const root = requireRecord(payload, "Gemini response");
  const candidate = requireRecord(requireArray(root.candidates, "Gemini candidates")[0], "Gemini first candidate");
  if (candidate.finishReason !== undefined && candidate.finishReason !== "STOP") {
    throw new ModelProtocolError("Gemini response did not complete normally");
  }
  const parts = recordArray(recordValue(candidate.content).parts);
  if (parts.some(part => part.functionCall)) throw new ModelProtocolError("Gemini function calls are not implemented");
  return {
    content: parts.map(part => stringValue(part.text)).join(""),
    tool_calls: [],
    usage: modelUsageFromGemini(root.usageMetadata)
  };
}
