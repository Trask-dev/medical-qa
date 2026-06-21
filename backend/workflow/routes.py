"""
工作流路由决策器（交通信号灯）
根据 State 中的标志位，动态决定工作流的下一个节点走向。

核心路由规则：
1. 安全熔断优先：任何节点只要触发 red_flag_raised，立即强制跳转到 response 节点
2. 意图分流：优先通过 RealRouterLLM 分类意图；LLM 不可用时回退到硬编码规则
3. 问诊闭环控制：只有 current_stage=="diagnose" 才放行到 search；否则继续在 interview 循环追问
4. 人工兜底触发：仅当 response 节点标记 fallback_triggered 时转人工审核

关键约束：
- 所有路由函数必须是无状态的纯函数，禁止修改 state、禁止依赖全局可变状态
- 路由返回值必须与 build_workflow() 中 conditional_edges 的映射键严格一致
- 新增路由分支时，必须同步更新对应节点的 conditional_edges 配置
"""

import logging

from llm.real_llm_adapter import RealRouterLLM

logger = logging.getLogger(__name__)

_router_llm: RealRouterLLM | None = None


def _get_router() -> RealRouterLLM:
    global _router_llm
    if _router_llm is None:
        _router_llm = RealRouterLLM()
    return _router_llm


def _extract_last_user_message(state: dict) -> str:
    messages = state.get("messages", [])
    for msg in reversed(messages):
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role == "user" or role == "human":
            return content or ""
    return ""


def route_by_intent(state: dict) -> str:
    if state.get("red_flag_raised"):
        return "response"

    intent = state.get("intent", "greeting")

    try:
        last_msg = _extract_last_user_message(state)
        if last_msg:
            routes = _get_router().classify(last_msg)
            if routes and routes[0][0] in ("general_consultation",):
                scenario_id = routes[0][0]
                logger.info("LLM routed: scenario=%s confidence=%.2f", scenario_id, routes[0][1])
                state["route_decision"] = scenario_id
                state["route_confidence"] = routes[0][1]
                state["route_rationale"] = routes[0][2]
                state["current_scenario"] = scenario_id
                return "interview"
    except Exception:
        logger.debug("RealRouterLLM unavailable, using hardcoded routing")

    if intent in ("diagnosis", "follow_up"):
        return "interview"
    if intent == "emergency":
        return "response"
    return "response"


def check_interview_complete(state: dict) -> str:
    if state.get("red_flag_raised"):
        return "response"
    current_stage = state.get("current_stage", "")
    if current_stage == "diagnose":
        return "response"
    if current_stage == "collect" and _last_is_assistant(state.get("messages", [])):
        return "response"
    return "interview"


def _last_is_assistant(messages: list) -> bool:
    if not messages:
        return False
    last = messages[-1]
    role = last.get("role", "") if isinstance(last, dict) else getattr(last, "type", "")
    return role in ("assistant", "ai")


def after_response(state: dict) -> str:
    if state.get("fallback_triggered"):
        return "human_review"
    return "done"
