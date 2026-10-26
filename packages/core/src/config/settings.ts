import path from "node:path";
import { mergeConfig, readEnvFile, readTomlFile } from "./configFileReaders.js";
import {
  boolSetting,
  headerSetting,
  listSetting,
  type ModelSettings,
  modelSettings,
  numberSetting,
  section,
  stringSetting,
  valueOrFallback
} from "./settingValues.js";

export type WebSearchSettings = {
  provider: string;
  tavilyApiKey: string;
  tavilyBaseUrl: string;
  timeout: number;
  maxResults: number;
  maxCreditsPerRun: number;
  allowDomains: string[];
  denyDomains: string[];
  allowAdvanced: boolean;
  allowRawContent: boolean;
};

export type McpSettings = {
  serverName: string;
  serverCommand: string;
  serverArgs?: string[];
  serverTransport: string;
  serverUrl: string;
  serverHeaders: Record<string, string>;
  clientTimeout: number;
  executionMode: string;
  sandboxProfile: string;
};

export type Settings = {
  repoRoot: string;
  host: {
    debug: boolean;
    projectName: string;
    apiPrefix: string;
    bindHost: string;
    port: number;
    domain: string;
    accessToken: string;
    corsOrigins: string[];
  };
  agent: {
    protocol: string;
    timeout: number;
    maxTokens: number;
    maxToolIterations: number;
    systemPrompt: string;
    enabledTools: string[];
    builtinTools: string[];
    maxConcurrentRequests: number;
    runRoot: string;
    statePath: string;
    memoryContextLimit: number;
    claude: ModelSettings;
  };
  models: Record<string, ModelSettings>;
  webSearch: WebSearchSettings;
  mcp: McpSettings;
};

