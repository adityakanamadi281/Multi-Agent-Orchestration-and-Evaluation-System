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
├── core/               # Foundation: Config, LLM factory, Logging
│   ├── config.py       # pydantic-settings
│   ├── llm.py          # Ollama/OpenAI factory
│   └── logging.py      # structlog setup
├── schemas/            # Data models (SharedContext, Eval, ToolResult)
├── db/                 # Database layer
│   ├── models.py       # SQLAlchemy tables
│   ├── queries.py      # Async CRUD operations
│   └── migrations/     # Alembic versions
├── agents/             # Multi-agent logic
│   ├── graph.py        # StateGraph wiring
│   ├── router.py       # Conditional routing logic
│   ├── decomposition.py, rag.py, critique.py, synthesis.py
│   └── meta.py         # Self-improvement agent
├── tools/              # Agent tools (web_search, code_sandbox, etc.)
├── eval/               # Evaluation pipeline
│   ├── test_cases.py   # Baseline, Ambiguous, Adversarial cases
│   ├── scoring.py      # 6 scoring dimensions
│   └── harness.py      # Execution & persistence
├── api/                # FastAPI service
│   ├── main.py         # App entry point
│   └── routes/         # query, trace, eval, reeval, approve
├── worker/             # ARQ background worker
│   └── tasks.py        # Async job handlers
└── observability/      # Monitoring dashboard
    ├── app.py          # Dashboard API/Routes
    └── templates/      # HTML/JS (Jobs, Logs, Tools, Evaluation)
```

---

## Access Points
| What | URL |
|---|---|
| Swagger UI | http://localhost:8000/docs |
| Observability Dashboard | http://localhost:8001 |
| API Health | http://localhost:8000/health |
