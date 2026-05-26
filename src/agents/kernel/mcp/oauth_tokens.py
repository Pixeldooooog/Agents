from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx

from agents.kernel.mcp.auth import MCPAuthTokenRecord


MCP_OAUTH_TOKEN_TIMEOUT_SECONDS = 30.0
NONSTANDARD_INVALID_GRANT_ALIASES = {
    "invalid_refresh_token",
    "expired_refresh_token",
    "token_expired",
}


@dataclass(frozen=True)
class MCPOAuthTokenResponse:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    expires_in: int = 0
    expires_at: float = 0.0
    scope: str = ""

    @property
    def scopes(self) -> list[str]:
        return [scope for scope in self.scope.split() if scope]


class MCPOAuthTokenRequestError(Exception):
    def __init__(
        self,
        error: str,
        description: str = "",
        *,
        status_code: int = 0,
        payload: Mapping[str, Any] | None = None,
    ):
        message = error
        if description:
            message = "%s: %s" % (message, description)
        super().__init__(message)
        self.error = str(error or "")
        self.description = str(description or "")
        self.status_code = int(status_code or 0)
        self.payload = dict(payload or {})


def generate_pkce_code_verifier(byte_count: int = 32) -> str:
    verifier = secrets.token_urlsafe(max(32, int(byte_count)))
    return verifier[:128]


def pkce_s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(str(verifier or "").encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_mcp_oauth_authorization_url(
    authorization_endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scope: str = "",
    resource: str = "",
    extra_params: Mapping[str, Any] | None = None,
) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": str(client_id or ""),
        "redirect_uri": str(redirect_uri or ""),
        "state": str(state or ""),
        "code_challenge": str(code_challenge or ""),
        "code_challenge_method": "S256",
    }
    if scope:
        params["scope"] = str(scope)
    if resource:
        params["resource"] = str(resource)
    for key, value in dict(extra_params or {}).items():
        if value is not None:
            params[str(key)] = str(value)
    separator = "&" if "?" in authorization_endpoint else "?"
    return "%s%s%s" % (authorization_endpoint, separator, urlencode(params))


async def exchange_mcp_oauth_code(
    token_endpoint: str,
    *,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_secret: str = "",
    resource: str = "",
    http_client: httpx.AsyncClient | None = None,
) -> MCPOAuthTokenResponse:
    data = {
        "grant_type": "authorization_code",
        "client_id": str(client_id or ""),
        "code": str(code or ""),
        "redirect_uri": str(redirect_uri or ""),
        "code_verifier": str(code_verifier or ""),
    }
    if client_secret:
        data["client_secret"] = str(client_secret)
    if resource:
        data["resource"] = str(resource)
    return await _post_token_request(token_endpoint, data, http_client=http_client)


async def refresh_mcp_oauth_token(
    token_endpoint: str,
    *,
    client_id: str,
    refresh_token: str,
    client_secret: str = "",
    scope: str = "",
    resource: str = "",
    http_client: httpx.AsyncClient | None = None,
) -> MCPOAuthTokenResponse:
    data = {
        "grant_type": "refresh_token",
        "client_id": str(client_id or ""),
        "refresh_token": str(refresh_token or ""),
    }
    if client_secret:
        data["client_secret"] = str(client_secret)
    if scope:
        data["scope"] = str(scope)
    if resource:
        data["resource"] = str(resource)
    return await _post_token_request(token_endpoint, data, http_client=http_client)


def parse_mcp_oauth_token_response(payload: Mapping[str, Any], *, now: float | None = None) -> MCPOAuthTokenResponse:
    if _looks_like_oauth_error(payload):
        _raise_oauth_error(payload, status_code=400)
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise MCPOAuthTokenRequestError("invalid_token_response", "Missing access_token", payload=payload)
    expires_in = _int(payload.get("expires_in"))
    return MCPOAuthTokenResponse(
        access_token=access_token,
        token_type=str(payload.get("token_type") or "Bearer"),
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_in=expires_in,
        expires_at=(now if now is not None else time.time()) + expires_in if expires_in else 0.0,
        scope=str(payload.get("scope") or ""),
    )


def mcp_auth_record_from_token_response(
    name: str,
    token: MCPOAuthTokenResponse,
    *,
    tenant_id: str = "",
    user_id: str = "",
    agent_id: str = "",
    workspace_id: str = "",
) -> MCPAuthTokenRecord:
    return MCPAuthTokenRecord(
        name=str(name or "default").strip() or "default",
        access_token=token.access_token,
        token_type=token.token_type,
        refresh_token=token.refresh_token,
        expires_at=token.expires_at,
        scopes=token.scopes,
        tenant_id=str(tenant_id or ""),
        user_id=str(user_id or ""),
        agent_id=str(agent_id or ""),
        workspace_id=str(workspace_id or ""),
    )


async def _post_token_request(
    token_endpoint: str,
    data: Mapping[str, str],
    *,
    http_client: httpx.AsyncClient | None,
) -> MCPOAuthTokenResponse:
    if http_client is None:
        async with httpx.AsyncClient(timeout=MCP_OAUTH_TOKEN_TIMEOUT_SECONDS) as client:
            return await _post_token_request(token_endpoint, data, http_client=client)
    response = await http_client.post(
        str(token_endpoint),
        data=dict(data),
        headers={"Accept": "application/json"},
    )
    payload = _json_payload(response)
    if response.status_code >= 400:
        _raise_oauth_error(payload, status_code=response.status_code)
    return parse_mcp_oauth_token_response(payload)


def _json_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise MCPOAuthTokenRequestError(
            "invalid_token_response",
            "Token endpoint did not return JSON",
            status_code=response.status_code,
        ) from exc
    if not isinstance(payload, dict):
        raise MCPOAuthTokenRequestError(
            "invalid_token_response",
            "Token endpoint JSON must be an object",
            status_code=response.status_code,
        )
    return payload


def _looks_like_oauth_error(payload: Mapping[str, Any]) -> bool:
    return isinstance(payload.get("error"), str) and not payload.get("access_token")


def _raise_oauth_error(payload: Mapping[str, Any], *, status_code: int) -> None:
    error = str(payload.get("error") or "token_request_failed")
    description = str(payload.get("error_description") or "")
    if error in NONSTANDARD_INVALID_GRANT_ALIASES:
        description = description or "Server returned non-standard error code: %s" % error
        error = "invalid_grant"
    raise MCPOAuthTokenRequestError(error, description, status_code=status_code, payload=payload)


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
