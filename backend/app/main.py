"""FastAPI 应用入口 — api 组"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, documents, faq, health, ingest, kb_files
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="计算机学院智能问答系统 — 课程项目骨架",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(faq.router, prefix=prefix)
    app.include_router(ingest.router, prefix=prefix)
    app.include_router(documents.router, prefix=prefix)
    app.include_router(kb_files.router, prefix=prefix)

    return app


app = create_app()
