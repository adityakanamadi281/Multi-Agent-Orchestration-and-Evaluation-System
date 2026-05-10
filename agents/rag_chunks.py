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
                            "chunk_id": {"type": "string"},
                            "chunk_text": {"type": "string"},
                            "hop_number": {"type": "integer"},
                        },
                        "required": ["claim", "chunk_id", "chunk_text", "hop_number"],
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
        {"id": "chunk_001", "text": "Paris is the capital and largest city of France.", "metadata": {"source": "geography_facts", "topic": "cities"}},
        {"id": "chunk_002", "text": "HTTP stands for HyperText Transfer Protocol.", "metadata": {"source": "tech_encyclopedia", "topic": "networking"}},
        {"id": "chunk_003", "text": "HyperText Transfer Protocol is an application-layer protocol for distributed, collaborative hypermedia.", "metadata": {"source": "tech_rfc", "topic": "networking"}},
        {"id": "chunk_004", "text": "World War II ended in 1945. Germany surrendered May 8, Japan September 2.", "metadata": {"source": "history_textbook", "topic": "ww2"}},
        {"id": "chunk_005", "text": "Climate change refers to long-term shifts in temperatures and weather patterns.", "metadata": {"source": "climate_science", "topic": "environment"}},
        {"id": "chunk_006", "text": "The Earth is approximately 4.54 billion years old.", "metadata": {"source": "geology_consensus", "topic": "earth_science"}},
        {"id": "chunk_007", "text": "Albert Einstein won the Nobel Prize in Physics in 1921 for his discovery of the photoelectric effect.", "metadata": {"source": "nobel_archive", "topic": "physics_history"}},
        {"id": "chunk_008", "text": "Einstein's 1905 paper on the photoelectric effect proposed that light consists of quanta.", "metadata": {"source": "physics_journal", "topic": "photoelectric"}},
        {"id": "chunk_009", "text": "World War II was a global war involving over 100 million people from more than 30 countries.", "metadata": {"source": "history_encyclopedia", "topic": "ww2"}},
        {"id": "chunk_010", "text": "Fossil records show life has existed on Earth for at least 3.5 billion years.", "metadata": {"source": "biology_textbook", "topic": "evolution"}},
        {"id": "chunk_011", "text": "Radiometric dating gives Earth rocks ages of approximately 4.0 billion years.", "metadata": {"source": "geology_research", "topic": "earth_age"}},
        {"id": "chunk_012", "text": "Large Language Models are trained using next-token prediction.", "metadata": {"source": "ml_paper", "topic": "llm_training"}},
        {"id": "chunk_013", "text": "Machine learning in healthcare includes medical imaging diagnosis and drug discovery.", "metadata": {"source": "healthcare_ml_review", "topic": "healthcare"}},
        {"id": "chunk_014", "text": "Retrieval-Augmented Generation combines retrieval with text generation.", "metadata": {"source": "ai_research", "topic": "rag"}},
        {"id": "chunk_015", "text": "Supervised learning trains models on labeled data.", "metadata": {"source": "ml_textbook", "topic": "supervised_learning"}},
        {"id": "chunk_016", "text": "The theory of relativity consists of special relativity and general relativity.", "metadata": {"source": "physics_encyclopedia", "topic": "relativity"}},
        {"id": "chunk_017", "text": "A 2019 meta-analysis found moderate coffee consumption reduces cardiovascular disease risk.", "metadata": {"source": "coffee_study_2019", "topic": "coffee_health"}},
        {"id": "chunk_018", "text": "A 2020 study found daily coffee intake above 6 cups increases cardiovascular events risk.", "metadata": {"source": "coffee_study_2020", "topic": "coffee_health"}},
        {"id": "chunk_019", "text": "15 percent of 200 equals 30.", "metadata": {"source": "math_reference", "topic": "arithmetic"}},
        {"id": "chunk_020", "text": "Fossil fuels include coal, oil, and natural gas.", "metadata": {"source": "energy_research", "topic": "climate"}},
    ]