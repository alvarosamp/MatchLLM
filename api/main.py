from fastapi import FastAPI
from api.routes import edital_routes

def create_app() -> FastAPI:
    app = FastAPI(
        title="Licitação IA API",
        version="0.1.0",
    )

    app.include_router(edital_routes.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()