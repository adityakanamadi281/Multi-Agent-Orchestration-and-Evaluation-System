import json
import hashlib
import uuid
import asyncio
from datetime import datetime, timezone
from core.llm import get_client
from core.config import settings
from core.logging import logger
from context_manager import budget_manager
from schemas.context import SharedContext, AgentOutput
from agents.prompts import AGENT_PROMPTS

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


def _get_knowledge_chunks():
    return [
        {"id": "chunk_001",
         "text": "Paris is the capital and largest city of France. It has been a major European hub for art, fashion, gastronomy, and culture since the 17th century.",
         "metadata": {"source": "geography_facts", "topic": "cities"}},
        {"id": "chunk_002",
         "text": "HTTP stands for HyperText Transfer Protocol. It is the foundation of data communication on the World Wide Web, invented by Tim Berners-Lee in 1989.",
         "metadata": {"source": "tech_encyclopedia", "topic": "networking"}},
        {"id": "chunk_003",
         "text": "HyperText Transfer Protocol (HTTP) is an application-layer protocol for distributed, collaborative hypermedia information systems.",
         "metadata": {"source": "tech_rfc", "topic": "networking"}},
        {"id": "chunk_004",
         "text": "World War II ended in 1945. Germany surrendered on May 8 (V-E Day) and Japan surrendered on September 2 (V-J Day).",
         "metadata": {"source": "history_textbook", "topic": "ww2"}},
        {"id": "chunk_005",
         "text": "Climate change refers to long-term shifts in temperatures and weather patterns. Human activities, primarily burning fossil fuels, have been the main driver since the 1800s.",
         "metadata": {"source": "climate_science", "topic": "environment"}},
        {"id": "chunk_006",
         "text": "The Earth is approximately 4.54 billion years old, determined through radiometric dating of meteorite material and Earth's oldest rocks.",
         "metadata": {"source": "geology_consensus", "topic": "earth_science"}},
        {"id": "chunk_007",
         "text": "Albert Einstein won the Nobel Prize in Physics in 1921 for his discovery of the photoelectric effect, which was pivotal in establishing quantum theory.",
         "metadata": {"source": "nobel_archive", "topic": "physics_history"}},
        {"id": "chunk_008",
         "text": "Einstein's 1905 paper on the photoelectric effect proposed that light consists of quanta (photons). This work earned him the 1921 Nobel Prize, not his theory of relativity.",
         "metadata": {"source": "physics_journal", "topic": "photoelectric"}},
        {"id": "chunk_009",
         "text": "World War II (1939-1945) was a global war involving the vast majority of the world's countries, over 100 million people from more than 30 countries.",
         "metadata": {"source": "history_encyclopedia", "topic": "ww2"}},
        {"id": "chunk_010",
         "text": "Fossil records show life has existed on Earth for at least 3.5 billion years, providing evidence for evolution over geological time scales.",
         "metadata": {"source": "biology_textbook", "topic": "evolution"}},
        {"id": "chunk_011",
         "text": "Radiometric dating of the oldest rocks on Earth gives ages of approximately 4.0 billion years. Zircon crystals from Australia dated to 4.4 billion years.",
         "metadata": {"source": "geology_research", "topic": "earth_age"}},
        {"id": "chunk_012",
         "text": "Large Language Models are trained using next-token prediction. The model predicts the next word given previous context, and gradients flow through the network to minimize prediction loss.",
         "metadata": {"source": "ml_paper", "topic": "llm_training"}},
        {"id": "chunk_013",
         "text": "Machine learning in healthcare includes medical imaging diagnosis, drug discovery, patient risk prediction, and personalized treatment using supervised learning.",
         "metadata": {"source": "healthcare_ml_review", "topic": "healthcare"}},
        {"id": "chunk_014",
         "text": "Retrieval-Augmented Generation (RAG) combines information retrieval with text generation for more accurate and factual responses.",
         "metadata": {"source": "ai_research", "topic": "rag"}},
        {"id": "chunk_015",
         "text": "Supervised learning trains models on labeled data. Common algorithms include linear regression, decision trees, random forests, and neural networks.",
         "metadata": {"source": "ml_textbook", "topic": "supervised_learning"}},
        {"id": "chunk_016",
         "text": "The theory of relativity consists of special relativity (1905) and general relativity (1915). General relativity describes gravity as a geometric property of spacetime.",
         "metadata": {"source": "physics_encyclopedia", "topic": "relativity"}},
        {"id": "chunk_017",
         "text": "A 2019 meta-analysis of 40 studies found that moderate coffee consumption (3-4 cups per day) is associated with a 15% reduction in cardiovascular disease risk.",
         "metadata": {"source": "coffee_study_2019", "topic": "coffee_health"}},
        {"id": "chunk_018",
         "text": "A 2020 cohort study of 8,000 participants concluded that daily coffee intake above 6 cups is associated with increased arterial stiffness and a 22% higher risk of cardiovascular events.",
         "metadata": {"source": "coffee_study_2020", "topic": "coffee_health"}},
        {"id": "chunk_019",
         "text": "15% of 200 equals 30. This can be computed as 200 * 0.15 = 30, or equivalently 200 * 15 / 100 = 30.",
         "metadata": {"source": "math_reference", "topic": "arithmetic"}},
        {"id": "chunk_020",
         "text": "Fossil fuels include coal, oil, and natural gas. Burning fossil fuels releases carbon dioxide, a greenhouse gas that contributes to climate change.",
         "metadata": {"source": "energy_research", "topic": "climate"}},
    ]


