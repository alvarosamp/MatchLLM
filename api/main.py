import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth.routes import router as auth_router
from api.routes import edital_routes
from api.routes import match_routes
from api.routes import produto_routes
from db.session import init_db

def create_app() -> FastAPI:
    app = FastAPI(
        title="Licitação IA API",
        version="0.1.0",
    )

    cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    cors_origins = [o.strip() for o in cors_origins if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)

    app.include_router(edital_routes.router)
    app.include_router(match_routes.router)
    app.include_router(produto_routes.router)

    # initialize DB (development only)
    init_db()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def root():
        return {"message": "MatchLLM API", "docs": "/docs"}

    return app


app = create_app()