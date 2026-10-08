# Vaquita — Backend

Personal finance tracker with an AI agent as its main feature. Users send natural language messages through a chat interface; the agent interprets transaction patches, resolves them deterministically, and returns drafts before persistence.

This is the **backend** repo. The frontend is a separate React app.

---

## Stack

- **Language:** Python 3.12 | **Package manager:** uv
- **Web framework:** FastAPI | **Database:** PostgreSQL
- **ORM:** SQLAlchemy (async) + asyncpg | **Migrations:** Alembic
- **AI orchestration:** LangChain + LangGraph
- **LLMs:** Gemini (Google AI Studio) / Groq
- **Audio transcription:** Groq Whisper / Gemini
- **Auth:** PyJWT (JWT) + Google OAuth + email y contraseña | **Linting:** Ruff | **Tests:** pytest + pytest-asyncio
- **Free AI limit:** 5 requests per day

## AI Agent (LangGraph)

- The graph is `parse` (LLM call with one retry on parse errors) → conditional router → `resolve` (deterministic) or `handle_chat` → `END`.
- `parse` interprets only the latest user message and returns a patch. Its structured-output schema is built per request with `Literal` values for short-lived account and category codes such as `a1`, `e1`, `e1.2`, `i1`, and `i1.1`; real database IDs are never sent to or returned by the LLM.
- `resolve` in `app/agent/resolve.py` is a pure function. It merges the patch onto the pending draft, resolves short codes to user-owned IDs, infers an expense or income account from the user's last-used account for `(type, currency)`, determines missing fields, and builds clarification text.
- A draft can be blocked by a missing amount and, for transfers, missing origin or destination. Expense and income accounts are inferred when possible; an account is otherwise required. Inferred accounts are marked in `inferred_fields`.
- The server is stateless across turns. The frontend echoes the previous clarification `data` as `pending_draft` in `POST /chat`; the backend whitelists the fields, sanitizes the draft, and drops IDs that do not belong to the current user.
- Agent outcomes are `draft`, `clarification`, or `answer`. The resolver computes `missing_fields` internally; the current public `ChatResponse` schema returns the response type, message, and data payload, without a separate `missing_fields` response field.
- Structured-output and validation failures are retried once before returning a friendly Spanish fallback message. Rate-limit and provider-auth errors are not retried and retain the router's existing provider and fallback-model handling.
- Model names are configured only via environment variables (`GROQ_DEFAULT_MODEL`, `GOOGLE_DEFAULT_MODEL`, `GROQ_FALLBACK_MODEL`, `GOOGLE_FALLBACK_MODEL`), never hardcoded.
- Each agent turn emits one structured metadata-only log line. It records routing and outcome metadata, never message text, amounts, descriptions, or names.
- The LLM interprets, including turning the amount into a number. Arithmetic such as installments, validation, id resolution, account inference, and database writes stay in Python.

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
- One test file per feature (`test_delete_account_contract.py`, `test_agent_resolve.py`)
- Use pytest-asyncio for all async tests (`asyncio_mode = "auto"` already configured)

---

## Coding Principles

- Simple and readable over clever — no unnecessary abstractions
- Small, focused functions — async by default for all DB and I/O
- Descriptive variable names
- Agent nodes: one node, one responsibility
- UI copy, error messages (including 429s), and agent replies → **Rioplatense Spanish**
- Code and variable names → **English**