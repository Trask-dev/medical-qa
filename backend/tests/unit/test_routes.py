import pytest
from workflow.routes import route_by_intent, check_interview_complete, after_response


def test_route_by_intent_diagnosis_goes_to_interview():
    state = {"intent": "diagnosis", "red_flag_raised": False}
    assert route_by_intent(state) == "interview"


def test_route_by_intent_greeting_goes_to_response():
    state = {"intent": "greeting", "red_flag_raised": False}
    assert route_by_intent(state) == "response"


def test_route_by_intent_red_flag_always_to_response():
    state = {"intent": "diagnosis", "red_flag_raised": True}
    assert route_by_intent(state) == "response"


def test_route_by_intent_question_goes_to_response():
    state = {"intent": "question", "red_flag_raised": False}
    assert route_by_intent(state) == "response"


def test_check_interview_complete_diagnose_stage_goes_to_response():
    state = {"current_stage": "diagnose", "red_flag_raised": False}
    assert check_interview_complete(state) == "response"


def test_check_interview_complete_collect_with_assistant_reply_goes_to_response():
    state = {"current_stage": "collect", "red_flag_raised": False, "messages": [{"role": "assistant", "content": "q"}]}
    assert check_interview_complete(state) == "response"


def test_check_interview_complete_collect_no_reply_loops_to_interview():
    state = {"current_stage": "collect", "red_flag_raised": False, "messages": []}
    assert check_interview_complete(state) == "interview"


def test_check_interview_complete_red_flag_goes_to_response():
    state = {"current_stage": "collect", "red_flag_raised": True}
    assert check_interview_complete(state) == "response"


def test_after_response_done_by_default():
    assert after_response({}) == "done"


def test_after_response_fallback_goes_to_human_review():
    assert after_response({"fallback_triggered": True}) == "human_review"
