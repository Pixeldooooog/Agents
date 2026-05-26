from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
from mcp.client.auth.oauth2 import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    resource_url_from_server_url,
)

from agents.kernel.mcp.auth import MCPAuthTokenStore
from agents.kernel.mcp.oauth import (
    MCPOAuthProviderError,
    MCPOAuthStateMismatchError,
    parse_mcp_oauth_callback_url,
)
from agents.kernel.mcp.oauth_tokens import (
    build_mcp_oauth_authorization_url,
    exchange_mcp_oauth_code,
    generate_pkce_code_verifier,
    mcp_auth_record_from_token_response,
    pkce_s256_challenge,
)


MCP_OAUTH_FLOW_TIMEOUT_SECONDS = 30.0
MCP_OAUTH_PENDING_TTL_SECONDS = 5 * 60


@dataclass(frozen=True)
class MCPOAuthServerMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str = ""
    scope: str = ""
    issuer: str = ""


@dataclass(frozen=True)
class MCPOAuthClientInformation:
    client_id: str
    client_secret: str = ""


@dataclass(frozen=True)
class MCPOAuthPendingAuthorization:
    server_name: str
    server_url: str
    authorization_url: str
    redirect_uri: str
    state: str
    code_verifier: str
    token_endpoint: str
    client_id: str
    client_secret: str = ""
    scope: str = ""
    resource: str = ""
    expires_at: float = 0.0

    def is_expired(self, *, now: float | None = None) -> bool:
        return bool(self.expires_at and self.expires_at <= (time.time() if now is None else now))


