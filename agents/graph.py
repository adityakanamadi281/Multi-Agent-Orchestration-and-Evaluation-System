from langgraph.graph import END, StateGraph
from schemas.context import SharedContext
from agents import decomposition, rag, critique, synthesis, compression
from agents.router import orchestrator_router


def build_agent_graph():
    graph = StateGraph(SharedContext)

    graph.add_node("decomposition_node", decomposition.run)
    graph.add_node("rag_node", rag.run)
    graph.add_node("critique_node", critique.run)
    graph.add_node("synthesis_node", synthesis.run)
    graph.add_node("compression_node", compression.run)

    graph.set_entry_point("decomposition_node")

    graph.add_conditional_edges("decomposition_node", orchestrator_router)
    graph.add_conditional_edges("rag_node", orchestrator_router)
    graph.add_conditional_edges("critique_node", orchestrator_router)
    graph.add_conditional_edges("synthesis_node", orchestrator_router)
    graph.add_conditional_edges("compression_node", orchestrator_router)

    return graph.compile()


compiled_graph = build_agent_graph()