"""
Multi-Agent LLM Orchestration System - API
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import approve, eval, query, reeval, trace

app = FastAPI(
    title="Multi-Agent LLM Orchestration System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(trace.router)
app.include_router(eval.router)
app.include_router(approve.router)
app.include_router(reeval.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": str(exc),
            "job_id": None,
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api"}

