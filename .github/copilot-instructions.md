# Project Overview

This project is a personal finance tracker with an integrated AI agent.

The system is split into two repositories:

- frontend: React web app
- backend: FastAPI API and AI agent

The main interaction happens through a chat interface where the user can send natural language messages such as:

"I spent $20 on coffee"

The backend interprets the message and stores structured financial data.

# Backend Stack

Python
FastAPI
PostgreSQL
LangGraph
Gemini (Google AI Studio)

# Responsibilities

- interpret chat messages
- run the AI agent
- store financial data
- expose REST API endpoints

# Main Endpoints

POST /chat
Processes user messages through the AI agent.

GET /expenses
Returns stored expenses.

POST /expenses
Creates a new expense.