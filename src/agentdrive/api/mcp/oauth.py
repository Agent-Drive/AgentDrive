import secrets
import time
from dataclasses import dataclass

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from fastapi import HTTPException
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from agentdrive.api.auth import service as auth_service
from agentdrive.api.auth.service import generate_api_key
from agentdrive.api.dependencies import _tenant_from_api_key
from agentdrive.api.mcp.deps import mcp_session
from agentdrive.engine.data.models.api_key import ApiKey

_AUTH_CODE_TTL_SECONDS = 300
_ACCESS_TOKEN_TTL_SECONDS = 365 * 24 * 60 * 60


@dataclass
class _PendingLogin:
    client: OAuthClientInformationFull
    params: AuthorizationParams


@dataclass
class _IssuedCode:
    auth_code: AuthorizationCode
    api_key: str


@dataclass
class _IssuedRefresh:
    refresh: RefreshToken
    api_key: str


class WorkOSOAuthProvider:
    """MCP OAuth server that wraps WorkOS AuthKit and issues tenant API keys."""

    def __init__(self, public_base_url: str) -> None:
        self.public_base_url = public_base_url.rstrip("/")
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, _PendingLogin] = {}
        self._codes: dict[str, _IssuedCode] = {}
        self._refresh: dict[str, _IssuedRefresh] = {}

    @property
    def callback_url(self) -> str:
        return f"{self.public_base_url}/mcp/oauth/callback"

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        workos = auth_service.workos_client
        if workos is None:
            raise AuthorizeError(
                error="server_error",
                error_description="WorkOS is not configured",
            )
        login_id = secrets.token_urlsafe(32)
        self._pending[login_id] = _PendingLogin(client=client, params=params)
        return workos.user_management.get_authorization_url(
            redirect_uri=self.callback_url,
            state=login_id,
            provider="authkit",
        )

    async def handle_callback(self, request: Request) -> Response:
        login_id = request.query_params.get("state")
        pending = self._pending.pop(login_id, None) if login_id else None
        if pending is None:
            return PlainTextResponse("Invalid or expired OAuth state", status_code=400)

        redirect_base = str(pending.params.redirect_uri)
        client_state = pending.params.state
        oauth_error = request.query_params.get("error")
        if oauth_error:
            return RedirectResponse(
                construct_redirect_uri(
                    redirect_base,
                    error=oauth_error,
                    error_description=request.query_params.get("error_description"),
                    state=client_state,
                ),
                status_code=302,
            )

        workos_code = request.query_params.get("code")
        workos = auth_service.workos_client
        if not workos_code or workos is None:
            return RedirectResponse(
                construct_redirect_uri(
                    redirect_base,
                    error="server_error",
                    error_description="WorkOS login failed",
                    state=client_state,
                ),
                status_code=302,
            )

        try:
            result = workos.user_management.authenticate_with_code(code=workos_code)
            user = result.user
        except Exception:
            return RedirectResponse(
                construct_redirect_uri(
                    redirect_base,
                    error="access_denied",
                    error_description="WorkOS authentication failed",
                    state=client_state,
                ),
                status_code=302,
            )

        try:
            async with mcp_session() as session:
                tenant = await auth_service.get_or_create_tenant_for_workos_user(session, user)
                raw_key, prefix, key_hash = generate_api_key()
                session.add(
                    ApiKey(
                        tenant_id=tenant.id,
                        key_prefix=prefix,
                        key_hash=key_hash,
                        name="mcp-oauth",
                    )
                )
                await session.commit()
        except HTTPException as exc:
            return RedirectResponse(
                construct_redirect_uri(
                    redirect_base,
                    error="access_denied",
                    error_description=str(exc.detail),
                    state=client_state,
                ),
                status_code=302,
            )

        code = secrets.token_urlsafe(32)
        auth_code = AuthorizationCode(
            code=code,
            scopes=pending.params.scopes or [],
            expires_at=time.time() + _AUTH_CODE_TTL_SECONDS,
            client_id=pending.client.client_id,
            code_challenge=pending.params.code_challenge,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            resource=pending.params.resource,
        )
        self._codes[code] = _IssuedCode(auth_code=auth_code, api_key=raw_key)
        return RedirectResponse(
            construct_redirect_uri(redirect_base, code=code, state=client_state),
            status_code=302,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        issued = self._codes.get(authorization_code)
        if issued is None or issued.auth_code.client_id != client.client_id:
            return None
        return issued.auth_code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        issued = self._codes.pop(authorization_code.code, None)
        if issued is None or issued.auth_code.client_id != client.client_id:
            raise TokenError(error="invalid_grant", error_description="authorization code does not exist")
        return self._issue_tokens(client.client_id, issued.api_key, issued.auth_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        issued = self._refresh.get(refresh_token)
        if issued is None or issued.refresh.client_id != client.client_id:
            return None
        return issued.refresh

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        issued = self._refresh.pop(refresh_token.token, None)
        if issued is None or issued.refresh.client_id != client.client_id:
            raise TokenError(error="invalid_grant", error_description="refresh token does not exist")
        return self._issue_tokens(client.client_id, issued.api_key, scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        async with mcp_session() as session:
            tenant = await _tenant_from_api_key(session, token)
        if tenant is None:
            return None
        return AccessToken(
            token=token,
            client_id="agentdrive",
            scopes=[],
            expires_at=None,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, RefreshToken):
            self._refresh.pop(token.token, None)

    def _issue_tokens(self, client_id: str, api_key: str, scopes: list[str]) -> OAuthToken:
        refresh = secrets.token_urlsafe(32)
        self._refresh[refresh] = _IssuedRefresh(
            refresh=RefreshToken(token=refresh, client_id=client_id, scopes=scopes, expires_at=None),
            api_key=api_key,
        )
        return OAuthToken(
            access_token=api_key,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh,
            scope=" ".join(scopes) if scopes else None,
        )
