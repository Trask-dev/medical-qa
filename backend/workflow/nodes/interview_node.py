"""
问诊节点 — 多轮结构化信息采集 + 后台异步搜索
架构文档 §5.1.3: 问诊与搜索并行，搜索不阻塞主对话线程
"""
import asyncio
import asyncio
import logging
from llm.real_llm_adapter import RealL2Adapter
from knowledge.retriever import retrieve_for_symptoms

logger = logging.getLogger(__name__)

_search_tasks: dict[str, asyncio.Task] = {}
_search_results_cache: dict[str, list[dict]] = {}
_session_options_cache: dict[str, list[dict]] = {}

# ============================================================================
# LLM 适配器单例缓存
# 避免每次问诊都重新初始化客户端，节省连接和资源开销
# 注意：这是只读单例，不因请求不同而变化，不违反纯函数约束
# ============================================================================
_l2_adapter: RealL2Adapter | None = None


def _get_l2_adapter() -> RealL2Adapter:
    """获取或创建 RealL2Adapter 单例实例"""
    global _l2_adapter
    if _l2_adapter is None:
        _l2_adapter = RealL2Adapter()
    return _l2_adapter


# ============================================================================
# 消息格式适配工具
# 兼容 dict 和 LangChain Message 两种消息对象格式，屏蔽属性差异
# ============================================================================
def _msg_role(msg) -> str:
    """
    统一提取消息角色
    - LangChain Message 对象：通过 .type 属性判断（human→user, ai→assistant）
    - 普通 dict：直接读取 "role" 键
    """
    if hasattr(msg, "type"):
        t = msg.type
        return "user" if t == "human" else ("assistant" if t == "ai" else t)
    return msg.get("role", "")


def _msg_content(msg) -> str:
    """
    统一提取消息内容
    - LangChain Message 对象：通过 .content 属性读取
    - 普通 dict：直接读取 "content" 键
    """
    if hasattr(msg, "content"):
        return msg.content or ""
    return msg.get("content", "")


# ============================================================================
# 核心问诊节点（异步函数，供 LangGraph StateGraph 调用）
# 
# 参数：state - 全局共享状态字典
# 返回：partial update 字典，LangGraph 会自动 merge 到全局 state 中
#       未返回的字段保持不变，不会丢失历史数据
# ============================================================================
async def interview_node(state: dict) -> dict:
    # ----- 1. 从全局状态中读取当前上下文 -----
    collected_info = state.get("collected_info", {})  # 已收集的结构化病历信息
    round_count = state.get("round_count", 0)  # 当前问诊轮次（0=尚未开始）
    max_rounds = state.get("max_rounds", 5)  # 最大允许追问轮数（安全阀，防无限循环）
    messages = state.get("messages", [])  # 完整对话历史
    red_flag_raised = state.get("red_flag_raised", False)  # 安全熔断标志

    # 🔴 安全熔断优先
    # 上一轮安检或问诊中发现危险信号，立即终止问诊
    # 设置 current_stage="emergency"，路由 check_interview_complete 会强制跳转到 response 节点
    if red_flag_raised:
        return {
            "collected_info": collected_info,
            "round_count": round_count,
            "current_stage": "emergency",
            "search_results": state.get("search_results", []),
        }

    # 🛑 防自说自话检查
    # 如果对话历史最后一条已经是 AI 消息，说明上一轮已生成追问但还未展示给用户
    # 此时不应再生成新问题，直接返回 collect 阶段，让路由把已有 AI 消息输出
    if _last_message_is_assistant(messages):
        return {
            "collected_info": collected_info,
            "round_count": round_count,
            "current_stage": "collect",
        }

    # 从消息列表倒序查找最后一条用户消息作为本轮输入
    last_user = ""
    for msg in reversed(messages):
        if _msg_role(msg) == "user":
            last_user = _msg_content(msg)
            break

    # 解析数字选择（如"1"/"选2"/"第3个" → 上次选项值）
    prev_options = _session_options_cache.get(state.get("session_id", ""), [])
    last_user = _parse_numeric_answer(last_user, prev_options)

    # ===== 2. 第 0 轮：首次问诊（初始化阶段）=====
    if round_count == 0:
        # 清洗主诉文本（去掉"我""我的"等口语前缀），存入 patient_info
        collected_info.setdefault("patient_info", {})
        collected_info["patient_info"]["chief_complaint"] = _clean_chief_complaint(last_user)
        logger.info("Round 0: chief_complaint=%s", collected_info["patient_info"]["chief_complaint"])

        # 轮次计数从 0 推进到 1
        round_count = 1

        llm_result = _try_llm_question(state, collected_info, round_count, max_rounds)
        if not llm_result:
            raise RuntimeError("LLM failed to generate first question")
        question = llm_result["question"]
        options = llm_result.get("options", [])
        logger.info("Round 0: preview=%s options=%d", question[:80], len(options))

    # ===== 3. 后续轮次：持续追问收集信息 =====
    else:
        round_count += 1

        # 每轮都从用户最新回复中增量提取结构化事实
        logger.info(
            "Round %d: extracted facts, collected_info keys=%s",
            round_count,
            list(collected_info.keys()),
        )

        # LLM 决策：生成下一问 或 返回 None 表示信息充足/紧急
        llm_result = _try_llm_question(state, collected_info, round_count, max_rounds)

        if llm_result is None:
            return {
                "collected_info": collected_info,
                "round_count": round_count,
                "current_stage": "diagnose",
            }

        question = llm_result["question"]
        options = llm_result.get("options", [])

        # 绝对安全阀：防止死循环（LLM 应在此之前自行判定完成）
        if round_count >= max_rounds:
            logger.warning("max_rounds=%d reached, forcing diagnose", max_rounds)
            return {
                "collected_info": collected_info,
                "round_count": round_count,
                "current_stage": "diagnose",
            }

        logger.info("Round %d: preview=%s options=%d", round_count, question[:80], len(options))

    # ===== 4. 后台异步搜索（与问诊并行，不阻塞主流程）=====
    session_id = state.get("session_id", "")
    if session_id and collected_info.get("patient_info", {}).get("chief_complaint"):
        _fire_background_search(session_id, collected_info)
    search_results = _pull_search_results(session_id, state.get("search_results", []))

    # ===== 5. 返回 partial update =====
    scenario = (state.get("scenario_context") or {}).get("scenario_id", "general_consultation") if isinstance(state.get("scenario_context"), dict) else "general_consultation"
    return {
        "collected_info": collected_info,
        "round_count": round_count,
        "current_stage": "collect",
        "current_scenario": scenario,
        "messages": [{"role": "assistant", "content": question}],
        "search_results": search_results,
    }


