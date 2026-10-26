export type ModelProtocol = "openai-chat" | "openai-responses" | "claude-messages" | "gemini";

export type ModelClientConfig = {
  /** External configuration accepts aliases; modelClients validates before dispatch. */
  protocol: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  maxTokens: number;
  maxThinkingTokens?: number;
  timeoutMs: number;
  signal?: AbortSignal;
};

export type TextDeltaHandler = (delta: string) => void;

/** A text adapter emits content or confirms its protocol terminal event. */
export type TextStreamStep = { delta?: string; done?: boolean };
