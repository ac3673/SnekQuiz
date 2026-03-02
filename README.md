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

- **Simple auth** – HTTP Basic. Admins can do admin things, users can take quizzes
- **Quiz list** – See what's available, what you've finished, what's left to do
- **One question at a time** – HTMX gives you instant feedback without page reloads
- **Results** – Your score, what you got wrong, what the right answers were
- **Admin stuff** – Upload quizzes (JSON), see how everyone's doing, delete quizzes when needed
- **API** – POST new quizzes, GET quiz lists, DELETE when you messed up
- **SQLite** – Because sometimes simple is better. No database server required
- **YAML config** – Tweak settings without touching code

## Quick Start

```bash
# Install dependencies (requires Python 3.13+ and uv)
uv sync

# Run the app (default: http://0.0.0.0:8001)
uv run snekquiz

# or run via the CLI entry-point
snekquiz

# or via python -m
python -m snekquiz

# Run with custom host/port, SSL, auto-reload for development
snekquiz --host localhost --port 8000 --ssl_keyfile key.pem --ssl_certfile cert.pem --reload

# Run with custom config files
snekquiz --config /path/to/app.yaml --log-config /path/to/logging.yaml

# or via uvicorn directly. NB this will expect `uvicorn` CLI args only
uvicorn snekquiz:create_app --factory --host 0.0.0.0 --port 8001
```

The server starts at **http://0.0.0.0:8001** by default. Log in with one of the default
accounts configured in `src/snekquiz/config/app.yaml`:

Admins can also take quizzes. The admin portal is at **http://0.0.0.0:8001/admin**.

## Adding Quizzes

Via the **admin portal** at `/admin/upload`, or via the API:

```bash
curl -u admin:admin \
  -H "Content-Type: application/json" \
  -d @quiz.json \
  http://localhost:8001/api/quizzes
```

Quiz format is pretty straightforward:

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

A user specified config file can be supplied with:

- The `APP_CONFIG` environment variable: `export APP_CONFIG=/path/to/config.yaml`
- The `--config` (or `-c`) CLI argument: `snekquiz --config /path/to/config.yaml`

**Logging config** (`src/snekquiz/config/logging.yaml`) provides default logging config.

A user specified config file can be supplied with:

- The `LOG_CONFIG` environment variable: `export LOG_CONFIG=/path/to/logging.yaml`
- The `--log-config` (or `-l`) CLI argument: `snekquiz --log-config /path/to/logging.yaml`

When running with `uvicorn` directly, you must use the environment variable approach.

### CLI Arguments

```bash
snekquiz --help
```

Available options:
- `--config`, `-c`: Path to app config YAML (default: bundled config/app.yaml)
- `--log-config`, `-l`: Path to logging config YAML (default: bundled config/logging.yaml)
- `--host`: Host to bind to (default: 0.0.0.0)
- `--port`: Port to bind to (default: 8001)
- `--reload`: Enable auto-reload for development
- `--ssl_keyfile`: Path to SSL key file
- `--ssl_certfile`: Path to SSL certificate file

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

White, black, navy, teal, and more teal: `#ffffff` · `#000000` · `#002554` · `#099d91` · `#00cc99`

## License

See [LICENSE](LICENSE).

---

<sub>Made with questionable judgment and Claude Opus 4.6.</sub>
