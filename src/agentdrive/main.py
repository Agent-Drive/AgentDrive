# src/agentdrive/main.py
from fastapi import FastAPI

from agentdrive.config import settings
from agentdrive.routers import api_keys, collections, files, search


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
    )
    app.include_router(api_keys.router)
    app.include_router(collections.router)
    app.include_router(files.router)
    app.include_router(search.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
