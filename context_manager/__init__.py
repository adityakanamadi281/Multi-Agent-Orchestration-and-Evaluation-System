import asyncio
from context_manager.budget import BudgetExceededException, ContextBudgetManager

_managers: dict[str, ContextBudgetManager] = {}
_registry_lock = asyncio.Lock()


async def get_manager(job_id: str) -> ContextBudgetManager:
    async with _registry_lock:
        if job_id not in _managers:
            _managers[job_id] = ContextBudgetManager()
        return _managers[job_id]


async def release_manager(job_id: str) -> None:
    async with _registry_lock:
        _managers.pop(job_id, None)