import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from agents.kernel.mcp.oauth_tokens import (
    MCPOAuthTokenRequestError,
    build_mcp_oauth_authorization_url,
    exchange_mcp_oauth_code,
    mcp_auth_record_from_token_response,
    parse_mcp_oauth_token_response,
    pkce_s256_challenge,
    refresh_mcp_oauth_token,
)


def test_pkce_s256_challenge_matches_rfc_example():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert pkce_s256_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_build_mcp_oauth_authorization_url_includes_pkce_and_resource():
    url = build_mcp_oauth_authorization_url(
        "https://auth.example.test/oauth/authorize",
        client_id="client-1",
        redirect_uri="http://localhost:3118/callback",
        state="state-1",
        code_challenge="challenge",
        scope="read write",
        resource="https://mcp.example.test",
        extra_params={"audience": "agents"},
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.example.test"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-1"]
    assert query["redirect_uri"] == ["http://localhost:3118/callback"]
    assert query["state"] == ["state-1"]
    assert query["code_challenge"] == ["challenge"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["read write"]
    assert query["resource"] == ["https://mcp.example.test"]
    assert query["audience"] == ["agents"]


def test_parse_mcp_oauth_token_response_and_builds_auth_record():
    token = parse_mcp_oauth_token_response(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scope": "read write",
        },
        now=1000,
    )
    record = mcp_auth_record_from_token_response(
        "docs",
        token,
        tenant_id="tenant",
        user_id="user",
        agent_id="agent",
        workspace_id="workspace",
    )

    assert token.expires_at == 4600
    assert token.scopes == ["read", "write"]
    assert record.authorization_header() == "Bearer access"
    assert record.refresh_token == "refresh"
    assert record.scopes == ["read", "write"]
    assert record.workspace_id == "workspace"


def test_parse_mcp_oauth_token_response_normalizes_nonstandard_invalid_grant():
    with pytest.raises(MCPOAuthTokenRequestError) as exc_info:
        parse_mcp_oauth_token_response({"error": "expired_refresh_token"})

    assert exc_info.value.error == "invalid_grant"
    assert "non-standard" in exc_info.value.description


def test_exchange_mcp_oauth_code_posts_authorization_code_form():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 120,
                "token_type": "Bearer",
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await exchange_mcp_oauth_code(
                "https://auth.example.test/token",
                client_id="client-1",
                client_secret="secret",
                code="code-1",
                redirect_uri="http://localhost:3118/callback",
                code_verifier="verifier",
                resource="https://mcp.example.test",
                http_client=client,
            )

    token = asyncio.run(exercise())

    assert token.access_token == "access"
    assert captured["headers"]["accept"] == "application/json"
    assert captured["form"] == {
        "grant_type": ["authorization_code"],
        "client_id": ["client-1"],
        "client_secret": ["secret"],
        "code": ["code-1"],
        "redirect_uri": ["http://localhost:3118/callback"],
        "code_verifier": ["verifier"],
        "resource": ["https://mcp.example.test"],
    }


def test_refresh_mcp_oauth_token_posts_refresh_form_and_surfaces_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert parse_qs(request.content.decode()) == {
            "grant_type": ["refresh_token"],
            "client_id": ["client-1"],
            "refresh_token": ["refresh"],
            "scope": ["read"],
        }
        return httpx.Response(
            200,
            json={"error": "invalid_refresh_token", "error_description": "rotated"},
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await refresh_mcp_oauth_token(
                "https://auth.example.test/token",
                client_id="client-1",
                refresh_token="refresh",
                scope="read",
                http_client=client,
            )

    with pytest.raises(MCPOAuthTokenRequestError) as exc_info:
        asyncio.run(exercise())

    assert exc_info.value.error == "invalid_grant"
    assert exc_info.value.description == "rotated"
