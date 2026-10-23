export type ModelClientConfig = {
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
