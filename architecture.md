# Architecture

## Docker Services

The system runs as 5 containerised services via `docker-compose.yml`:

1. **db** — PostgreSQL 16 with asyncpg driver. Stores jobs, agent events, tool call logs, eval runs, prompt rewrites, and approvals.
2. **redis** — Redis 7, used for ARQ job queuing and pub/sub channels for real-time SSE streaming.
3. **api** — FastAPI server on port 8000. Accepts queries, serves SSE streams via Redis subscription, provides trace/eval/approve/reeval endpoints.
4. **worker** — ARQ background worker. Runs the LangGraph pipeline (`process_query_job`), eval harness (`run_eval_harness`), and targeted re-eval (`run_targeted_reeval`).
5. **observability** — FastAPI on port 8001 with Jinja2 HTML templates. Provides a browser-based dashboard for jobs, agent logs, tool calls, and graph edge visualisation.

## LangGraph StateGraph

The multi-agent pipeline is built as a `StateGraph` with a `SharedContext` Pydantic model as the shared state:

- **5 agent nodes**: decomposition, rag, critique, synthesis, compression
- **1 conditional edge router**: `orchestrator_router` — an LLM-powered decision function that examines the current state and picks the next node. Not a graph node itself; it's registered as a conditional edge.
- **Annotated reducers**: Append-only fields (`tool_call_log`, `critique_results`, `routing_log`) use `Annotated[list, operator.add]` so each node returns only NEW items — the graph merges them automatically.

### Execution flow

```
decomposition_node → orchestrator_router →
  rag_node → critique_node → synthesis_node → END
  
  Any BudgetExceededException → compression_node → back to rag_node
```

### SharedContext state object

- `job_id`, `original_query`: set at start, never modified
- `sub_tasks`: set by decomposition, read by RAG
- `agent_outputs`: set by rag, read by critique and synthesis
- `critique_results`: append-only, set by critique, read by synthesis
- `final_answer`, `provenance_map`: set by synthesis
- `tool_call_log`, `routing_log`: append-only, set by all nodes

## LLM Integration

All LLM calls go through **Ollama** using the `openai` AsyncOpenAI SDK (OpenAI-compatible mode):
- Base URL: `http://localhost:11434/v1` (configurable)
- Model: `nemotron-3-super:cloud` (configurable via `.env`)
- Every call uses `tools + tool_choice="required"` for structured output
- Runs locally, no external LLM API keys required for core inference

## Tools

| Tool | Provider | Failure Handling |
|------|----------|-----------------|
| web_search | Exa SDK (real API via `asyncio.to_thread`) | TIMEOUT→retry 1.5x; EMPTY→rephrase once; MALFORMED→skip |
| code_sandbox | Python subprocess with tempdir | TIMEOUT→kill process; MALFORMED→skip |
| db_lookup | NL→SQL via LLM, SELECT-only guard, asyncpg | MALFORMED→skip non-SELECT |
| self_reflection | LLM contradiction scanner over agent outputs | Returns empty list on failure |

## Context Budget System

- Each agent has a max token budget declared at node start
- `ContextBudgetManager.consume()` counts tokens using `tiktoken cl100k_base`
- `BudgetExceededException` is never swallowed — always returns a routing patch to `compression_node`
- `ContextBudgetManager` uses `asyncio.Lock` for thread safety
- Module-level singleton in `context_manager/__init__.py`

## Worker: Redis Pub/Sub + SSE

1. API creates a Job row, enqueues `process_query_job` via ARQ
2. API subscribes to `job:{job_id}` Redis channel
3. Worker runs `compiled_graph.astream()` — yields per-node
4. Worker publishes each node event to Redis channel
5. API forwards events to client as SSE (`text/event-stream`)

## Eval Pipeline

- 15 test cases: 5 baseline, 5 ambiguous, 5 adversarial
- 6 scoring dimensions: answer_correctness, citation_accuracy, contradiction_resolution, tool_efficiency, budget_compliance, critique_agreement
- Each dimension returns `ScoreResult(score: float, justification: str)`
- Exact agent prompts stored per run for reproducibility
- EvalCase child rows per dimension per run for granular querying

## Self-Improving Loop

1. Eval harness runs all 15 test cases
2. MetaAgent identifies worst (dimension, agent) pair
3. LLM proposes a prompt rewrite with unified diff
4. Stored as `PromptRewrite(status="pending")`
5. Human approves/rejects via `POST /approve/{rewrite_id}`
6. Approved rewrites tested via targeted re-eval
7. Performance delta stored on PromptRewrite

**Known limitation**: Prompt rewrites use module-level dict patching (not hot-reload). Worker restart needed to persist.

## Storage

| Component | Technology |
|-----------|-----------|
| Job/Event/Tool data | PostgreSQL via SQLAlchemy 2.0 async |
| Vector knowledge base | ChromaDB PersistentClient (in-process) |
| Job queue | Redis via ARQ |
| Pub/sub | Redis channels |
| Logging | structlog JSON (production) / ConsoleRenderer (dev) |