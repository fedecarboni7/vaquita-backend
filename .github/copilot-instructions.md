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

# Auth Flow

1. Frontend sends Google OAuth credential to `POST /auth/google`
2. Backend verifies the credential against Google
3. Backend issues its own JWT using python-jose
4. All protected endpoints expect: `Authorization: Bearer <token>`

# Main Endpoints

```
POST /auth/google   — verify Google credential, return { access_token }
POST /chat          — run user message through the AI agent, return { reply }
GET  /expenses      — return stored expenses for the authenticated user
POST /expenses      — manually create a new expense
```

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