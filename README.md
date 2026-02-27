# SnekQuiz 🐍

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3130/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/type--checked-ty-blue?logo=python&logoColor=white)](https://github.com/astral-sh/ty)
[![pre-commit](https://img.shields.io/badge/pre--commit-prek-blue?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Coverage](reports/coverage-badge.svg)](https://github.com/ac3673/snekquiz)

A minimalist multiple-choice quiz web application built with **FastAPI**, **HTMX**, and **Jinja2** templates.

> [!NOTE]
> This project was vibe-coded with [Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6) 🤖✨

## Features

- **Role-based auth** – admins and quiz-takers via HTTP Basic authentication
- **Quiz catalogue** – home page lists all quizzes, highlighting completed vs new
- **Paginated questions** – one question at a time with instant feedback via HTMX
- **Results page** – score summary with per-question review (safe to refresh)
- **Admin portal** – upload quizzes, view aggregated results, delete quizzes
- **Quiz API** – `POST /api/quizzes` (admin), `GET /api/quizzes`, `DELETE /api/quizzes/{id}` (admin)
- **SQLite storage** – lightweight, zero-config persistence via aiosqlite
- **YAML config** – app settings parsed into Pydantic models, logging via `dictConfig`

## Quick Start

```bash
# Install dependencies (requires Python 3.13+ and uv)
uv sync

# Run the app
uv run snekquiz

# or run via the CLI entry-point
snekquiz

# or via python -m
python -m snekquiz

# or via uvicorn directly
uvicorn snekquiz:create_app --factory
```

The server starts at **http://localhost:8000**. Log in with one of the default
accounts configured in `src/snekquiz/config/app.yaml`:

Admins can also take quizzes. The admin portal is at **http://localhost:8000/admin**.

## Uploading a Quiz

Via the **admin portal** at `/admin/upload`, or via the API:

```bash
curl -u admin:admin \
  -H "Content-Type: application/json" \
  -d @quiz.json \
  http://localhost:8000/api/quizzes
```

See the example quiz format below.

<details>
<summary>Example quiz.json</summary>

```json
{
  "quiz_name": "Cities quiz",
  "questions": [
    {
      "id": 1,
      "question_type": "single_answer",
      "question_text": "What is the capital of France?",
      "options": [
        {"id": "A", "text": "Paris"},
        {"id": "B", "text": "London"},
        {"id": "C", "text": "Berlin"},
        {"id": "D", "text": "Madrid"}
      ],
      "correct_answers": ["A"],
      "explanation": "Paris is the capital and largest city of France."
    },
    {
      "id": 2,
      "question_type": "multiple_answer",
      "question_text": "Which of the following are cities in Europe?",
      "options": [
        {"id": "A", "text": "Paris"},
        {"id": "B", "text": "London"},
        {"id": "C", "text": "Singapore"},
        {"id": "D", "text": "Perth"}
      ],
      "correct_answers": ["A", "B", "D"],
      "explanation": "Paris (France), London (England), Perth (Scotland)."
    }
  ]
}
```

</details>

## Project Structure

```
src/snekquiz/
├── __init__.py          # App factory & CLI entry-point
├── auth.py              # Authentication including LDAP layer
├── database.py          # SQLite database layer (aiosqlite)
├── models.py            # Pydantic models (config + quiz data)
├── routes.py            # Web & API routes
├── config/
│   ├── app.yaml         # Application settings
│   └── logging.yaml     # Python logging dictConfig
├── templates/
│   ├── base.html        # Base layout
│   ├── home.html        # Quiz catalogue
│   ├── complete.html    # Quiz completion interstitial
│   ├── question.html    # Question page
│   ├── results.html     # Results / score page
│   ├── admin/
│   │   ├── dashboard.html    # Admin overview with aggregated stats
│   │   ├── quiz_detail.html  # Per-quiz attempt drilldown
│   │   └── upload.html       # Quiz upload form
│   └── partials/
│       └── answer_feedback.html   # HTMX fragment for answer feedback
└── static/
    └── style.css        # Minimalist CSS theme
```

## Configuration

**App config** (`src/snekquiz/config/app.yaml`) provides default config if no path is provided.

A user specified config file can supplied with:

- The `APP_CONFIG` environment variable is read to load a config file, eg `export APP_CONFIG=/path/to/config.yaml`.
- Providing `-c` or `--app-config` arguments


**Logging config** (`src/snekquiz/config/logging.yaml`) provides default logging config.

A user specified config file can supplied with:
- The `LOG_CONFIG` environment variable
- The `-l` or `--log-config` arguments

When running with `uvicorn` you must use the environment variable approach.

## Development

```bash
# Lint & format
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run ty check

# Pre-commit hooks (using prek)
prek install
prek run --all-files
```

## Theme

Colours: `#ffffff` · `#000000` · `#002554` · `#099d91` · `#00cc99`

## License

See [LICENSE](LICENSE).

---

<sub>Built with vibes and [Claude Opus 4.6](https://www.anthropic.com/claude).</sub>
