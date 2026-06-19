from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages


class MedicalQAState(TypedDict):
    messages: Annotated[List[dict], add_messages]
    current_stage: str
    intent: str
    route_decision: str
    collected_info: dict
    search_results: List[dict]
    search_queries: List[str]
    diagnosis_result: Optional[dict]
    red_flag_raised: bool
    safety_checks_passed: bool
    round_count: int
    max_rounds: int
    session_id: str
