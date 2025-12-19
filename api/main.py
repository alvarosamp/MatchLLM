from fastapi import FastAPI
from api.routes import edital_routes
from api.routes import produto_routes
from db.session import init_db

def create_app() -> FastAPI:
    app = FastAPI(
        title="Licitação IA API",
        version="0.1.0",
    )

    app.include_router(edital_routes.router)
    app.include_router(produto_routes.router)

    # initialize DB (development only)
    init_db()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()