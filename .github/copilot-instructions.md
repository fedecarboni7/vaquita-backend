# Project Context

Personal finance tracker with an AI agent as its main feature. Users send natural language messages ("I spent $20 on coffee") through a chat interface, and the AI agent interprets them and stores structured financial data.

This is the **backend** repo. The frontend is a separate React app.

# Stack

- **Language:** Python
- **Package manager:** uv
- **Web framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy (async) + asyncpg
- **Migrations:** Alembic
- **AI orchestration:** LangChain + LangGraph
- **LLM:** Gemini via Google AI Studio
- **Auth:** python-jose (JWT)

# Running the Project

```bash
uv sync
uv run fastapi dev
```

# Required Post-Task Validation (Mirror CI)

After finishing any task or code edit in the backend repo, run the same checks used in CI:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest -v
```

In a multi-repo task, run these backend commands only when backend files were changed.

# Auth Flow

1. Frontend sends Google OAuth credential to `POST /auth/google`
2. Backend verifies the credential against Google
3. Backend issues its own JWT using python-jose
4. All protected endpoints expect: `Authorization: Bearer <token>`

# Testing Philosophy

- Write tests for: new endpoints (contract tests) and business logic with arithmetic or validation
- Do NOT write tests for: helper utilities, simple CRUD with no logic, or frontend code
- No coverage thresholds — coverage is informational only, not a CI gate
- Keep tests small and independent — each test should set up and tear down its own state
- Prefer real behavior over mocks: use the actual FastAPI test client, avoid patching internals
- One test file per feature or module (e.g. `test_delete_account_contract.py`)
- Use pytest-asyncio for all async tests (`asyncio_mode = "auto"` is already configured)

# AI Agent

The chat feature is handled by a LangGraph agent. The agent:

- Receives the user's natural language message
- Decides whether to store a transaction, answer a question, or generate an insight
- Uses tools to interact with the database
- Returns a natural language reply

When working on agent logic, keep tools small and single-purpose.

# Database

- SQLAlchemy async models
- Alembic for all schema changes — never modify the DB directly
- asyncpg as the async driver

Always use async sessions. Never use synchronous SQLAlchemy calls.

# Coding Principles

- Simple and readable over clever
- Avoid unnecessary abstractions
- Keep functions small and focused
- Use descriptive variable names
- Async by default — all DB access and I/O should be async
- Keep agent tools focused: one tool, one responsibility