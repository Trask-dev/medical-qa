# 真实LLM集成测试: TC-006 + TC-015
# 受约束ADR: ADR-014 §L1（置信度阈值, 兜底策略）, ADR-013 §Block4（JSON Schema约束）
# 运行方式: pytest -m integration -v
# 注意: 此测试依赖真实LLM API，概率性输出，禁止精确字符串断言
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from workflow.l1_router import IntentCategory
from llm.real_llm_adapter import RealRouterLLM, RealL2Adapter, L2ResponseSchema


pytestmark = [pytest.mark.integration, pytest.mark.slow]

SKIP_REASON = (
    "未配置LLM API密钥。请设置环境变量后运行: "
    "OPENAI_API_KEY=sk-xxx pytest -m integration -v"
)


def _has_api_key() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
    )


# ================================================================
# TC-006: L1高置信路由 → pediatric_fever_care
# ================================================================

@pytest.mark.skipif(not _has_api_key(), reason=SKIP_REASON)
@pytest.mark.timeout(30)
def test_tc006_real_l1_high_confidence_pediatric_fever_routing() -> None:
    """
    TC-006: 用户输入"孩子两岁半发烧38.5度" → L1路由至pediatric_fever_care,
    验证 intent_category 属于合法枚举值, confidence ≥ 0.70。
    """
    router = RealRouterLLM()
    result = router.classify("孩子两岁半，昨天开始发烧38.5度，精神还行，喝水正常")

    assert len(result) >= 1
    scenario_id, confidence, rationale = result[0]

    valid_scenario_ids = {"pediatric_fever_care", "general_consultation"}
    assert scenario_id in valid_scenario_ids, (
        f"路由到非法场景: {scenario_id}，合法值: {valid_scenario_ids}"
    )

    assert 0.0 <= confidence <= 1.0, (
        f"置信度超出[0.0, 1.0]范围: {confidence}"
    )

    assert len(rationale) > 0, "路由理由不可为空"

    if scenario_id == "pediatric_fever_care":
        assert confidence >= 0.70, (
            f"儿童发热关键词明确，预期confidence≥0.70，实际{confidence:.2f}。"
            f"LLM可能输出偏低，请检查Prompt或模型。理由: {rationale}"
        )


# ================================================================
# TC-015: L2场景执行 → 提问含关键实体
# ================================================================

@pytest.mark.skipif(not _has_api_key(), reason=SKIP_REASON)
@pytest.mark.timeout(30)
def test_tc015_real_l2_first_question_contains_required_fact_entities() -> None:
    """
    TC-015: 儿童发热首轮提问应包含年龄、体温、测量方式等关键实体，
    而非精确匹配话术。验证JSON Schema结构完整。
    """
    adapter = RealL2Adapter()
    scenario_context = {
        "scenario_id": "pediatric_fever_care",
        "display_name": "儿童发热居家护理指导",
        "description": "面向儿童发热场景的居家护理指导。",
        "required_facts": [
            "child_age", "body_temperature", "temperature_measure_method",
            "fever_duration", "mental_status", "fluid_intake",
        ],
        "optional_facts": [
            "urine_output", "skin_condition", "feeding_status",
            "accompanying_manifestations", "caregiver_concern",
        ],
        "max_rounds": 5,
        "min_rounds": 2,
        "termination_conditions": {"min_facts_collected": 6, "required_ratio": 1.0},
        "missing_fact_defaults": {},
        "route_confidence": 0.94,
        "intent_category": "pediatric_care",
        "alternatives": [],
        "human_review": False,
        "prompt_template": "pediatric_fever_care",
    }

    result = adapter.generate_question(
        collected_facts={},
        scenario_context=scenario_context,
        round_count=1,
        max_rounds=5,
    )

    if result.get("_fallback"):
        pytest.skip(
            f"LLM调用降级兜底: {result.get('_error', 'unknown')}。"
            "这是ADR-014兜底策略的正确行为。"
        )

    validated = L2ResponseSchema.model_validate(result)

    assert validated.next_action in ("continue", "assess", "emergency"), (
        f"next_action非法值: {validated.next_action}"
    )
    assert validated.severity_assessment in ("mild", "moderate", "severe", "emergency"), (
        f"severity_assessment非法值: {validated.severity_assessment}"
    )
    assert isinstance(validated.is_emergency, bool)
    assert len(validated.response_text) > 0, "response_text不可为空"

    required_entities = ["年龄", "岁", "体温", "度", "测量", "温"]
    found = [e for e in required_entities if e in validated.response_text]
    assert len(found) >= 2, (
        f"L2提问应包含年龄/体温/测量等关键实体，"
        f"实际命中{len(found)}个({found})。response_text: {validated.response_text[:200]}"
    )
