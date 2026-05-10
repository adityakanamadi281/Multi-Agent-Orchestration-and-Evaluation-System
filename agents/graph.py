from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from schemas.context import SharedContext
from agents.decomposition import decomposition_node
from agents.rag import rag_node
from agents.critique import critique_node
from agents.synthesis import synthesis_node
from agents.compression import compression_node
from agents.router import orchestrator_router

_EDGE_MAP = {
    "decomposition_node": "decomposition_node",
    "rag_node": "rag_node",
    "critique_node": "critique_node",
    "synthesis_node": "synthesis_node",
    "compression_node": "compression_node",
    END: END,
}


def build_agent_graph() -> CompiledStateGraph:
    g = StateGraph(SharedContext)
    g.add_node("decomposition_node", decomposition_node)
    g.add_node("rag_node", rag_node)
    g.add_node("critique_node", critique_node)
    g.add_node("synthesis_node", synthesis_node)
    g.add_node("compression_node", compression_node)
    g.set_entry_point("decomposition_node")
    for node in ["decomposition_node", "rag_node", "critique_node", "synthesis_node", "compression_node"]:
        g.add_conditional_edges(node, orchestrator_router, _EDGE_MAP)
    return g.compile()


compiled_graph = build_agent_graph()


