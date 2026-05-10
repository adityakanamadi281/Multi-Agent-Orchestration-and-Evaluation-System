from core.config import settings
import json
import hashlib
import uuid
import asyncio
from datetime import datetime, timezone
from core.llm import get_client
from core.logging import logger
from context_manager import budget_manager
from schemas.context import SharedContext, AgentOutput
from agents.prompts import AGENT_PROMPTS
from agents.rag_chunks import _get_knowledge_chunks

RAG_TOOL = {
    "type": "function",
    "function": {
        "name": "produce_rag_answer",
        "description": "Produce a cited answer from retrieved knowledge chunks",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string"},
                            "source_chunk_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["claim", "source_chunk_ids"],
                    },
                },
            },
            "required": ["answer", "citations"],
        },
    },
}

REFINE_TOOL = {
    "type": "function",
    "function": {
        "name": "refine_query",
        "description": "Output a refined follow-up search query",
        "parameters": {
            "type": "object",
            "properties": {
                "refined_query": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["refined_query", "reasoning"],
        },
    },
}


def _ensure_chroma_chunks(collection) -> None:
    knowledge_chunks = _get_knowledge_chunks()
    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
    if len(existing_ids) >= len(knowledge_chunks):
        return
    docs = []
    ids = []
    metadatas = []
    for chunk in knowledge_chunks:
        if chunk["id"] not in existing_ids:
            docs.append(chunk["text"])
            ids.append(chunk["id"])
            metadatas.append(chunk["metadata"])
    if docs:
        collection.add(documents=docs, ids=ids, metadatas=metadatas)


async def rag_node(state: SharedContext) -> dict:
    job_id = state.job_id
    agent_id = "rag_node"
    start = datetime.now(timezone.utc)

    await budget_manager.declare_budget(agent_id, 8000)

    import chromadb

    chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    collection = chroma_client.get_or_create_collection("knowledge_base")
    _ensure_chroma_chunks(collection)

    query = state.original_query
    client = get_client()

    # --- Step 1: Local Knowledge Base Search ---
    hop1_results = collection.query(query_texts=[query], n_results=3)
    local_chunks = []
    for i, chunk_text in enumerate(hop1_results.get("documents", [[]])[0]):
        local_chunks.append({"id": f"local_{i}", "text": chunk_text})

    # --- Step 2: Live Web Search via Exa ---
    web_chunks = []
    if settings.EXA_API_KEY:
        try:
            from exa_py import Exa
            exa = Exa(api_key=settings.EXA_API_KEY)
            search_response = await asyncio.to_thread(
                exa.search_and_contents,
                query,
                num_results=5,
                text=True
            )
            for i, result in enumerate(search_response.results):
                web_chunks.append({
                    "id": f"web_{i}",
                    "text": f"Source: {result.url}\nContent: {result.text[:2000]}"
                })
        except Exception as e:
            logger.error("exa_search_failed", error=str(e))

    all_chunks = local_chunks + web_chunks
    all_combined = "\n\n".join(
        f"[{c['id']}] {c['text']}" for c in all_chunks
    )

    try:
        rag_response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[RAG_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": AGENT_PROMPTS["rag"]},
                {"role": "user",
                 "content": f"Query: {query}\n\nRetrieved chunks:\n{all_combined}"},
            ],
            max_tokens=4000,
        )

        if not rag_response.choices[0].message.tool_calls:
             raise ValueError(f"Model {settings.MODEL_NAME} failed to return tool calls for RAG.")

        args = json.loads(
            rag_response.choices[0].message.tool_calls[0].function.arguments
        )
    except Exception as e:
        logger.error("rag_llm_failed", agent_id=agent_id, error=str(e))
        return {
            "routing_log": [{
                "next": "critique_node",
                "reason": f"RAG LLM failed: {e}. Check if model '{settings.MODEL_NAME}' is pulled in Ollama.",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }

    content = rag_response.choices[0].message.content or ""
    try:
        await budget_manager.consume(agent_id, content)
    except Exception:
        return {
            "routing_log": [{
                "next": "compression_node",
                "reason": "RAG exceeded token budget",
                "agent": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }

    latency_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    agent_output = AgentOutput(
        agent_id=agent_id,
        output=args.get("answer", ""),
        token_count=len(content),
        citations=args.get("citations", []),
        timestamp=datetime.now(timezone.utc),
    )

    async def _write_event():
        from db.queries import write_agent_event
        from db import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await write_agent_event(
                session=session,
                job_id=uuid.UUID(job_id),
                agent_id=agent_id,
                event_type="agent_done",
                input_hash=hashlib.sha256(query.encode()).hexdigest(),
                output_hash=hashlib.sha256(agent_output.output.encode()).hexdigest(),
                latency_ms=latency_ms,
                token_count=len(content),
                payload={"answer": agent_output.output, "citations": agent_output.citations},
            )

    asyncio.create_task(_write_event())

    return {
        "agent_outputs": {agent_id: agent_output},
        "routing_log": [{
            "next": "critique_node",
            "reason": "RAG answer produced with 2-hop retrieval",
            "agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }





