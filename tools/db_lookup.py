from core.config import settings
import json
from core.llm import get_client
from tools.base import BaseTool
from schemas.tool_result import ToolResult, ErrorCode

DB_SCHEMA_PROMPT = """
Tables:
  jobs(id, status, query, created_at, completed_at, final_answer)
  agent_events(id, job_id, agent_id, event_type, token_count, latency_ms, timestamp)
  tool_call_logs(id, job_id, agent_id, tool_name, latency_ms, accepted, retry_number)
  eval_runs(id, run_group_id, category, query, scores, timestamp)
  prompt_rewrites(id, agent_id, status, proposed_at, decided_at, performance_delta)

Convert the following natural language query into a valid PostgreSQL SELECT statement.
Return ONLY SELECT statements. Any non-SELECT must be rejected.
"""

SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_sql",
        "description": "Generate a SQL SELECT query from natural language",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The PostgreSQL SELECT query",
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of what the query does",
                },
            },
            "required": ["sql", "explanation"],
        },
    },
}


class DbLookupTool(BaseTool):
    name = "db_lookup"
    timeout_seconds = 15.0

    async def _execute(self, input: dict) -> ToolResult:
        nl_query = input.get("natural_language_query", "").strip()

        if not nl_query:
            return ToolResult(
                success=False,
                error_code=ErrorCode.MALFORMED,
                error_message="natural_language_query must be non-empty",
            )

        client = get_client()
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            tools=[SQL_TOOL],
            tool_choice="required",
            messages=[
                {"role": "system", "content": DB_SCHEMA_PROMPT},
                {"role": "user", "content": nl_query},
            ],
        )

        args = json.loads(
            response.choices[0].message.tool_calls[0].function.arguments
        )
        sql = args["sql"].strip()

        if not sql:
            return ToolResult(
                success=False,
                error_code=ErrorCode.MALFORMED,
                error_message="LLM produced empty SQL",
            )

        sql_upper = sql.upper().lstrip()
        if not sql_upper.startswith("SELECT"):
            if sql_upper.startswith("WITH"):
                pass
            else:
                return ToolResult(
                    success=False,
                    error_code=ErrorCode.MALFORMED,
                    error_message=f"Non-SELECT statement rejected: {sql[:100]}",
                )

        from db import AsyncSessionLocal
        from sqlalchemy import text as sa_text

        async with AsyncSessionLocal() as session:
            result = await session.execute(sa_text(sql))
            rows = result.fetchall()
            columns = list(result.keys())
            row_dicts = [dict(zip(columns, row)) for row in rows]

        return ToolResult(
            success=True,
            data={
                "sql": sql,
                "rows": row_dicts,
                "row_count": len(row_dicts),
            },
        )


