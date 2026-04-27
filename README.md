# Vaquita — Backend

Backend de [Vaquita](https://vaquita.up.railway.app), una app de finanzas personales con IA integrada. Los usuarios registran transacciones en lenguaje natural a través de un chat, y el agente interpreta, estructura y persiste la información automáticamente.

---

## ¿Qué hace?

- **Chat financiero con IA** — registrá gastos, ingresos y transferencias escribiendo o mandando un audio
- **Agente LangGraph multi-nodo** — clasifica la intención, extrae los datos y valida contra las cuentas y categorías reales del usuario
- **Cálculos determinísticos** — toda la aritmética y lógica de negocio se ejecuta en Python/SQL, no en el LLM
- **BYOK (Bring Your Own Key)** — soporte para Groq y Google AI Studio; si el usuario carga su propia API key, se usa en lugar de la del servidor
- **Rate limiting** — límite diario de uso gratuito compartido entre chat y transcripción de audio

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
| LLM | Gemini / Groq (configurable por usuario) |
| Transcripción de audio | Whisper vía Groq / Gemini |
| Auth | python-jose (JWT) + Google OAuth |
| Linting / formato | Ruff |
| Tests | pytest + pytest-asyncio |

---

## Cómo ejecutar

### Requisitos

- Python 3.12+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
# Instalar dependencias
uv sync

# Configurar variables de entorno
cp .env.example .env
# Completar los valores en .env

# Aplicar migraciones
uv run alembic upgrade head

# Iniciar servidor de desarrollo
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
uv run pytest -v
```

---

## Licencia

MIT