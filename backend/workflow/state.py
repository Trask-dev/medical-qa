"""
注意：此 State 仅用于后端各节点间传递数据（黑板模式）。
严禁直接将此对象序列化后作为 API 响应返回给前端！
对外接口请在 response_node 中按需提取字段，并按 SDD-03 契约重新组装。
"""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages


class MedicalQAState(TypedDict):
    """
    LangGraph 工作流核心状态契约。

    注意: 此状态模型需与 architecture-decisions.md 中的 SDD-01-State契约 保持同步。
    新增/修改字段前须确认对应 ADR 已审批，避免节点间数据契约断裂。
    """

    # --- 对话历史 (使用 LangGraph 内置 reducer 自动追加消息) ---
    messages: Annotated[List[dict], add_messages]

    # --- 流程控制 ---
    current_stage: str          # 当前对话阶段 (init/collecting/assessing/completed)
    intent: str                 # 用户意图分类结果
    route_decision: str         # 路由决策 (问诊/检索/紧急转人工等)
    round_count: int            # 当前问诊轮次
    max_rounds: int             # 最大允许问诊轮次

    # --- 信息收集与检索 ---
    collected_info: dict        # 已收集的结构化事实 (主诉、症状、时长等)
    search_queries: List[str]   # 生成的检索查询列表
    search_results: List[dict]  # 知识库/外部检索返回的结果

    # --- 诊断与安全 ---
    diagnosis_result: Optional[dict]  # 最终诊断/建议结果
    red_flag_raised: bool             # 是否触发危险信号标志
    safety_checks_passed: bool        # 安全检查是否通过

    # --- 会话标识 ---
    session_id: str             # 全局唯一会话ID，用于状态持久化与日志追踪
    current_scenario: str       # 当前问诊模板名称（general_consultation/pediatric_fever_care等）
    scenario_context: dict      # 场景配置上下文（模板名/采集项/限制等）, 由_detect_scenario设置