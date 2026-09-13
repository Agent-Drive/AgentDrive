from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from agentdrive.config import settings
from agentdrive.engine.data.session import async_session_factory
from agentdrive.api.files.router import router as files_router
from agentdrive.api.search.router import router as search_router
from agentdrive.api.keys.router import router as keys_router
from agentdrive.api.auth.router import router as auth_router
from agentdrive.engine.pipeline.queue import reap_stuck_files, start_workers, stop_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await reap_stuck_files(session)
    start_workers()
    yield
    await stop_workers()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
        lifespan=lifespan,
    )
    app.include_router(keys_router)
    app.include_router(auth_router)
    app.include_router(files_router)
    app.include_router(search_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    @app.get("/install.sh", response_class=PlainTextResponse)
    async def install_script():
        script_path = Path("scripts/install.sh")
        if not script_path.is_file():
            script_path = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "install.sh"
        if not script_path.is_file():
            return PlainTextResponse("install script not found", status_code=404)
        return PlainTextResponse(script_path.read_text())

    return app


app = create_app()
