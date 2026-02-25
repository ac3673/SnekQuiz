"""Pydantic models for application configuration and quiz data."""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App configuration (parsed from config/app.yaml)
# ---------------------------------------------------------------------------


class AppSettings(BaseModel):
    title: str = "SnekQuiz"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


class DbSettings(BaseModel):
    path: str = "data/snekquiz.db"


class LdapSettings(BaseModel):
    """Optional Active Directory / LDAP authentication.

    When ``server_url`` is set, users not found in the local admins/users
    maps will be authenticated via an LDAP simple-bind.
    ``domain`` is prepended to the username as ``domain\\username`` when
    binding (set to the NetBIOS domain name, e.g. ``CORP``).
    ``admin_groups`` lists LDAP group CNs whose members are treated as
    admins; everyone else is a regular quiz-taker.
    """

    server_url: str | None = None
    domain: str | None = None
    use_ssl: bool = True
    admin_groups: list[str] = []


class AuthSettings(BaseModel):
    admins: dict[str, str] = {}
    users: dict[str, str] = {}
    ldap: LdapSettings = LdapSettings()


class Settings(BaseModel):
    app: AppSettings = AppSettings()
    db: DbSettings = DbSettings()
    auth: AuthSettings = AuthSettings()


# ---------------------------------------------------------------------------
# Quiz data models
# ---------------------------------------------------------------------------


class Option(BaseModel):
    id: str
    text: str


class Question(BaseModel):
    id: int
    question_type: str  # "single_answer" | "multiple_answer"
    question_text: str
    options: list[Option]
    correct_answers: list[str]
    explanation: str


class Quiz(BaseModel):
    quiz_name: str
    questions: list[Question]