# ============================================================================
# 辅助工具函数
# ============================================================================

def _fire_background_search(session_id: str, collected_info: dict) -> None:
    async def _search():
        try:
            results = await retrieve_for_symptoms(collected_info)
            existing = _search_results_cache.setdefault(session_id, [])
            seen_ids = {r.get("knowledge_entry_id", "") for r in existing if isinstance(r, dict)}
            for r in results:
                rid = r.knowledge_entry_id if hasattr(r, 'knowledge_entry_id') else r.get("knowledge_entry_id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    existing.append({"content": r.content, "source": r.source, "knowledge_entry_id": rid, "relevance_score": r.relevance_score} if hasattr(r, 'content') else r)
            logger.info("Background search: session=%s found=%d total=%d", session_id, len(results), len(existing))
        except Exception as e:
            logger.debug("Background search failed: %s", e)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_search())
        _search_tasks[session_id] = task
    except RuntimeError:
        pass


def _pull_search_results(session_id: str, existing: list) -> list:
    cached = _search_results_cache.get(session_id, [])
    if not cached:
        return existing
    existing_ids = {r.get("knowledge_entry_id", "") for r in existing if isinstance(r, dict)}
    merged = list(existing)
    for r in cached:
        rid = r.get("knowledge_entry_id", "")
        if rid and rid not in existing_ids:
            existing_ids.add(rid)
            merged.append(r)
    return merged


def _last_message_is_assistant(messages: list) -> bool:
    """
    判断对话历史最后一条消息是否来自 AI
    兼容 dict（role="assistant"）和 LangChain Message（type="ai"）两种格式
    用于防止 AI 连续自说自话
    """
    if not messages:
        return False
    last = messages[-1]
    role = last.get("role", "") if isinstance(last, dict) else getattr(last, "type", "")
    return role in ("assistant", "ai")


