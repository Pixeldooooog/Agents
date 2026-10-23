export type SdkTransportUrlParts = {
  scheme: string;
  authority: string;
  path: string;
  query: string;
  fragment: string;
};

export function parseSdkTransportUrl(url: string): SdkTransportUrlParts {
  const match = url.match(/^([A-Za-z][A-Za-z\d+.-]*:)?(\/\/[^/?#]*)?([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/);
  if (!match) {
    return { scheme: "", authority: "", path: url, query: "", fragment: "" };
  }
  return {
    scheme: match[1] || "",
    authority: match[2] || "",
    path: match[3] || "",
    query: match[4] || "",
    fragment: match[5] || ""
  };
}

export function formatSdkTransportUrl(url: SdkTransportUrlParts): string {
  const query = url.query ? `?${url.query}` : "";
  const fragment = url.fragment ? `#${url.fragment}` : "";
  return `${url.scheme}${url.authority}${url.path}${query}${fragment}`;
}

export function withSdkTransportQueryParam(url: string, paramName: string, paramValue: string): string {
  const transportUrl = parseSdkTransportUrl(url);
  const queryParams = new URLSearchParams(transportUrl.query);
  queryParams.set(paramName, paramValue);
  transportUrl.query = queryParams.toString();
  return formatSdkTransportUrl(transportUrl);
}
