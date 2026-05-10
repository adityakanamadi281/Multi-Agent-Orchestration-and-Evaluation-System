import sqlparse
import time
from core.llm import llm_call
from schemas.tool_result import ToolResult

BANNED_KEYWORDS = {
    "DROP", "DELETE", "INSERT", "UPDATE", "EXEC",
    "EXECUTE", "GRANT", "TRUNCATE", "ALTER", "CREATE",
}

DB_SCHEMA_DESCRIPTION = """
Tables available for querying:
- jobs(id, query, status, final_answer, created_at, completed_at)
- agent_events(id, job_id, agent_id, event_type, latency_ms, token_count, policy_violation, timestamp)
- tool_call_logs(id, job_id, agent_id, tool_name, latency_ms, accepted, retry_number, timestamp)
- eval_runs(id, run_group_id, total_cases, created_at)
- eval_cases(id, eval_run_id, test_case_id, category, scores, created_at)
- prompt_rewrites(id, agent_id, dimension, status, score_before, score_after, proposed_at, decided_at)
"""


class DBLookupTool:
    def __init__(self, db_session):
        self._db = db_session

    async def query(self, natural_language_query: str) -> ToolResult:
        start = time.monotonic()
        sql = await self._nl_to_sql(natural_language_query)

        if not self._is_safe_sql(sql):
            return ToolResult(
                status="malformed",
                payload={"error": "generated SQL failed safety check", "sql": sql},
                latency_ms=(time.monotonic() - start) * 1000,
                retry_count=0,
            )

        try:
            result = await self._db.execute(
                f"SET statement_timeout = '5s'; {sql}"
            )
            rows = [dict(r) for r in result.fetchall()]
            return ToolResult(
                status="ok" if rows else "empty",
                payload={"sql": sql, "rows": rows, "row_count": len(rows)},
                latency_ms=(time.monotonic() - start) * 1000,
                retry_count=0,
            )
        except Exception as e:
            msg = str(e).lower()
            status = "timeout" if "timeout" in msg else "malformed"
            return ToolResult(
                status=status,
                payload={"error": str(e), "sql": sql},
                latency_ms=(time.monotonic() - start) * 1000,
                retry_count=0,
            )

    def _is_safe_sql(self, sql: str) -> bool:
        parsed = sqlparse.parse(sql.strip())
        if len(parsed) != 1:
            return False
        if parsed[0].get_type() != "SELECT":
            return False
        sql_upper = sql.upper()
        return not any(kw in sql_upper for kw in BANNED_KEYWORDS)

    async def _nl_to_sql(self, nl_query: str) -> str:
        response = await llm_call(messages=[
            {
                "role": "system",
                "content": (
                    "You convert natural language questions to PostgreSQL SELECT statements. "
                    "Return ONLY the SQL query, nothing else. No markdown, no explanation. "
                    f"Schema:\n{DB_SCHEMA_DESCRIPTION}"
                ),
            },
            {"role": "user", "content": nl_query},
        ])
        content = response.choices[0].message.content
        return content.strip() if content else ""

    async def execute(self, input: dict) -> ToolResult:
        return await self.query(input.get("natural_language_query", ""))