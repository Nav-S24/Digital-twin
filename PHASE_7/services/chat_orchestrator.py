"""
Phase 7 - ChatOrchestrator

Coordinates the full chat flow:
  1. Detect intent
  2. Extract OBD code(s)
  3. Build minimal grounded context
  4. Add recent conversation history (last 5-10 turns)
  5. Call LLMService
  6. Return answer + intent + actual data sources used + obd codes found

Session memory is kept in-process, per session_id, capped at 10 turns.
For production/multi-worker deployments swap this dict for Redis or a DB.
"""

from collections import deque, defaultdict
from typing import Optional

from services.intent_detector import IntentDetector, Intent
from services.context_builder import ContextBuilder
from services.llm_service import LLMService

MAX_HISTORY_TURNS = 10  # keep last 10 messages (5 user + 5 assistant, roughly)

# session_id -> deque of {"role": "user"|"assistant", "content": str}
_SESSION_MEMORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY_TURNS))

# Tracks which vehicle a session was last associated with, so a vehicle
# switch on the dashboard can't leak the previous vehicle's context.
_SESSION_VEHICLE: dict[str, str] = {}


class ChatOrchestrator:

    @staticmethod
    def process_chat(vehicle_id: Optional[str], session_id: str, message: str) -> dict:
        # If the dashboard's selected vehicle changed since the last turn
        # in this session, drop prior history so old vehicle context can't
        # leak into the new answer.
        previous_vehicle = _SESSION_VEHICLE.get(session_id)
        if previous_vehicle is not None and previous_vehicle != vehicle_id:
            _SESSION_MEMORY[session_id].clear()
        _SESSION_VEHICLE[session_id] = vehicle_id

        # 1. Detect intent
        intent = IntentDetector.detect(message)

        # 2. Extract OBD code(s)
        obd_codes = IntentDetector.extract_obd_codes(message)

        # 3. Build minimal grounded context
        context = ContextBuilder.build(intent, vehicle_id, obd_codes)

        # 4. Recent conversation history
        history = list(_SESSION_MEMORY[session_id])

        # 5. Call LLM
        answer = LLMService.generate(
            intent=intent.value,
            context=context,
            conversation_history=history,
            user_message=message,
        )

        # 6. Update session memory
        _SESSION_MEMORY[session_id].append({"role": "user", "content": message})
        _SESSION_MEMORY[session_id].append({"role": "assistant", "content": answer})

        return {
            "vehicle_id": vehicle_id,
            "session_id": session_id,
            "intent": intent.value,
            "answer": answer,
            "data_sources": context["data_sources"],
            "obd_codes": obd_codes,
        }

    @staticmethod
    def clear_session(session_id: str) -> None:
        _SESSION_MEMORY.pop(session_id, None)
        _SESSION_VEHICLE.pop(session_id, None)
