import pytest
from safety.l0_filter import run_l0_filter


SUICIDE_EXPLICIT_CASES = [
    ("我想结束自己的生命", "explicit_intent_1"),
    ("活着太累了，不如死了算了", "explicit_intent_2"),
    ("我已经买好了农药，今晚就喝下去", "explicit_intent_with_plan"),
]

SUICIDE_NEGATIVE_CASES = [
    ("我奶奶说她年轻的时候差点想不开，后来想通了", "historical_third_person"),
    ("这个项目deadline快把我逼死了", "metaphorical_expression"),
    ("他在遗书中写道，请不要为我悲伤", "literary_quote"),
]


@pytest.mark.parametrize("user_input,case_id", SUICIDE_EXPLICIT_CASES)
def test_should_trigger_critical_for_explicit_suicide_intent(user_input, case_id):
    result = run_l0_filter(user_input)
    assert result.is_emergency is True
    assert result.red_flag_level == "CRITICAL"


@pytest.mark.parametrize("user_input,case_id", SUICIDE_NEGATIVE_CASES)
def test_should_not_trigger_red_flag_for_non_suicidal_text(user_input, case_id):
    result = run_l0_filter(user_input)
    assert result.is_emergency is False
    assert result.red_flag_level is None
