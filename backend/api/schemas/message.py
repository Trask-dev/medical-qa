from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class SendMessageRequest(BaseModel):
    content: str
    content_type: str = "text"


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    round_number: int
    role: str
    content: str
    content_type: str
    agent_source: Optional[str]
    token_count: Optional[int]
    created_at: datetime


class SendMessageResponse(BaseModel):
    message: MessageResponse
    session_status: str
    current_stage: str
    red_flag_raised: bool
    round_count: int
    collected_fields_summary: dict
    next_action: str


class SSEMessageEvent(BaseModel):
    type: str
    role: str
    content: str
    content_type: Optional[str]
    agent_source: Optional[str]
    round_number: Optional[int]


class SSEDiagnosisProgressEvent(BaseModel):
    type: str
    stage: str
    progress: int
    stage_description: Optional[str]


class SSEDiagnosisCompleteEvent(BaseModel):
    type: str
    result: dict


class SSEEmergencyEvent(BaseModel):
    type: str
    action: str
    guidance: str
    red_flags: List[str]
    disclaimer: Optional[str]


class SSEErrorEvent(BaseModel):
    type: str
    code: str
    message: str


class SSEHeartbeatEvent(BaseModel):
    type: str
    timestamp: datetime
