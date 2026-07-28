"""
Phase 7 - Chat Routes

FastAPI router exposing:
    POST /chat        - main chat endpoint
    POST /chat/clear  - clear a session's memory
"""

from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel

from services.chat_orchestrator import ChatOrchestrator

router = APIRouter()


class ChatRequest(BaseModel):
    vehicle_id: Optional[str] = None
    session_id: str
    message: str


class ChatResponse(BaseModel):
    vehicle_id: Optional[str] = None
    session_id: str
    intent: str
    answer: str
    data_sources: List[str]
    obd_codes: List[str]


class ClearSessionRequest(BaseModel):
    session_id: str


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = ChatOrchestrator.process_chat(
        vehicle_id=req.vehicle_id,
        session_id=req.session_id,
        message=req.message,
    )
    return result


@router.post("/chat/clear")
def clear_chat(req: ClearSessionRequest):
    ChatOrchestrator.clear_session(req.session_id)
    return {"status": "cleared", "session_id": req.session_id}
