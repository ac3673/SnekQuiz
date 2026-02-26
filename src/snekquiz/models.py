"""Pydantic models for application configuration and quiz data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

# ---------------------------------------------------------------------------
# App configuration (parsed from config/app.yaml)
# ---------------------------------------------------------------------------


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
    search_base: str | None = None
    search_filter: str = "(&(objectclass=person)(SamAccountName={username}))"
    group_attrib: str = "memberOf"
    domain: str | None = None
    use_ssl: bool = True
    admin_groups: list[str] = Field(default_factory=list)
    admin_users: list[str] = Field(default_factory=list)


class AuthSettings(BaseModel):
    admins: dict[str, SecretStr] = Field(default_factory=dict)
    users: dict[str, SecretStr] = Field(default_factory=dict)
    ldap: LdapSettings = LdapSettings()


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_title: str = "SnekQuiz"
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
