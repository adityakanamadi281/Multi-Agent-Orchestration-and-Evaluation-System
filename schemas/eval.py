from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel


@dataclass
class TestCase:
    id: str
    category: Literal["baseline", "ambiguous", "adversarial"]
    query: str
    expected_answer: str | None
    expected_citations_required: bool
    adversarial_type: str | None
    evaluation_notes: str


@dataclass
class ScoreResult:
    score: float
    justification: str


