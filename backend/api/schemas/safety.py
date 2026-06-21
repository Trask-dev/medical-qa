from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SafetyEventResponse(BaseModel):
    id: str
    session_id: str
    event_category: str
    severity: str
    description: str
    context_data: dict = {}
    action_taken: str
    created_at: Optional[datetime] = None


class SafetyEventSummary(BaseModel):
    total_events: int = 0
    red_flag_count: int = 0
    pii_detection_count: int = 0


class SafetyEventListResponse(BaseModel):
    data: list[SafetyEventResponse] = []
    pagination: dict = {}
    summary: SafetyEventSummary = SafetyEventSummary()
