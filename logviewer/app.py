import uuid
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

app = FastAPI(title="Logviewer", version="0.1.0")

templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/logs")
async def get_logs(
    job_id: str | None = Query(None),
    agent_id: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    from db import AsyncSessionLocal
    from db.queries import get_agent_events, get_tool_call_logs

    async with AsyncSessionLocal() as session:
        if job_id:
            try:
                jid = uuid.UUID(job_id)
            except ValueError:
                return {"logs": [], "total": 0}
            events = await get_agent_events(
                session, jid, agent_id=agent_id, event_type=event_type,
                limit=limit, offset=offset,
            )
            tool_logs = await get_tool_call_logs(session, job_id=jid, limit=limit, offset=offset)
        else:
            events = []
            tool_logs = []

    logs = []
    for e in events:
        logs.append({
            "id": str(e.id),
            "job_id": str(e.job_id),
            "agent_id": e.agent_id,
            "event_type": e.event_type,
            "input_hash": e.input_hash,
            "output_hash": e.output_hash,
            "latency_ms": e.latency_ms,
            "token_count": e.token_count,
            "policy_violation": e.policy_violation,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        })
    for t in tool_logs:
        logs.append({
            "id": str(t.id),
            "job_id": str(t.job_id),
            "agent_id": t.agent_id,
            "event_type": f"tool:{t.tool_name}",
            "input_hash": "",
            "output_hash": "",
            "latency_ms": t.latency_ms,
            "retry_number": t.retry_number,
            "accepted": t.accepted,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        })

    logs.sort(key=lambda x: x.get("timestamp", ""))
    return {"logs": logs, "total": len(logs)}


@app.get("/graph/{job_id}")
async def get_graph(job_id: str):
    from db import AsyncSessionLocal
    from db.queries import get_agent_events
    import uuid as _uuid

    try:
        jid = _uuid.UUID(job_id)
    except ValueError:
        return {"edges": []}

    async with AsyncSessionLocal() as session:
        events = await get_agent_events(session, jid, event_type="graph_edge")

    edges = []
    for e in events:
        payload = e.payload or {}
        edges.append({
            "from_node": payload.get("from", payload.get("agent", "")),
            "to_node": payload.get("to", payload.get("next", "")),
            "reasoning": payload.get("reasoning", payload.get("reason", "")),
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        })

    return {"edges": edges}

