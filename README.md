# 🧠 Expenses Tracker Backend

Backend de una aplicación de gastos impulsada por IA. Permite registrar gastos en lenguaje natural y consultar la información mediante un agente conversacional que utiliza herramientas determinísticas sobre la base de datos.

---

## 🚀 Propósito

Construir **la forma más rápida y privada de entender tus gastos personales usando IA**.

Diferenciales clave:

* Registro de gastos por chat (lenguaje natural)
* Agente de IA que responde preguntas financieras
* Cálculos realizados en SQL (no en el LLM)
* Arquitectura channel‑agnostic (web, Telegram, etc.)
* Enfoque privacy‑first

---

## 🧩 Capacidades (MVP)

* Crear y listar gastos
* Parseo de gastos desde texto libre
* Endpoint conversacional (`/chat`)
* Tools financieras (ej: mayor gasto del mes, gasto por categoría)

---

## 🏗️ Stack

* FastAPI
* SQLAlchemy + Pydantic
* PostgreSQL
* LLM con tool calling

---

## 📌 Estado

🚧 En desarrollo inicial

---

> Registrar gastos debería sentirse como chatear. La privacidad no es negociable.
