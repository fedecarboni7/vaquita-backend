# vaquita — Backend

Backend de [vaquita](https://vaquita.up.railway.app), una app de finanzas personales con IA integrada. Los usuarios describen transacciones en lenguaje natural a través de un chat, y el agente interpreta la información, arma un borrador y lo devuelve para confirmar antes de persistirlo.

---

## ¿Qué hace?

- **Chat financiero con IA** — registrá gastos, ingresos y transferencias escribiendo o mandando un audio
- **Agente LangGraph** — un nodo LLM interpreta el último mensaje y un paso determinístico resuelve el borrador contra las cuentas y categorías reales del usuario
- **Cálculos determinísticos** — toda la aritmética y lógica de negocio se ejecuta en Python/SQL, no en el LLM
- **BYOK (Bring Your Own Key)** — soporte para Groq y Google AI Studio; si el usuario carga su propia API key, se usa en lugar de la del servidor
- **Rate limiting** — límite diario de uso gratuito por tipo de uso: chat y transcripción de audio mantienen cuotas separadas

### Flujo del agente

`parse` interpreta únicamente el último mensaje y devuelve un parche estructurado usando códigos cortos por request para cuentas y categorías. Luego el grafo deriva a una respuesta conversacional o a `resolve`, que combina el parche con el `pending_draft`, valida y resuelve IDs, infiere la cuenta usada recientemente cuando corresponde y devuelve un `draft` o una `clarification`. El frontend conserva el borrador parcial entre turnos mediante `pending_draft`; el servidor no mantiene estado conversacional.

La respuesta `draft` no escribe en la base de datos: el frontend la muestra y crea la transacción cuando el usuario confirma.

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
| Auth | PyJWT (JWT) + Google OAuth + email y contraseña |
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
# Completar los valores en .env (las cuatro variables de modelos son obligatorias y no tienen valor por defecto)

# Aplicar migraciones
uv run alembic upgrade head

# Iniciar servidor de desarrollo
uv run fastapi dev
```

### Con Docker

```bash
docker compose up
```

### Autenticación por email

Además de Google, la API permite registrarse e iniciar sesión con email y contraseña. Los registros nuevos deben verificar su email; también se pueden recuperar contraseñas mediante un link de un solo uso.

Para habilitar el envío de emails configurá `BREVO_API_KEY`, `MAIL_FROM_EMAIL` y opcionalmente `MAIL_FROM_NAME`. `FRONTEND_URL` se usa para construir los links de verificación y recuperación. Sin `BREVO_API_KEY`, los emails se registran en el log para desarrollo local.

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