async def start_mcp_oauth_authorization(
    server_name: str,
    server_url: str,
    *,
    redirect_uri: str,
    scope: str = "",
    resource: str = "",
    auth_server_metadata_url: str = "",
    resource_metadata_url: str = "",
    client_name: str = "",
    state: str = "",
    code_verifier: str = "",
    now: float | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> MCPOAuthPendingAuthorization:
    metadata = await discover_mcp_oauth_server_metadata(
        server_url,
        auth_server_metadata_url=auth_server_metadata_url,
        resource_metadata_url=resource_metadata_url,
        http_client=http_client,
    )
    selected_scope = str(scope or metadata.scope or "")
    client = await register_mcp_oauth_client(
        metadata.registration_endpoint,
        redirect_uri=redirect_uri,
        client_name=client_name or "Agents (%s)" % (str(server_name or "MCP")),
        scope=selected_scope,
        http_client=http_client,
    )
    verifier = code_verifier or generate_pkce_code_verifier()
    state_value = state or generate_pkce_code_verifier()
    resource_value = str(resource or resource_url_from_server_url(server_url) or "")
    authorization_url = build_mcp_oauth_authorization_url(
        metadata.authorization_endpoint,
        client_id=client.client_id,
        redirect_uri=redirect_uri,
        state=state_value,
        code_challenge=pkce_s256_challenge(verifier),
        scope=selected_scope,
        resource=resource_value,
    )
    return MCPOAuthPendingAuthorization(
        server_name=str(server_name or "default"),
        server_url=str(server_url or ""),
        authorization_url=authorization_url,
        redirect_uri=redirect_uri,
        state=state_value,
        code_verifier=verifier,
        token_endpoint=metadata.token_endpoint,
        client_id=client.client_id,
        client_secret=client.client_secret,
        scope=selected_scope,
        resource=resource_value,
        expires_at=(time.time() if now is None else now) + MCP_OAUTH_PENDING_TTL_SECONDS,
    )


async def discover_mcp_oauth_server_metadata(
    server_url: str,
    *,
    auth_server_metadata_url: str = "",
    resource_metadata_url: str = "",
    http_client: httpx.AsyncClient | None = None,
) -> MCPOAuthServerMetadata:
    if http_client is None:
        async with httpx.AsyncClient(timeout=MCP_OAUTH_FLOW_TIMEOUT_SECONDS) as client:
            return await discover_mcp_oauth_server_metadata(
                server_url,
                auth_server_metadata_url=auth_server_metadata_url,
                resource_metadata_url=resource_metadata_url,
                http_client=client,
            )
    if auth_server_metadata_url:
        payload = await _get_json(http_client, auth_server_metadata_url)
        return _metadata_from_payload(payload, source=auth_server_metadata_url)

    auth_server_url = await _discover_authorization_server_url(
        http_client,
        server_url,
        resource_metadata_url=resource_metadata_url,
    )
    for url in _authorization_server_metadata_urls(auth_server_url, server_url):
        payload = await _get_optional_json(http_client, url)
        if payload is None:
            continue
        try:
            return _metadata_from_payload(payload, source=url)
        except MCPOAuthFlowError:
            continue
    raise MCPOAuthFlowError("OAuth authorization server metadata was not found for %s" % server_url)


async def register_mcp_oauth_client(
    registration_endpoint: str,
    *,
    redirect_uri: str,
    client_name: str,
    scope: str = "",
    http_client: httpx.AsyncClient | None = None,
) -> MCPOAuthClientInformation:
    endpoint = str(registration_endpoint or "").strip()
    if not endpoint:
        raise MCPOAuthFlowError("OAuth server metadata did not include a registration_endpoint")
    if http_client is None:
        async with httpx.AsyncClient(timeout=MCP_OAUTH_FLOW_TIMEOUT_SECONDS) as client:
            return await register_mcp_oauth_client(
                endpoint,
                redirect_uri=redirect_uri,
                client_name=client_name,
                scope=scope,
                http_client=client,
            )
    payload: dict[str, Any] = {
        "client_name": str(client_name or "Agents"),
        "redirect_uris": [str(redirect_uri or "")],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        payload["scope"] = str(scope)
    response = await http_client.post(
        endpoint,
        json=payload,
        headers={"Accept": "application/json"},
    )
    body = _json_response(response)
    if response.status_code >= 400:
        raise MCPOAuthFlowError(_oauth_error_message(body, fallback="OAuth client registration failed"))
    client_id = str(body.get("client_id") or "").strip()
    if not client_id:
        raise MCPOAuthFlowError("OAuth client registration response is missing client_id")
    return MCPOAuthClientInformation(
        client_id=client_id,
        client_secret=str(body.get("client_secret") or ""),
    )


async def complete_mcp_oauth_authorization(
    pending: MCPOAuthPendingAuthorization,
    callback_url: str,
    *,
    auth_store: MCPAuthTokenStore | None,
    tenant_id: str,
    user_id: str = "",
    agent_id: str = "",
    workspace_id: str = "",
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    if pending.is_expired():
        raise MCPOAuthFlowError("OAuth authorization session expired; start authentication again")
    callback = parse_mcp_oauth_callback_url(callback_url)
    if callback is None:
        raise MCPOAuthFlowError("callback_url must be an OAuth /callback URL")
    if callback.error:
        message = "OAuth error: %s" % callback.error
        if callback.error_description:
            message += " - %s" % callback.error_description
        if callback.error_uri:
            message += " (See: %s)" % callback.error_uri
        raise MCPOAuthProviderError(message)
    if callback.state != pending.state:
        raise MCPOAuthStateMismatchError("OAuth state mismatch - possible CSRF attack")
    if not callback.code:
        raise MCPOAuthFlowError("callback_url is missing authorization code")
    token = await exchange_mcp_oauth_code(
        pending.token_endpoint,
        client_id=pending.client_id,
        client_secret=pending.client_secret,
        code=callback.code,
        redirect_uri=pending.redirect_uri,
        code_verifier=pending.code_verifier,
        resource=pending.resource,
        http_client=http_client,
    )
    if auth_store is not None:
        await auth_store.save(
            mcp_auth_record_from_token_response(
                pending.server_name,
                token,
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                workspace_id=workspace_id,
            )
        )
    return {
        "status": "authenticated",
        "server": pending.server_name,
        "expiresAt": token.expires_at,
        "expires_at": token.expires_at,
        "scopes": token.scopes,
        "message": "Authentication completed for %s. Run mcp.reload to reconnect with the cached token."
        % pending.server_name,
    }


class MCPOAuthFlowError(Exception):
    pass


async def _discover_authorization_server_url(
    http_client: httpx.AsyncClient,
    server_url: str,
    *,
    resource_metadata_url: str = "",
) -> str:
    for url in build_protected_resource_metadata_discovery_urls(resource_metadata_url or None, server_url):
        payload = await _get_optional_json(http_client, url)
        if payload is None:
            continue
        servers = payload.get("authorization_servers")
        if isinstance(servers, list) and servers:
            return str(servers[0] or "")
    return ""


def _authorization_server_metadata_urls(auth_server_url: str, server_url: str) -> list[str]:
    urls = build_oauth_authorization_server_metadata_discovery_urls(auth_server_url or None, server_url)
    if not auth_server_url:
        parsed = urlparse(str(server_url or ""))
        if parsed.path and parsed.path != "/":
            urls.extend(build_oauth_authorization_server_metadata_discovery_urls(server_url, server_url))
    return _unique(urls)


async def _get_optional_json(http_client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    response = await http_client.get(str(url), headers={"Accept": "application/json"})
    if response.status_code >= 400:
        return None
    return _json_response(response)


async def _get_json(http_client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await http_client.get(str(url), headers={"Accept": "application/json"})
    payload = _json_response(response)
    if response.status_code >= 400:
        raise MCPOAuthFlowError("HTTP %d fetching OAuth metadata from %s" % (response.status_code, url))
    return payload


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MCPOAuthFlowError("OAuth endpoint did not return JSON") from exc
    if not isinstance(payload, dict):
        raise MCPOAuthFlowError("OAuth endpoint JSON must be an object")
    return payload


def _metadata_from_payload(payload: Mapping[str, Any], *, source: str) -> MCPOAuthServerMetadata:
    authorization_endpoint = str(payload.get("authorization_endpoint") or "").strip()
    token_endpoint = str(payload.get("token_endpoint") or "").strip()
    if not authorization_endpoint or not token_endpoint:
        raise MCPOAuthFlowError("OAuth metadata at %s is missing authorization_endpoint or token_endpoint" % source)
    return MCPOAuthServerMetadata(
        issuer=str(payload.get("issuer") or ""),
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        registration_endpoint=str(payload.get("registration_endpoint") or "").strip(),
        scope=_scope_from_metadata(payload),
    )


def _scope_from_metadata(payload: Mapping[str, Any]) -> str:
    for key in ("scope", "default_scope"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    scopes = payload.get("scopes_supported")
    if isinstance(scopes, list):
        return " ".join(str(item) for item in scopes if str(item))
    return ""


def _oauth_error_message(payload: Mapping[str, Any], *, fallback: str) -> str:
    error = str(payload.get("error") or fallback)
    description = str(payload.get("error_description") or payload.get("message") or "")
    return "%s: %s" % (error, description) if description else error


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
