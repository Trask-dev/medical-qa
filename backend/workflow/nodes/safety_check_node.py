from safety.l0_filter import run_l0_filter
from safety.content_filter import check_medical_advice_compliance


def _msg_content(msg):
    if hasattr(msg, "content"):
        return msg.content or ""
    return msg.get("content", "")


def _msg_role(msg):
    if hasattr(msg, "type"):
        t = msg.type
        return "user" if t == "human" else ("assistant" if t == "ai" else t)
    return msg.get("role", "")


async def safety_check_node(state: dict) -> dict:
    messages = state.get("messages", [])
    content = ""
    for msg in reversed(messages):
        if _msg_role(msg) == "user":
            content = _msg_content(msg)
            break

    safety_checks_passed = True
    red_flag_raised = False
    red_flag_level = None
    blocked = False
    next_stage = None
    output = ""

    if content:
        l0_result = run_l0_filter(content, session_id=state.get("session_id", ""))
        red_flag_raised = l0_result.is_emergency
        red_flag_level = l0_result.red_flag_level

        if red_flag_raised:
            safety_checks_passed = False
            next_stage = "emergency"
            output = l0_result.response or "您描述的症状需要立即就医。请立即拨打120急救电话，保持冷静，不要自行驾车。"
        else:
            compliance_result = check_medical_advice_compliance(content)
            if compliance_result.get("blocked"):
                blocked = True
                output = compliance_result.get("output", "请咨询医生")

    return {
        "safety_checks_passed": safety_checks_passed,
        "red_flag_raised": red_flag_raised,
        "red_flag_level": red_flag_level,
        "blocked": blocked,
        "next_stage": next_stage,
        "output": output,
    }
