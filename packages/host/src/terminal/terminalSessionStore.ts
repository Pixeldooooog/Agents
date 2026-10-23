import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

export type TerminalSessionRecord = {
  session_id: string;
  updated_at?: number;
  model?: string;
  workspace_path?: string;
  messages?: Array<{ role: string; content: unknown }>;
  pending_run_id?: string;
  pending_approval?: unknown;
};

export type SessionRow = {
  id: string;
  short_id: string;
  updated: string;
  model: string;
  messages: string;
  workspace: string;
};

export class TerminalSessionStore {
  constructor(private readonly root: string) {}

  async list(): Promise<SessionRow[]> {
    const sessions = await this.readAll();
    return sessions.map((session) => ({
      id: session.session_id,
      short_id: session.session_id.slice(0, 12),
      updated: new Date(Number(session.updated_at || 0) * 1000 || Date.now()).toISOString(),
      model: String(session.model || ""),
      messages: String(session.messages?.length || 0),
      workspace: String(session.workspace_path || "")
    }));
  }

  async load(id: string): Promise<TerminalSessionRecord | undefined> {
    return (await this.readAll()).find((session) => session.session_id === id || session.session_id.startsWith(id));
  }

  private async readAll(): Promise<TerminalSessionRecord[]> {
    try {
      const files = await readdir(this.root);
      const sessions = await Promise.all(files.filter((file) => file.endsWith(".json")).map((file) => this.read(path.join(this.root, file))));
      return sessions.filter(Boolean).sort((a, b) => Number(b?.updated_at || 0) - Number(a?.updated_at || 0)) as TerminalSessionRecord[];
    } catch {
      return [];
    }
  }

  private async read(filename: string): Promise<TerminalSessionRecord | undefined> {
    try {
      const payload = JSON.parse(await readFile(filename, "utf8"));
      return payload && typeof payload.session_id === "string" ? payload : undefined;
    } catch {
      return undefined;
    }
  }
}

export function transcriptMessages(session: TerminalSessionRecord): Array<{ role: string; content: string }> {
  return (session.messages || []).map((message) => ({ role: message.role, content: contentText(message.content) })).filter((message) => message.content);
}

function contentText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((item) => typeof item?.text === "string" ? item.text : "").join("");
  return "";
}
