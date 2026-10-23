import { formatSdkTransportUrl, parseSdkTransportUrl } from "./sdkTransportUrls.js";

export function pathWithQuery(path: string, params: Record<string, string>, cursor?: string): string {
  const queryParams = new URLSearchParams(params);
  if (cursor) queryParams.set("cursor", cursor);
  const query = queryParams.toString();
  return query ? `${path}?${query}` : path;
}

export function normalizeCcrSessionUrl(sessionUrl: string): string {
  const url = parseSdkTransportUrl(sessionUrl);
  url.path = url.path.replace(/\/+$/, "");
  url.query = "";
  url.fragment = "";
  return formatSdkTransportUrl(url);
}

export function ccrSessionIdFromUrl(sessionBaseUrl: string): string {
  return sessionBaseUrl.replace(/\/+$/, "").split("/").at(-1) || "";
}
