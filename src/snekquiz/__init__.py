"""SnekQuiz - MCQ quiz web application."""

from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from snekquiz import database as db
from snekquiz.auth import load_users
from snekquiz.models import Settings
from snekquiz.routes import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger("snekquiz")

_PKG_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _PKG_DIR / "config"
_TEMPLATES_DIR = _PKG_DIR / "templates"
_STATIC_DIR = _PKG_DIR / "static"

# Module-level overrides set by main() before uvicorn starts.
# create_app() reads these so the factory picks up CLI arguments.
_app_config_path: Path | None = None
_log_config_path: Path | None = None


def _resolve_app_config() -> Path:
    """Return the effective app config path."""
    if _app_config_path is not None:
        return _app_config_path
    return _CONFIG_DIR / "app.yaml"


def _resolve_log_config() -> Path:
    """Return the effective logging config path."""
    if _log_config_path is not None:
        return _log_config_path
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
    settings = _load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Startup / shutdown."""
        logger.info("Starting %s", settings.app.title)
        await db.init_db(settings.db.path)
        load_users(settings.auth.admins, settings.auth.users, settings.auth.ldap)
        yield
        await db.close_db()
        logger.info("Stopped %s", settings.app.title)

    app = FastAPI(
        title=settings.app.title,
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
    args = parser.parse_args()

    # Store overrides at module level so create_app() can read them
    global _app_config_path, _log_config_path
    _app_config_path = args.config
    _log_config_path = args.log_config

    settings = _load_settings()
    uvicorn.run(
        "snekquiz:create_app",
        factory=True,
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )
