export type SdkWebSocketProxyEnv = Record<string, string | undefined>;

export function resolveWebSocketProxy(options: {
  url: string;
  proxyUrl?: string;
  noProxy?: string;
  trustEnvProxy?: boolean;
  env?: SdkWebSocketProxyEnv;
}): string | undefined {
  const env = options.env || environmentProxyValues();
  const proxy = options.proxyUrl || (options.trustEnvProxy === false ? undefined : envProxyUrl(env));
  if (!proxy) return undefined;
  const noProxy = options.noProxy ?? envNoProxy(env);
  return shouldBypassProxy(options.url, noProxy) ? undefined : proxy;
}

export function envProxyUrl(env: SdkWebSocketProxyEnv): string | undefined {
  return firstEnv(env, "https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY");
}

export function envNoProxy(env: SdkWebSocketProxyEnv): string | undefined {
  return firstEnv(env, "no_proxy", "NO_PROXY");
}

export function shouldBypassProxy(url: string, noProxy: string | undefined): boolean {
  if (!noProxy) return false;
  if (noProxy.trim() === "*") return true;
  const parsedUrl = new URL(url);
  const hostname = parsedUrl.hostname.toLowerCase();
  if (!hostname) return false;
  const port = parsedUrl.port || (["wss:", "https:"].includes(parsedUrl.protocol) ? "443" : "80");
  const hostWithPort = `${hostname}:${port}`;
  for (const rawPattern of noProxy.replace(/,/g, " ").split(/\s+/)) {
    const pattern = rawPattern.trim().toLowerCase();
    if (!pattern) continue;
    if (pattern.includes(":")) {
      if (hostWithPort === pattern) return true;
      continue;
    }
    if (pattern.startsWith(".")) {
      if (hostname === pattern.slice(1) || hostname.endsWith(pattern)) return true;
      continue;
    }
    if (hostname === pattern) return true;
  }
  return false;
}

function firstEnv(env: SdkWebSocketProxyEnv, ...names: string[]): string | undefined {
  for (const name of names) {
    const value = env[name];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

function environmentProxyValues(): SdkWebSocketProxyEnv {
  return {
    https_proxy: process.env.https_proxy,
    HTTPS_PROXY: process.env.HTTPS_PROXY,
    http_proxy: process.env.http_proxy,
    HTTP_PROXY: process.env.HTTP_PROXY,
    no_proxy: process.env.no_proxy,
    NO_PROXY: process.env.NO_PROXY
  };
}
