import asyncio
import tiktoken


class BudgetExceededException(Exception):
    def __init__(self, agent_id: str, overage: int):
        self.agent_id = agent_id
        self.overage = overage
        super().__init__(f"Agent {agent_id} exceeded budget by {overage} tokens")


class ContextBudgetManager:
    """
    Thread-safe token budget tracker.
    declare_budget() must be called before consume() for any agent.
    consume() raises BudgetExceededException — never silently truncates.
    Caller must catch the exception and return a routing patch to
    compression_node. Swallowing it silently is a policy violation.
    """

    def __init__(self):
        self._enc = tiktoken.get_encoding("cl100k_base")
        self._budgets: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def declare_budget(self, agent_id: str, max_tokens: int) -> None:
        async with self._lock:
            self._budgets[agent_id] = {"max": max_tokens, "used": 0}

    async def check_remaining(self, agent_id: str) -> int:
        async with self._lock:
            b = self._budgets[agent_id]
            return b["max"] - b["used"]

    async def consume(self, agent_id: str, text: str) -> int:
        tokens = len(self._enc.encode(text))
        async with self._lock:
            b = self._budgets[agent_id]
            new_used = b["used"] + tokens
            if new_used > b["max"]:
                raise BudgetExceededException(agent_id, new_used - b["max"])
            b["used"] = new_used
        return tokens

    async def is_over_budget(self, agent_id: str) -> bool:
        async with self._lock:
            b = self._budgets[agent_id]
            return b["used"] >= b["max"]

    async def get_all_budgets(self) -> dict[str, dict]:
        async with self._lock:
            return {
                aid: {
                    "max": b["max"],
                    "used": b["used"],
                    "remaining": b["max"] - b["used"],
                }
                for aid, b in self._budgets.items()
            }