export type Role = "user" | "assistant" | "system" | "event" | "error";

export type ChatMessage = {
  id: number;
  role: Role;
  content: string;
};

export type ActivityEventKind = "system" | "stream" | "tool" | "approval" | "code" | "search" | "browser" | "error";
export type ActivityEventStatus = "queued" | "running" | "waiting" | "done" | "error";

export type ActivityEvent = {
  id: number;
  kind: ActivityEventKind;
  title: string;
  detail: string;
  status: ActivityEventStatus;
  time: string;
};
