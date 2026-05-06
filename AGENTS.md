# Vaquita — Backend

Personal finance tracker with an AI agent as its main feature. Users send natural language messages through a chat interface; the agent classifies intent, extracts structured data, and validates it before persisting.

This is the **backend** repo. The frontend is a separate React app.

---

## Stack

- **Language:** Python 3.12 | **Package manager:** uv
- **Web framework:** FastAPI | **Database:** PostgreSQL
- **ORM:** SQLAlchemy (async) + asyncpg | **Migrations:** Alembic
- **AI orchestration:** LangChain + LangGraph
- **LLMs:** Gemini (Google AI Studio) / Groq
- **Audio transcription:** Groq Whisper
- **Auth:** python-jose (JWT) + Google OAuth | **Linting:** Ruff | **Tests:** pytest + pytest-asyncio

---

## Commands

```bash
uv sync && uv run fastapi dev          # install + dev server
uv run alembic upgrade head            # apply migrations
uv run alembic revision --autogenerate -m "description"  # new migration
```

## Post-Task Validation (mirrors CI)

Propose the user to run after every task that touches backend files:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest -v
```

In a multi-repo task, only run these when backend files were changed.

---

## Database

- Always async sessions — never synchronous SQLAlchemy calls
- Alembic for **all** schema changes — never modify the DB directly
- Consolidate migrations instead of creating revert chains when no production data exists

---

## Testing Philosophy

- **Write tests for:** new endpoints (contract tests) and business logic with arithmetic or validation
- **Don't write tests for:** simple CRUD with no logic, helper utilities, or frontend code
- No coverage thresholds — coverage is informational only
- Small and independent tests — each sets up and tears down its own state
- Prefer real behavior over mocks: use the actual FastAPI test client, avoid patching internals
- One test file per feature (`test_delete_account_contract.py`, `test_installments_logic.py`)
- Use pytest-asyncio for all async tests (`asyncio_mode = "auto"` already configured)

---

## Coding Principles

- Simple and readable over clever — no unnecessary abstractions
- Small, focused functions — async by default for all DB and I/O
- Descriptive variable names
- Agent tools: one tool, one responsibility
- UI copy, error messages (including 429s), and agent replies → **Rioplatense Spanish**
- Code and variable names → **English**