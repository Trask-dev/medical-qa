# =============================================================================
# 问诊对话 API 路由层（FastAPI Router）
#
# 这个文件是前端与AI问诊引擎之间的"翻译官"和"调度台"。
# 负责接收HTTP请求、组装初始状态、调用工作流引擎、格式化响应结果。
#
# 包含三个核心接口：
# 1. POST /messages：发送消息并触发一轮完整的AI问诊推理
# 2. GET  /messages：分页查询历史消息记录
# 3. GET  /stream：SSE流式推送实时事件（当前为占位实现）
#
# ⚠️ 注意：_messages_store 是内存字典，仅用于开发调试
#    生产环境必须替换为 Redis / PostgreSQL 等持久化存储
# =============================================================================

import uuid
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas.message import SendMessageRequest, SendMessageResponse, MessageResponse
from workflow.graph import build_workflow

router = APIRouter()

# 内存级消息存储（开发用，重启即丢失）
_messages_store: dict[str, list[dict]] = {}
_session_state: dict[str, dict] = {}

def _get_graph():
    return build_workflow()


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, req: SendMessageRequest):
    """
    发送消息接口：用户每发一条消息，就驱动AI问诊引擎走一步。

    完整流程：
    1. 把用户消息存入历史记录
    2. 组装引擎所需的初始状态（state）
    3. 调用 LangGraph 工作流执行一轮推理
    4. 根据引擎输出判断下一步动作，封装成标准响应返回
    """
    graph = _get_graph()

    # ---- 第1步：持久化用户消息 ----
    session_messages = _messages_store.setdefault(session_id, [])
    user_msg = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "round_number": 0,           # TODO: 应从已有消息数自动递增
        "role": "user",
        "content": req.content,
        "content_type": req.content_type,
        "agent_source": None,
        "token_count": None,
        "created_at": datetime.utcnow(),
    }
    session_messages.append(user_msg)

    # ---- 第2步：累计状态（跨 API 调用持久化） ----
    prev = _session_state.get(session_id, {})
    
    # 从消息存储中获取完整的历史消息（转换为工作流引擎需要的格式）
    history_messages = []
    for msg in session_messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role and content:
            history_messages.append({"role": role, "content": content})
    
    state = {
        "messages": history_messages,
        "intent": "diagnosis",
        "red_flag_raised": prev.get("red_flag_raised", False),
        "safety_checks_passed": prev.get("safety_checks_passed", True),
        "collected_info": prev.get("collected_info", {}),
        "search_results": prev.get("search_results", []),
        "search_queries": prev.get("search_queries", []),
        "diagnosis_result": prev.get("diagnosis_result"),
        "round_count": prev.get("round_count", 0),
        "max_rounds": prev.get("max_rounds", 5),
        "session_id": session_id,
        "current_stage": prev.get("current_stage", "init"),
        "route_decision": prev.get("route_decision", ""),
        "current_scenario": prev.get("current_scenario", "general_consultation"),
        "scenario_context": prev.get("scenario_context", {}),
    }

    if not state.get("scenario_context"):
        sc = _detect_scenario(req.content)
        state["scenario_context"] = sc
        # 将场景配置中的参数应用到 state（仅首次）
        if sc.get("use_expert"):
            state["use_expert"] = True
        if sc.get("max_rounds"):
            state["max_rounds"] = sc["max_rounds"]

    # 确保 use_expert 从持久化的 scenario_context 中恢复到 state
    if state.get("scenario_context", {}).get("use_expert"):
        state["use_expert"] = True

    # ---- 第3步：执行AI工作流 ----
    result = await graph.ainvoke(state)

    _session_state[session_id] = {
        "collected_info": result.get("collected_info", {}),
        "round_count": result.get("round_count", 0),
        "max_rounds": result.get("max_rounds", prev.get("max_rounds", 5)),
        "current_stage": result.get("current_stage", "init"),
        "red_flag_raised": result.get("red_flag_raised", False),
        "safety_checks_passed": result.get("safety_checks_passed", True),
        "search_results": result.get("search_results", []),
        "search_queries": result.get("search_queries", []),
        "diagnosis_result": result.get("diagnosis_result"),
        "route_decision": result.get("route_decision", ""),
        "current_scenario": result.get("current_scenario", "general_consultation"),
        "scenario_context": result.get("scenario_context", prev.get("scenario_context", {})),
    }

    # ---- 第4步：根据引擎输出决定前端下一步动作 ----
    red_flag = result.get("red_flag_raised", False)
    stage = result.get("current_stage", "init")
    round_count = result.get("round_count", 0)
    collected = result.get("collected_info", {})

    next_action = "continue"              # 默认继续对话
    if red_flag:
        next_action = "emergency_interrupted"   # 触发紧急中断
    elif stage == "diagnose":
        next_action = "diagnosis_ready"         # 可以出诊断了
    elif stage == "done":
        next_action = "completed"               # 问诊流程结束

    assistant_reply = _extract_assistant_reply(result.get("messages", []))

    if assistant_reply:
        ai_msg = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "round_number": round_count,
            "role": "assistant",
            "content": assistant_reply,
            "content_type": "text",
            "agent_source": "system",
            "token_count": None,
            "created_at": datetime.utcnow(),
        }
        session_messages.append(ai_msg)

    options = result.get("options", []) if stage == "collect" else []

    return SendMessageResponse(
        message=MessageResponse(**user_msg),
        session_status="active",
        current_stage=stage,
        red_flag_raised=red_flag,
        round_count=round_count,
        collected_fields_summary=_summarize(collected),
        next_action=next_action,
        response_content=assistant_reply,
        options=options,
        scenario=result.get("current_scenario"),
    )


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str, limit: int = 20, offset: int = 0, round_number: int = None):
    """
    查询历史消息：支持分页 + 按轮次过滤。
    用于前端刷新页面后恢复对话上下文。
    """
    all_msgs = _messages_store.get(session_id, [])

    # 如果指定了轮次号，只返回该轮的消息
    if round_number is not None:
        all_msgs = [m for m in all_msgs if m.get("round_number") == round_number]

    total = len(all_msgs)
    data = all_msgs[offset:offset + limit]

    return {
        "data": data,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,  # 是否还有下一页
        },
    }


