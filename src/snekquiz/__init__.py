from __future__ import annotations

import logging
import logging.config
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import database as db
from .auth import AuthManager
from .models import Settings
from .routes import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

log = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _PKG_DIR / "config"
_TEMPLATES_DIR = _PKG_DIR / "templates"
_STATIC_DIR = _PKG_DIR / "static"

# Module-level overrides set by main() before uvicorn starts.
# create_app() reads these so the factory picks up CLI arguments.


def _resolve_app_config() -> Path:
    """Return the effective app config path."""
    if app_config := os.getenv("APP_CONFIG"):
        return Path(app_config)
    return _CONFIG_DIR / "app.yaml"


def _resolve_log_config() -> Path:
    """Return the effective logging config path."""
    if log_config := os.getenv("LOG_CONFIG"):
        return Path(log_config)
    return _CONFIG_DIR / "logging.yaml"


def _load_settings(config_path: Path | None = None) -> Settings:
    """Parse an app YAML config file into a validated Pydantic model."""
    path = config_path or _resolve_app_config()
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f)
        return Settings.model_validate(raw or {})
    return Settings()


def _setup_logging(log_config_path: Path | None = None) -> None:
    """Configure logging from a YAML file via dictConfig."""
    path = log_config_path or _resolve_log_config()
    if path.exists():
        with open(path) as f:
            config = yaml.safe_load(f)
        # Ensure log directory exists
        for handler in config.get("handlers", {}).values():
            if "filename" in handler:
                Path(handler["filename"]).parent.mkdir(parents=True, exist_ok=True)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    """Application factory."""
    _setup_logging()
    log.debug("Create app in factory")
    settings = _load_settings()
    log.debug(f"Loaded settings {settings}")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Startup / shutdown."""
        log.info(f"Starting {settings.app_title}")
        await db.init_db(settings.db.path)
        app.state.auth = AuthManager(settings.auth)
        yield
        await db.close_db()
        log.info(f"Stopped {settings.app_title}")

    app = FastAPI(
        title=settings.app_title,
        lifespan=lifespan,
    )

    # Jinja2 templates
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    class _Templates:
        """Minimal adapter matching Starlette's Jinja2Templates interface."""

        def TemplateResponse(  # noqa: N802
            self,
            name: str,
            context: dict,
            status_code: int = 200,
        ) -> HTMLResponse:
            template = env.get_template(name)
            html = template.render(**context)
            return HTMLResponse(content=html, status_code=status_code)

    app.state.templates = _Templates()
    app.state.settings = settings

    # Static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Routes
    app.include_router(router)
    log.debug("App factory finished")
    return app


def main() -> None:
    """CLI entry-point: ``snekquiz`` / ``python -m snekquiz``."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(
        prog="snekquiz",
        description="SnekQuiz - MCQ quiz web application",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to app config YAML (default: bundled config/app.yaml)",
    )
    parser.add_argument(
        "-l",
        "--log-config",
        type=Path,
        default=None,
        help="Path to logging config YAML (default: bundled config/logging.yaml)",
    )
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--ssl_keyfile", type=str, default=None)
    parser.add_argument("--ssl_certfile", type=str, default=None)

    args = parser.parse_args()
    if args.config:
        os.environ["APP_CONFIG"] = args.config.as_posix()
    if args.log_config:
        os.environ["LOG_CONFIG"] = args.log_config.as_posix()
    uvicorn.run(
        "snekquiz:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
    )
