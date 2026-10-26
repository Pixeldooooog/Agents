import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, JsonStateStore, specFromPayload } from "../src/index.js";

describe("agent and team collaboration tools", () => {
  test("saves profiles and runs agents through an injected runner", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-collab-tools-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "collab", tenant_id: "tenant", user_id: "user", agent_id: "lead", workspace_id: "workspace", enabled_tools: ["filesystem.read"] });
      const context = {
        store,
        spec,
        agentRunner: {
          run: async ({ prompt }: { prompt: string }) => ({ status: "finished", content: `done:${prompt}`, messages: [{ role: "user" }], tool_results: [] })
        }
      };

      const saved = await executeBuiltinTool(root, "agent.save_profile", { agent_id: "reviewer", name: "Reviewer" }, context);
      expect(JSON.parse(saved.result.content).profile.name).toBe("Reviewer");

      const profiles = await executeBuiltinTool(root, "agent.profiles", { query: "review" }, context);
      expect(JSON.parse(profiles.result.content).profiles[0].agent_id).toBe("reviewer");

      const ran = await executeBuiltinTool(root, "agent.run", { description: "Review", prompt: "notes", agent_id: "reviewer" }, context);
      const runPayload = JSON.parse(ran.result.content);
      expect(runPayload.status).toBe("finished");
      expect(runPayload.content).toContain("notes");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("creates teams, sends messages, reads inboxes, runs members, and deletes teams", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-team-tools-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "team", tenant_id: "tenant", user_id: "user", agent_id: "lead", workspace_id: "workspace" });
      const context = {
        store,
        spec,
        agentRunner: {
          run: async ({ spec: childSpec, prompt }: any) => ({ status: "finished", content: `${childSpec.agent_id}:${prompt}`, messages: [], tool_results: [] })
        }
      };

      const created = await executeBuiltinTool(root, "team.create", {
        team_id: "alpha",
        description: "Alpha team",
        members: [{ agent_id: "team-lead", role: "lead" }]
      }, context);
      expect(JSON.parse(created.result.content).team.member_count).toBe(1);

      const updated = await executeBuiltinTool(root, "team.create", { team_id: "alpha", members: [{ agent_id: "reviewer", role: "review" }] }, context);
      expect(JSON.parse(updated.result.content).team.member_count).toBe(2);

      const sent = await executeBuiltinTool(root, "team.send", { team_id: "alpha", to: "reviewer", message: "check" }, context);
      expect(JSON.parse(sent.result.content).count).toBe(1);

      const inbox = await executeBuiltinTool(root, "team.inbox", { team_id: "alpha", agent_id: "reviewer", mark_read: true }, context);
      expect(JSON.parse(inbox.result.content).messages[0].message).toContain("check");

      const ran = await executeBuiltinTool(root, "team.run_member", { team_id: "alpha", agent_id: "reviewer", prompt: "go" }, context);
      expect(JSON.parse(ran.result.content).result.content).toBe("reviewer:go");

      const deleted = await executeBuiltinTool(root, "team.delete", { team_id: "alpha" }, context);
      expect(JSON.parse(deleted.result.content).deleted).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