@router.get("/sessions/{session_id}/stream")
async def stream_events(session_id: str):
    """
    SSE流式推送接口：实时向前端推送问诊过程中的各类事件。

    ⚠️ 当前为占位实现！仅发送心跳和欢迎语。
    生产环境应接入工作流引擎的异步事件队列，
    实时推送 message / diagnosis_progress / emergency 等事件。
    """
    async def event_stream():
        # 先发一个心跳，确认连接建立成功
        yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
        # 再发一条欢迎消息作为示例
        yield f"data: {json.dumps({'type': 'message', 'role': 'assistant', 'content': '您好，请描述您的症状。'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",       # 禁止缓存，确保实时性
            "Connection": "keep-alive",        # 保持长连接
            "X-Accel-Buffering": "no",         # 关闭Nginx缓冲，防止SSE被攒批发送
        },
    )


def _detect_scenario(user_msg: str) -> dict:
    return {
        "scenario_id": "general_consultation",
        "prompt_template": "general_consultation",
        "display_name": "通用健康咨询",
        "max_rounds": 10,
        "use_expert": True,        # 启用专家模式：基础阶段结束后进入专家问诊
        "basic_max_rounds": 5,     # 基础问诊最多 5 轮，之后 LLM 判断结束或达上限→专家
    }


def _extract_assistant_reply(messages: list) -> str:
    for msg in reversed(messages):
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("assistant", "ai"):
            return content or ""
    return ""


def _summarize(collected: dict) -> dict:
    summary = {}
    patient_info = collected.get("patient_info", {})
    for key, value in patient_info.items():
        if value is not None:
            summary[key] = value
    for key in ("pain_character", "swelling", "redness", "heat", "accompanying_symptoms"):
        if key in collected and collected[key] is not None:
            summary[key] = collected[key]
    return summary