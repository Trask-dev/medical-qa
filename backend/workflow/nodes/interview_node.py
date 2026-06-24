"""问诊节点"""
import asyncio
import logging
import json

from llm.real_llm_adapter import RealL2Adapter
from knowledge.retriever import retrieve_for_symptoms

logger = logging.getLogger(__name__)
_adapter = RealL2Adapter()
_search_cache: dict[str, list[dict]] = {}

async def _async_search(session_id: str, collected_info: dict):
    try:
        results = await retrieve_for_symptoms(collected_info, top_k=5)
        existing = _search_cache.setdefault(session_id, [])
        seen = {r.get("knowledge_entry_id", "") for r in existing if isinstance(r, dict)}
        for r in results:
            rid = r.knowledge_entry_id if hasattr(r, "knowledge_entry_id") else r.get("knowledge_entry_id", "")
            if rid and rid not in seen:
                seen.add(rid)
                existing.append({"content": r.content, "source": r.source, "knowledge_entry_id": rid,
                                 "relevance_score": r.relevance_score} if hasattr(r, "content") else r)
        logger.info("Search done: session=%s found=%d total=%d", session_id, len(results), len(existing))
    except Exception as e:
        logger.debug("Search failed: %s", e)


def _pull_results(session_id: str, existing: list) -> list:
    cached = _search_cache.get(session_id, [])
    if not cached:
        return existing
    merged = list(existing)
    existing_ids = {r.get("knowledge_entry_id", "") for r in existing if isinstance(r, dict)}
    for r in cached:
        rid = r.get("knowledge_entry_id", "")
        if rid and rid not in existing_ids:
            existing_ids.add(rid)
            merged.append(r)
    return merged


def _msg_role(msg) -> str:  # 从消息对象中提取角色类型（user/assistant）
    if hasattr(msg, "type"):
        t = msg.type
        return "user" if t == "human" else ("assistant" if t == "ai" else t)
    return msg.get("role", "")


def _msg_content(msg) -> str:   #从消息对象中提取文本内容
    if hasattr(msg, "content"):
        return msg.content or ""
    return msg.get("content", "")


async def interview_node(state: dict) -> dict:
    collected_info = state.get("collected_info", {})  # 已收集的患者信息，默认为空字典
    round_count = state.get("round_count", 0)  # 当前问诊轮次，默认为0
    max_rounds = state.get("max_rounds", 5)  # 最大允许轮次，默认5轮
    messages = state.get("messages", [])  # 消息历史列表，默认为空列表

    # 🔴 安全熔断：如果触发了危险信号，立即进入紧急处理阶段
    if state.get("red_flag_raised"):
        return {"current_stage": "emergency"}
    # 🛑 防自说自话：如果最后一条消息是AI发出的，等待用户输入
    if messages and _msg_role(messages[-1]) in ("assistant", "ai"):
        return {"current_stage": "collect"}

    # 从消息历史中获取最后一条用户消息的内容，如果没有用户消息则返回空字符串
    last_user = next((_msg_content(m) for m in reversed(messages) if _msg_role(m) == "user"), "")


    # 初始化患者信息：如果这是第一轮问诊，将用户消息内容作为患者主诉
    if round_count == 0:
        collected_info.setdefault("patient_info", {})["chief_complaint"] = last_user.strip()
        round_count = 1

    # 将消息转换为标准字典格式（兼容 HumanMessage 对象和普通字典）
    formatted_messages = []
    for msg in messages:
        role = _msg_role(msg)
        content = _msg_content(msg)
        formatted_messages.append({"role": role, "content": content})

    # 打印 formatted_messages
    logger.info("Messages: %s", json.dumps(formatted_messages, ensure_ascii=False))

    try:
        llm_result = _adapter.generate_question(
            collected_facts=collected_info,  # 已收集的患者信息
            scenario_context=state.get("scenario_context", {}),  # 场景上下文
            messages=formatted_messages,  # 格式化后的聊天历史
            round_count=round_count,  # 当前问诊轮次
            max_rounds=max_rounds,  # 最大轮次限制
        )
    except Exception as e:  # 异常处理逻辑，用于捕获 LLM 调用过程中可能发生的错误并进行适当处理
        logger.error("LLM failed: %s", e)
        raise RuntimeError(f"LLM generation failed: {e}") from e

    if extracted := llm_result.get("extracted_facts"):  # 提取的结构化患者信息
        # 将提取的信息放入 patient_info 中
        patient_info = collected_info.setdefault("patient_info", {})
        # 如果 extracted 本身包含 patient_info 键，需要展平处理
        if isinstance(extracted, dict) and "patient_info" in extracted:
            extracted = extracted["patient_info"]
        patient_info.update(extracted)

    # 打印收集到的患者信息
    logger.info("Collected: %s", json.dumps(collected_info, ensure_ascii=False))

    next_action = llm_result.get("next_action", "continue")
    round_count += 1
    # 问诊流程的终止判断逻辑，决定什么时候停止追问并进入下一阶段
    if next_action in ("assess", "emergency") or round_count >= max_rounds:
        stage = "emergency" if next_action == "emergency" else "diagnose"
        return {"collected_info": collected_info, "round_count": round_count, "current_stage": stage,
                "search_results": _pull_results(state.get("session_id", ""), state.get("search_results", []))}

    session_id = state.get("session_id", "")
    if session_id and collected_info.get("patient_info", {}).get("chief_complaint"):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_search(session_id, collected_info))
        except RuntimeError:
            pass

    merged_results = _pull_results(session_id, state.get("search_results", []))

    return {
        "collected_info": collected_info,
        "round_count": round_count,
        "current_stage": "collect",
        "messages": [{"role": "assistant", "content": llm_result["response_text"]}],
        "options": llm_result.get("options", []),
        "search_results": merged_results,
    }