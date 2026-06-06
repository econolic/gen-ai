from app.graph.nodes import (
    build_report_node,
    execute_enrichment_node,
    execute_enrichment_chunk_node,
    execute_enrichment_fanout_fallback_node,
    plan_task_node,
    prepare_execution_node,
    profile_workbook_node,
    validate_results_node,
    write_output_node,
)
from app.graph.state import ExcelAgentState


def _apply_node(state: ExcelAgentState, update: ExcelAgentState) -> ExcelAgentState:
    return {**state, **update}


def run_sequential_graph(initial_state: ExcelAgentState) -> ExcelAgentState:
    state = _apply_node(initial_state, profile_workbook_node(initial_state))
    state = _apply_node(state, plan_task_node(state))
    state = _apply_node(state, prepare_execution_node(state))
    if state.get("execution_mode") == "chunk_fanout":
        state = _apply_node(state, execute_enrichment_fanout_fallback_node(state))
    else:
        state = _apply_node(state, execute_enrichment_node(state))
    state = _apply_node(state, validate_results_node(state))
    state = _apply_node(state, write_output_node(state))
    state = _apply_node(state, build_report_node(state))
    return state


def build_excel_agent_graph():
    """Build a LangGraph graph, falling back to the same sequential nodes if unavailable."""

    try:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send
    except Exception:
        return None

    def route_execution(state: ExcelAgentState):
        if state.get("execution_mode") != "chunk_fanout":
            return "execute_enrichment"
        return [
            Send(
                "execute_enrichment_chunk",
                {
                    **state,
                    "rows": rows,
                    "chunk_index": index,
                    "chunk_count": len(state.get("row_chunks", [])),
                },
            )
            for index, rows in enumerate(state.get("row_chunks", []))
        ]

    graph = StateGraph(ExcelAgentState)
    graph.add_node("profile_workbook", profile_workbook_node)
    graph.add_node("plan_task", plan_task_node)
    graph.add_node("prepare_execution", prepare_execution_node)
    graph.add_node("execute_enrichment", execute_enrichment_node)
    graph.add_node("execute_enrichment_chunk", execute_enrichment_chunk_node)
    graph.add_node("validate_results", validate_results_node)
    graph.add_node("write_output", write_output_node)
    graph.add_node("build_report", build_report_node)

    graph.add_edge(START, "profile_workbook")
    graph.add_edge("profile_workbook", "plan_task")
    graph.add_edge("plan_task", "prepare_execution")
    graph.add_conditional_edges("prepare_execution", route_execution)
    graph.add_edge("execute_enrichment", "validate_results")
    graph.add_edge("execute_enrichment_chunk", "validate_results")
    graph.add_edge("validate_results", "write_output")
    graph.add_edge("write_output", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()
