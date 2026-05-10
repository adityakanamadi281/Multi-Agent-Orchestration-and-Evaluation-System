# Multi-Agent LLM Orchestration System

Production-grade multi-agent LLM orchestration and evaluation system built with LangGraph, Ollama, FastAPI, and ARQ.

---

## Features
- **Advanced Agentic Workflow**: Multi-agent orchestration using LangGraph (Decomposition, RAG, Critique, Synthesis).
- **Real-time Knowledge**: Live web search integration via Exa API and local vector retrieval.
- **Evaluation Pipeline**: Automated testing suite with 15 cases and 6 scoring dimensions (Correctness, Citations, etc.).
- **Self-Improvement**: MetaAgent loop that analyzes failures and proposes prompt optimizations.
- **Observability**: Interactive dashboard for real-time job tracing, agent logs, and graph visualization.
- **Reliability**: Token budget enforcement, automatic context compression, and robust error handling.

---

## Tech Stack
- **Framework**: LangGraph
- **LLM Engine**: Ollama (OpenAI Compatible)
- **API Framework**: FastAPI
- **Task Queue**: ARQ + Redis
- **Database**: PostgreSQL (SQLAlchemy + Alembic)
- **Vector Search**: ChromaDB
- **Infrastructure**: Docker + Docker Compose
- **Environment**: uv

---

## Setup and Installation

### 1. Clone & Navigation
```bash
git clone https://github.com/adityakanamadi281/Multi-Agent-Orchestration-and-Evaluation-System.git
cd Multi-Agent-Orchestration-and-Evaluation-System
```

### 2. Prerequisites
- Docker + Docker Compose
- [uv](https://github.com/astral-sh/uv) (for local development)
- API keys: [Exa](https://dashboard.exa.ai/api-keys)

### 3. Configure Environment
```bash
cp .env.example .env
```
Edit `.env` and fill in your keys:
```
OLLAMA_BASE_URL=http://localhost:11434/v1
MODEL_NAME=gemma4:31b-cloud  
EXA_API_KEY=your_key_here
```

### 4. Run with Docker
```bash
docker compose up --build
```

### 4. Running Locally (Alternative)
Ensure PostgreSQL and Redis are running, then:
```bash
uv sync
uv run alembic upgrade head

# Terminal 1: API
uv run uvicorn api.main:app --reload --port 8000

# Terminal 2: Worker
uv run arq worker.tasks.WorkerSettings

# Terminal 3: Dashboard
uv run uvicorn observability.app:app --reload --port 8001
```

---

## Project Structure

```
multi-agent-system/
├── agents/
│   ├── compression.py
│   ├── critique.py
│   ├── decomposition.py
│   ├── graph.py
│   ├── meta.py
│   ├── prompts.py
│   ├── rag.py
│   ├── rag_chunks.py
│   ├── router.py
│   └── __init__.py
├── api/
│   ├── Dockerfile
│   ├── dependencies.py
│   ├── main.py
│   ├── routes/
│   │   ├── approve.py
│   │   ├── eval.py
│   │   ├── query.py
│   │   ├── reeval.py
│   │   ├── trace.py
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── responses.py
│   │   └── __init__.py
│   └── __init__.py
├── context_manager/
│   ├── budget.py
│   └── __init__.py
├── core/
│   ├── config.py
│   ├── llm.py
│   ├── logging.py
│   └── __init__.py
├── db/
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial.py
│   ├── models.py
│   ├── queries.py
│   └── __init__.py
├── eval/
│   ├── harness.py
│   ├── scoring.py
│   ├── test_cases.py
│   ├── test_cases_data.py
│   └── __init__.py
├── observability/
│   ├── Dockerfile
│   ├── app.py
│   ├── templates/
│   │   └── index.html
│   └── __init__.py
├── schemas/
│   ├── context.py
│   ├── eval.py
│   ├── tool_result.py
│   └── __init__.py
├── tools/
│   ├── base.py
│   ├── code_sandbox.py
│   ├── db_lookup.py
│   ├── self_reflection.py
│   ├── tool_logger.py
│   ├── web_search.py
│   └── __init__.py
├── worker/
│   ├── Dockerfile
│   ├── tasks.py
│   └── __init__.py
├── .dockerignore
├── .env.example
├── .gitignore
├── .python-version
├── alembic.ini
├── architecture.md
├── docker-compose.yml
├── prompt.md
├── pyproject.toml
├── README.md
└── uv.lock
```

---

## Access Points
| What | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| Observability Dashboard | http://localhost:8001 |
| API Health | http://localhost:8000/health |
