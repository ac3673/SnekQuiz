"""Shared pytest fixtures for SnekQuiz tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient

from snekquiz import database as db
from snekquiz.auth import User
from snekquiz.models import Quiz

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ---------------------------------------------------------------------------
# Sample quiz data used across tests
# ---------------------------------------------------------------------------

SAMPLE_QUIZ_JSON = json.dumps(
    {
        "quiz_name": "Test Quiz",
        "questions": [
            {
                "id": 1,
                "question_type": "single_answer",
                "question_text": "What is 1+1?",
                "options": [
                    {"id": "A", "text": "1"},
                    {"id": "B", "text": "2"},
                    {"id": "C", "text": "3"},
                ],
                "correct_answers": ["B"],
                "explanation": "1+1=2",
            },
            {
                "id": 2,
                "question_type": "multiple_answer",
                "question_text": "Which are even?",
                "options": [
                    {"id": "A", "text": "2"},
                    {"id": "B", "text": "3"},
                    {"id": "C", "text": "4"},
                ],
                "correct_answers": ["A", "C"],
                "explanation": "2 and 4 are even",
            },
            {
                "id": 3,
                "question_type": "single_answer",
                "question_text": "What is 2+2?",
                "options": [
                    {"id": "A", "text": "3"},
                    {"id": "B", "text": "4"},
                    {"id": "C", "text": "5"},
                ],
                "correct_answers": ["B"],
                "explanation": "2+2=4",
            },
        ],
    }
)


def get_sample_quiz() -> Quiz:
    """Return a parsed Quiz model from the sample data."""
    return Quiz.model_validate_json(SAMPLE_QUIZ_JSON)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_db(tmp_path):
    """Initialise a temporary database and tear it down after the test."""
    db_path = str(tmp_path / "test.db")
    await db.init_db(db_path)
    yield db
    await db.close_db()


@pytest.fixture
async def quiz_id(test_db):
    """Insert the sample quiz and return its id."""
    return await test_db.insert_quiz("Test Quiz", SAMPLE_QUIZ_JSON)


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


def _make_test_app():
    """Build a FastAPI app wired for testing with fake auth."""
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from snekquiz.models import Settings
    from snekquiz.routes import router

    templates_dir = Path(__file__).resolve().parent.parent / "src" / "snekquiz" / "templates"
    static_dir = Path(__file__).resolve().parent.parent / "src" / "snekquiz" / "static"

    app = FastAPI()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.state.templates = Jinja2Templates(templates_dir)
    app.state.settings = Settings()

    class _FakeAuth:
        """Bypass real auth - username comes from the Basic header."""

        def authenticate_user(self, credentials):
            is_admin = credentials.username.startswith("admin")
            return User(
                username=credentials.username, is_admin=is_admin, full_name=credentials.username
            )

    app.state.auth = _FakeAuth()
    app.include_router(router)
    return app


@pytest.fixture
async def app(test_db):
    """Return a FastAPI app connected to the test database."""
    return _make_test_app()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient]:
    """Return an httpx AsyncClient for the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        auth=("testuser", "pass"),
    ) as c:
        yield c


@pytest.fixture
async def admin_client(app) -> AsyncGenerator[AsyncClient]:
    """Return an httpx AsyncClient authenticated as an admin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        auth=("admin", "pass"),
    ) as c:
        yield c
