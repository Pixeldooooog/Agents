export function defaultApiBaseUrl() {
  const explicit = import.meta.env.VITE_AGENT_API_BASE_URL?.trim();
  return stripTrailingSlash(explicit || window.location.origin);
}

function stripTrailingSlash(value: string) {
  return value.replace(/\/$/, "");
}
