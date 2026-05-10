import asyncio
import tiktoken


class BudgetExceededException(Exception):
    def __init__(self, agent_id: str, overage: int):
        self.agent_id = agent_id
        self.overage = overage
        super().__init__(f"Agent {agent_id} exceeded budget by {overage} tokens")


class ContextBudgetManager:
    def __init__(self):
        self._enc = tiktoken.get_encoding("cl100k_base")
        self._budgets: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def declare_budget(self, agent_id: str, max_tokens: int) -> None:
        async with self._lock:
            self._budgets[agent_id] = {"max": max_tokens, "used": 0}

    async def check_remaining(self, agent_id: str) -> int:
        async with self._lock:
            b = self._budgets.get(agent_id, {})
            return b.get("max", 0) - b.get("used", 0)

    async def consume(self, agent_id: str, text: str) -> int:
        tokens = len(self._enc.encode(text))
        async with self._lock:
            if agent_id not in self._budgets:
                raise ValueError(f"Budget not declared for agent: {agent_id}")
            b = self._budgets[agent_id]
            new_used = b["used"] + tokens
            if new_used > b["max"]:
                raise BudgetExceededException(agent_id, new_used - b["max"])
            b["used"] = new_used
        return tokens

    async def reset_budget(self, agent_id: str) -> None:
        async with self._lock:
            if agent_id in self._budgets:
                self._budgets[agent_id]["used"] = 0

    async def reset_all(self) -> None:
        async with self._lock:
            for b in self._budgets.values():
                b["used"] = 0

    async def is_over_budget(self, agent_id: str) -> bool:
        async with self._lock:
            b = self._budgets.get(agent_id, {})
            return b.get("used", 0) >= b.get("max", 1)

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