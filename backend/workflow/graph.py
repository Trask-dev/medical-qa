"""
医疗问答 AI 工作流编排器（LangGraph）

核心流转：safety_check → interview(循环) → response → END/human_review
"""
from workflow.state import MedicalQAState
from workflow.nodes.safety_check_node import safety_check_node
from workflow.nodes.interview_node import interview_node
from workflow.nodes.response_node import response_node
from workflow.nodes.human_review_node import human_review_node
from workflow.routes import route_by_intent, check_interview_complete, after_response


def build_workflow():
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(MedicalQAState)

    # 注册节点
    workflow.add_node("safety_check", safety_check_node)   # 安全安检入口
    workflow.add_node("interview", interview_node)         # 多轮问诊收集信息
    workflow.add_node("response", response_node)           # 生成回复
    workflow.add_node("human_review", human_review_node)   # 人工兜底审核

    # 统一从安检进入
    workflow.set_entry_point("safety_check")

    # 安检后分流：医疗意图→问诊，否则→直接回复
    workflow.add_conditional_edges("safety_check", route_by_intent, {
        "interview": "interview",
        "response": "response",
    })

    # 问诊循环：信息不足→继续追问，完整/需输出→跳转回复
    workflow.add_conditional_edges("interview", check_interview_complete, {
        "interview": "interview",
        "response": "response",
    })

    # 回复后出口：正常结束或转人工审核
    workflow.add_conditional_edges("response", after_response, {
        "done": END,
        "human_review": "human_review",
    })

    # 人工审核完成后流程结束
    workflow.add_edge("human_review", END)

    return workflow.compile()