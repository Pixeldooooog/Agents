import { expect, test } from "bun:test";
import { loadSettings } from "../src/config/settings.js";
import {
  profileDefaults,
  buildModelProfiles,
} from "../src/models/modelProfiles.js";
import { AgentRunService } from "../src/runtime/agentRunService.js";
import { JsonStateStore } from "../src/store/jsonStateStore.js";

test("protocol selection uses matching server credentials and defaults", async () => {
  const settings = await loadSettings("/tmp/kevin-profile-selection-fixture");
  settings.agent.protocol = "claude-messages";
  settings.agent.claude = {
    apiKey: "claude-secret",
    baseUrl: "https://claude.example/v1",
    model: "claude-fixture",
  };
  settings.models.openai = {
    apiKey: "chat-secret",
    baseUrl: "https://chat.example/v1",
    model: "chat-fixture",
  };
  settings.models.openai_responses = {
    apiKey: "responses-secret",
    baseUrl: "https://responses.example/v1",
    model: "responses-fixture",
  };
  const service = new AgentRunService({
    settings,
    store: new JsonStateStore("/tmp/unused-profile-test.json"),
  });
  expect(service.specFromPayload({}).protocol).toBe("claude-messages");
  const selected = service.specFromPayload({ protocol: "openai-responses" });
  expect(selected.api_key).toBe("responses-secret");
  expect(selected.model).toBe("responses-fixture");
  expect(selected.base_url).toBe("https://responses.example/v1");
  expect(
    service.specFromPayload({ protocol: "openai-chat", api_key: "manual" })
      .api_key,
  ).toBe("manual");
  expect(() => profileDefaults(settings, "invalid")).toThrow(
    "unsupported model protocol",
  );
  settings.models.openai_responses = { apiKey: "", baseUrl: "", model: "" };
  const profile = buildModelProfiles(settings).find(
    (item) => item.name === "responses",
  )!;
  expect(profile.configured).toBe(true);
  expect(profile.model).toBe(profileDefaults(settings, "responses").model);
  expect(JSON.stringify(profile)).not.toContain("chat-secret");
});