export async function loadSettings(repoRoot = process.cwd()): Promise<Settings> {
  const env = { ...process.env, ...(await readEnvFile(path.join(repoRoot, ".env"))) };
  const defaults = await readTomlFile(path.join(repoRoot, "config/defaults.toml"));
  const local = await readTomlFile(path.join(repoRoot, "config/local.toml"));
  const tree = mergeConfig(defaults, local);
  const host = section(tree, "host");
  const agent = section(tree, "agent");
  const webSearch = section(tree, "web_search");
  const mcp = section(tree, "mcp");
  return {
    repoRoot,
    host: {
      debug: boolSetting(env.DEBUG, valueOrFallback(host.debug, false)),
      projectName: stringSetting(env.PROJECT_NAME, valueOrFallback(host.project_name, "Kevin")),
      apiPrefix: stringSetting(env.API_PREFIX, valueOrFallback(host.api_prefix, "/api")),
      bindHost: stringSetting(env.HOST, valueOrFallback(host.host, "127.0.0.1")),
      port: numberSetting(env.PORT, valueOrFallback(host.port, 8020)),
      domain: stringSetting(env.DOMAIN, valueOrFallback(host.domain, "http://localhost:8020")),
      accessToken: stringSetting(env.ACCESS_TOKEN, ""),
      corsOrigins: listSetting(env.CORS_ORIGINS, valueOrFallback(host.cors_origins, []))
    },
    agent: {
      protocol: stringSetting(env.AGENT_PROTOCOL, valueOrFallback(agent.protocol, "openai-chat")),
      timeout: numberSetting(env.AGENT_TIMEOUT, valueOrFallback(agent.timeout, 60)),
      maxTokens: numberSetting(env.AGENT_MAX_TOKENS, valueOrFallback(agent.max_tokens, 16384)),
      maxToolIterations: numberSetting(env.AGENT_MAX_TOOL_ITERATIONS, valueOrFallback(agent.max_tool_iterations, 40)),
      systemPrompt: stringSetting(env.AGENT_SYSTEM_PROMPT, valueOrFallback(agent.system_prompt, "")),
      enabledTools: listSetting(env.AGENT_ENABLED_TOOLS, valueOrFallback(agent.enabled_tools, "")),
      builtinTools: listSetting(env.AGENT_BUILTIN_TOOLS, valueOrFallback(agent.builtin_tools, "")),
      maxConcurrentRequests: numberSetting(env.AGENT_MAX_CONCURRENT_REQUESTS, valueOrFallback(agent.max_concurrent_requests, 20)),
      runRoot: stringSetting(env.AGENT_RUN_ROOT, valueOrFallback(agent.run_root, ".kevin/runs")),
      statePath: stringSetting(env.AGENT_STATE_PATH, valueOrFallback(agent.state_path, ".kevin/host/state.json")),
      memoryContextLimit: numberSetting(env.AGENT_MEMORY_CONTEXT_LIMIT, valueOrFallback(agent.memory_context_limit, 20)),
      claude: {
        apiKey: stringSetting(env.AGENT_CLAUDE_API_KEY, ""),
        baseUrl: stringSetting(env.AGENT_CLAUDE_BASE_URL, valueOrFallback(agent.claude_base_url, "")),
        model: stringSetting(env.AGENT_CLAUDE_MODEL, valueOrFallback(agent.claude_model, ""))
      }
    },
    models: {
      openai: modelSettings(tree, "models.openai", env, "OPENAI"),
      openai_responses: modelSettings(tree, "models.openai_responses", env, "OPENAI_RESPONSES"),
      anthropic: modelSettings(tree, "models.anthropic", env, "ANTHROPIC"),
      gemini: modelSettings(tree, "models.gemini", env, "GEMINI")
    },
    webSearch: {
      provider: stringSetting(env.WEB_SEARCH_PROVIDER, valueOrFallback(webSearch.provider, "none")),
      tavilyApiKey: stringSetting(env.TAVILY_API_KEY ?? env.WEB_SEARCH_API_KEY, valueOrFallback(webSearch.tavily_api_key, "")),
      tavilyBaseUrl: stringSetting(env.TAVILY_BASE_URL, valueOrFallback(webSearch.tavily_base_url, "https://api.tavily.com")),
      timeout: numberSetting(env.WEB_SEARCH_TIMEOUT, valueOrFallback(webSearch.timeout, 30)),
      maxResults: numberSetting(env.WEB_SEARCH_MAX_RESULTS, valueOrFallback(webSearch.max_results, 5)),
      maxCreditsPerRun: numberSetting(env.WEB_SEARCH_MAX_CREDITS_PER_RUN, valueOrFallback(webSearch.max_credits_per_run, 10)),
      allowDomains: listSetting(env.WEB_SEARCH_ALLOW_DOMAINS, valueOrFallback(webSearch.allow_domains, "")),
      denyDomains: listSetting(env.WEB_SEARCH_DENY_DOMAINS, valueOrFallback(webSearch.deny_domains, "")),
      allowAdvanced: boolSetting(env.WEB_SEARCH_ALLOW_ADVANCED, valueOrFallback(webSearch.allow_advanced, false)),
      allowRawContent: boolSetting(env.WEB_SEARCH_ALLOW_RAW_CONTENT, valueOrFallback(webSearch.allow_raw_content, false))
    },
    mcp: {
      serverName: stringSetting(env.MCP_SERVER_NAME, valueOrFallback(mcp.server_name, "")),
      serverCommand: stringSetting(env.MCP_SERVER_COMMAND, valueOrFallback(mcp.server_command, "")),
      serverArgs: listSetting(env.MCP_SERVER_ARGS, valueOrFallback(mcp.server_args, [])),
      serverTransport: stringSetting(env.MCP_SERVER_TRANSPORT, valueOrFallback(mcp.server_transport, "stdio")),
      serverUrl: stringSetting(env.MCP_SERVER_URL, valueOrFallback(mcp.server_url, "")),
      serverHeaders: headerSetting(env.MCP_SERVER_HEADERS, valueOrFallback(mcp.server_headers, {})),
      clientTimeout: numberSetting(env.MCP_CLIENT_TIMEOUT, valueOrFallback(mcp.client_timeout, 30)),
      executionMode: stringSetting(env.MCP_EXECUTION_MODE, valueOrFallback(mcp.execution_mode, "trusted_control_plane")),
      sandboxProfile: stringSetting(env.MCP_SANDBOX_PROFILE, valueOrFallback(mcp.sandbox_profile, ""))
    }
  };
}
