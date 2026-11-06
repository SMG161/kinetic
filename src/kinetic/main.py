"""Composition root: builds the FastAPI app and wires each context's router into it."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from kinetic.db import get_engine
from kinetic.directory.api import routes as directory_api
from kinetic.identity.api import routes as identity_api

# A plain HTML/JS page for trying the API by hand. Served from the same origin as
# the API, so the browser needs no CORS setup.
DEMO_DIR = Path(__file__).parents[2] / "demo"


def create_app() -> FastAPI:
    app = FastAPI(title="Kinetic Care Team")
    identity_api.install(app)
    directory_api.install(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    app.mount("/demo", StaticFiles(directory=DEMO_DIR, html=True), name="demo")
    return app


app = create_app()
