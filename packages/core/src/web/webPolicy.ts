import type { WebSearchSettings } from "../config/settings.js";
import type { ToolContext } from "../tools/toolContracts.js";

const creditsByRun = new Map<string, number>();

export const fallbackWebSearchSettings: WebSearchSettings = {
  provider: "none",
  tavilyApiKey: "",
  tavilyBaseUrl: "https://api.tavily.com",
  timeout: 30,
  maxResults: 5,
  maxCreditsPerRun: 10,
  allowDomains: [],
  denyDomains: [],
  allowAdvanced: false,
  allowRawContent: false
};

export class WebRequestPolicy {
  constructor(private readonly settings: WebSearchSettings) {}

  normalizeMaxResults(value: unknown): number {
    const requested = Number(value || this.settings.maxResults || 5);
    const maximum = Math.max(1, this.settings.maxResults || 5);
    return Math.max(1, Math.min(Number.isFinite(requested) ? requested : maximum, maximum));
  }

  validateDepth(value: unknown, parameter: "search_depth" | "extract_depth"): string {
    const normalized = String(value || "basic").trim().toLowerCase().replace("-", "_");
    const allowed = parameter === "extract_depth"
      ? new Set(["basic", "advanced"])
      : new Set(["basic", "advanced", "fast", "ultra_fast"]);
    if (!allowed.has(normalized)) throw new Error(`unsupported ${parameter}: ${String(value)}`);
    if (["advanced", "ultra_fast"].includes(normalized) && !this.settings.allowAdvanced) {
      throw new Error(`${normalized} requires advanced web search permission`);
    }
    return normalized;
  }

  validateRawContent(includeRawContent: unknown): boolean {
    const enabled = Boolean(includeRawContent);
    if (enabled && !this.settings.allowRawContent) throw new Error("raw web content requires explicit permission");
    return enabled;
  }

  includeDomainsForRequest(domains: unknown): string[] {
    const requested = cleanDomains(domains);
    if (requested.length) {
      this.validateDomains(requested);
      return requested;
    }
    return cleanDomains(this.settings.allowDomains);
  }

  excludeDomainsForRequest(domains: unknown): string[] {
    return uniqueStrings([...cleanDomains(domains), ...cleanDomains(this.settings.denyDomains)]);
  }

  validateUrls(urls: Iterable<unknown>): string[] {
    const cleanUrls = [...urls].map((url) => String(url || "").trim()).filter(Boolean);
    if (!cleanUrls.length) throw new Error("at least one URL is required");
    for (const url of cleanUrls) {
      const parsed = parseHttpUrl(url);
      this.validateDomains([parsed.hostname]);
    }
    return cleanUrls;
  }

  canUseUrl(url: string): boolean {
    try {
      this.validateUrls([url]);
      return true;
    } catch {
      return false;
    }
  }

  reserveCredits(runId: string, credits: number): void {
    const scope = runId || "session";
    const current = creditsByRun.get(scope) || 0;
    const nextValue = current + Math.max(0, credits || 0);
    if (this.settings.maxCreditsPerRun > 0 && nextValue > this.settings.maxCreditsPerRun) {
      throw new Error("web search credit budget exceeded for run");
    }
    creditsByRun.set(scope, nextValue);
  }

  private validateDomains(domains: Iterable<string>): void {
    for (const domain of cleanDomains(domains)) {
      if (this.settings.denyDomains.some((denied) => domainMatches(domain, denied))) {
        throw new Error(`domain is denied: ${domain}`);
      }
      if (this.settings.allowDomains.length && !this.settings.allowDomains.some((allowed) => domainMatches(domain, allowed))) {
        throw new Error(`domain is not allowed: ${domain}`);
      }
    }
  }
}

export function webSettingsForContext(context: ToolContext<never, "settings">): WebSearchSettings {
  return context.settings?.webSearch || fallbackWebSearchSettings;
}

export function cleanDomains(domains: unknown): string[] {
  const values = Array.isArray(domains) ? domains : String(domains || "").split(",");
  return uniqueStrings(values.map((domain) => {
    let text = String(domain || "").trim().toLowerCase();
    if (!text) return "";
    if (text.startsWith("http://") || text.startsWith("https://")) text = parseHttpUrl(text).hostname.toLowerCase();
    return text;
  }).filter(Boolean));
}

export function parseHttpUrl(url: string): URL {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
    throw new Error("web tools only support http:// and https:// URLs");
  }
  return parsed;
}

export function looksLikeHttpUrl(value: string): boolean {
  try {
    parseHttpUrl(value);
    return true;
  } catch {
    return false;
  }
}

export function domainFromUrl(url: string): string {
  return parseHttpUrl(url).hostname.toLowerCase();
}

export function domainMatches(domain: string, pattern: string): boolean {
  const normalizedDomain = domain.toLowerCase();
  const normalizedPattern = pattern.toLowerCase();
  return normalizedDomain === normalizedPattern || normalizedDomain.endsWith(`.${normalizedPattern}`);
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}
