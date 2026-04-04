from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from agentdrive.config import settings
from agentdrive.db.session import async_session_factory
from agentdrive.routers import api_keys, auth, files, knowledge_bases, search
from agentdrive.services.queue import reap_stuck_files, start_workers, stop_workers


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
    app.include_router(api_keys.router)
    app.include_router(auth.router)
    app.include_router(files.router)
    app.include_router(search.router)
    app.include_router(knowledge_bases.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    @app.get("/install.sh", response_class=PlainTextResponse)
    async def install_script():
        script_path = Path("scripts/install.sh")
        if not script_path.is_file():
            script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "install.sh"
        if not script_path.is_file():
            return PlainTextResponse("install script not found", status_code=404)
        return PlainTextResponse(script_path.read_text())

    return app


app = create_app()
