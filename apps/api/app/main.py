from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health, optimize, projects, rag, training


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(optimize.router, prefix="/optimize", tags=["optimize"])
    app.include_router(rag.router, prefix="/rag", tags=["rag"])
    app.include_router(projects.router, prefix="/projects", tags=["projects"])
    app.include_router(training.router, tags=["jobs"])
    return app


app = create_app()
