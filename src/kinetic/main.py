"""Composition root: builds the FastAPI app and wires each context's router into it."""

from fastapi import FastAPI
from sqlalchemy import text

from kinetic.db import get_engine


def create_app() -> FastAPI:
    app = FastAPI(title="Kinetic Care Team")

    @app.get("/health")
    def health() -> dict[str, str]:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