def _force_extract(state: dict) -> dict:
    messages = state.get("messages", [])
    user_msg = ""
    for msg in reversed(messages):
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role in ("user", "human"):
            user_msg = content or ""
            break
    if not user_msg:
        return {}

    result: dict = {}
    locations = ["肩膀", "膝盖", "头部", "前额", "后脑", "太阳穴", "腹部", "上腹", "下腹",
                 "胸部", "背部", "腰部", "脖子", "颈部", "手腕", "脚踝", "肘部", "大腿", "小腿"]
    for loc in locations:
        if loc in user_msg:
            result["symptom_location"] = loc
            break

    symptoms = ["疼痛", "疼", "痛", "发烧", "发热", "头晕", "恶心", "呕吐", "乏力", "咳嗽", "胸闷"]
    for sym in symptoms:
        if sym in user_msg:
            result["complaint"] = sym if sym != "疼" and sym != "痛" else "疼痛"
            break

    if not result and user_msg.strip():
        result["raw_response"] = user_msg.strip()

    return result


def _parse_numeric_answer(user_msg: str, prev_options: list[dict]) -> str:
    import re
    if not prev_options:
        return user_msg
    m = re.match(r'^\s*(\d+)\s*$', user_msg)
    if not m:
        m = re.search(r'[选第](\d+)', user_msg)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(prev_options):
            opt = prev_options[idx]
            val = opt.get("value", "") if isinstance(opt, dict) else ""
            if val and val != "other":
                return val
    return user_msg


def _clean_chief_complaint(raw: str) -> str:
    """
    清洗主诉文本
    去掉"我""我的""本人"等口语化前缀，使主诉更规范
    若清洗后为空则保留原文
    """
    import re
    cleaned = re.sub(r"^(我|我的|本人)", "", raw)
    return cleaned.strip() or raw


def _try_llm_question(
        state: dict, collected_info: dict, round_count: int, max_rounds: int
) -> dict | None:
    """
    LLM 引擎生成下一轮追问。
    返回 {"question": str, "options": list} 或 None（终止问诊）。
    LLM 调用失败时直接抛出异常。
    """
    adapter = _get_l2_adapter()
    ctx = state.get("scenario_context") or {}
    if isinstance(ctx, dict):
        ctx.setdefault("prompt_template", "general_consultation")
        ctx.setdefault("max_rounds", max_rounds)
        ctx.setdefault("required_facts", [])
        ctx.setdefault("optional_facts", [])
        ctx.setdefault("display_name", "通用健康咨询")
        ctx.setdefault("description", "")

    llm_result = adapter.generate_question(
        collected_facts=collected_info,
        scenario_context=ctx,
        round_count=round_count,
        max_rounds=max_rounds,
    )

    extracted = llm_result.get("extracted_facts", {})
    logger.info("LLM round=%d extracted_facts=%s response_text=%s",
                round_count, extracted, llm_result.get("response_text", "")[:60])
    if extracted:
        collected_info.update(extracted)

    forced = _force_extract(state)
    if forced:
        collected_info.update(forced)
        logger.info("forced extract: %s", forced)

    logger.info("collected_info after merge: %s", collected_info)

    next_action = llm_result.get("next_action", "continue")
    if next_action in ("assess", "emergency"):
        return None

    response_text = llm_result.get("response_text", "")
    if not response_text:
        raise RuntimeError("LLM returned empty response_text")
    options = llm_result.get("options", [])
    _session_options_cache[state.get("session_id", "")] = options
    return {"question": response_text, "options": options}


def _build_first_question(collected_info: dict) -> str:
    """
    【规则引擎 - 首轮】LLM 失败时的硬编码首问模板
    基于主诉拼接固定追问：持续时间 + 部位 + 疼痛程度
    """
    patient_info = collected_info.get("patient_info", {})
    chief = patient_info.get("chief_complaint", "您描述的症状")

    parts = [f"您的{chief}持续多久了？"]
    if not patient_info.get("complaint_location"):
        parts.append("具体在哪个位置？")
    if "severity" not in patient_info:
        parts.append("疼痛程度1-10分打几分？")

    return "".join(parts)



    if not patient_info.get("complaint_duration"):
        return "请告诉我这个症状持续多久了？具体在哪个位置？"
    if not patient_info.get("complaint_location"):
        return "具体是哪个部位不舒服？"
    if severity is None:
        return "疼痛或不适的程度1-10分您打几分？"
    if accompanying is None:
        return "有没有伴随其他症状？比如发烧、恶心、乏力等？"
    if not collected_info.get("past_history", {}).get("chronic_diseases"):
        return "您有慢性病史吗？比如高血压、糖尿病等？以前做过手术吗？"
    drug_allergies = collected_info.get("allergy_history", {}).get("drug_allergies")
    if not drug_allergies:
        return "您对什么药物过敏吗？比如青霉素等？"

    # 所有预设字段均已收集，使用开放式兜底问题
    return "您还有什么其他需要补充的信息吗？"