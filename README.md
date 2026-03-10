# Expenses Tracker — Backend

Backend de una aplicación de gastos impulsada por IA. Permite registrar gastos en lenguaje natural y consultar la información mediante un agente conversacional que utiliza herramientas determinísticas sobre la base de datos.

---

## Propósito

Construir **la forma más rápida y privada de entender tus gastos personales usando IA**.

Diferenciales clave:

- Registro de transacciones por chat en lenguaje natural
- Agente de IA con herramientas determinísticas sobre la base de datos
- Cálculos realizados en SQL (no en el LLM)

---

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Gestor de paquetes | uv |
| Framework web | FastAPI |
| Base de datos | PostgreSQL |
| ORM | SQLAlchemy (async) + asyncpg |
| Migraciones | Alembic |
| Orquestación de IA | LangChain + LangGraph |
| LLM | Gemini (gemini-flash-lite-latest) |
| Auth | python-jose (JWT) + Google OAuth |
| Linting / formato | Ruff |
| Tests | pytest + pytest-asyncio |

---

## Cómo ejecutar

### Con uv (desarrollo)

```bash
uv sync
uv run fastapi dev
```

### Con Docker

```bash
docker compose up
```

---

## Migraciones

```bash
# Crear una nueva migración
uv run alembic revision --autogenerate -m "descripción"

# Aplicar migraciones
uv run alembic upgrade head

# Revertir la última migración
uv run alembic downgrade -1
```

---

## Tests

```bash
uv run pytest
```

---

## Estado

🚧 En desarrollo activo
