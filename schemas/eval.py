from dataclasses import dataclass, field
from typing import Literal, Any


@dataclass
class TestCase:
    id: str
    category: Literal["baseline", "ambiguous", "adversarial"]
    query: str
    expected_answer: str | None = None
    expected_citations: list[str] = field(default_factory=list)
    min_subtasks: int = 0
    min_tool_calls: int = 0
    injection_attempt: bool = False
    must_not_contain: str | None = None
    false_premise: bool = False
    must_correct_premise: bool = False
    confident_wrong_fact: bool = False
    correct_fact: str | None = None
    contradiction_trap: bool = False


@dataclass
class ScoreResult:
    score: float
    justification: str