import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.middleware.authentication import AuthenticationMiddleware

from agentdrive.config import settings
from agentdrive.engine.data.session import async_session_factory
from agentdrive.api.files.router import router as files_router
from agentdrive.api.search.router import router as search_router
from agentdrive.api.keys.router import router as keys_router
from agentdrive.api.auth.router import router as auth_router
from agentdrive.api.mcp import create_mcp_server
from agentdrive.engine.pipeline.queue import reap_stuck_files, start_workers, stop_workers


def _load_gcp_credentials() -> None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return
    path = Path("/tmp/gcp-sa.json")
    path.write_text(raw)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)


def create_app() -> FastAPI:
    mcp, oauth_provider = create_mcp_server()
    mcp_asgi = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _load_gcp_credentials()
        async with async_session_factory() as session:
            await reap_stuck_files(session)
        start_workers()
        async with mcp.session_manager.run():
            yield
        await stop_workers()

    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
        lifespan=lifespan,
    )
    app.state.mcp = mcp
    app.state.mcp_oauth = oauth_provider
    app.include_router(keys_router)
    app.include_router(auth_router)
    app.include_router(files_router)
    app.include_router(search_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    @app.get("/mcp/oauth/callback")
    async def mcp_oauth_callback(request: Request):
        return await request.app.state.mcp_oauth.handle_callback(request)

    for route in mcp_asgi.routes:
        app.router.routes.append(route)

    if mcp._token_verifier is not None:
        from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
        from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend

        app.add_middleware(AuthContextMiddleware)
        app.add_middleware(
            AuthenticationMiddleware,
            backend=BearerAuthBackend(mcp._token_verifier),
        )

    return app


app = create_app()
