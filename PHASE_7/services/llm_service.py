"""
Phase 7 - LLMService

Isolated LLM provider integration. Uses the Anthropic API via env-var
API key. If no API key is configured, falls back to a deterministic
"debug mode" that returns the built context as plain text instead of
calling the LLM - this lets you validate retrieval/context-building
end-to-end (Postman-testable) before wiring in real LLM calls.
"""

import os
import json
from typing import Optional

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("PHASE7_LLM_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """You are a vehicle assistant embedded in a Vehicle Digital Twin dashboard.

STRICT RULES - follow all of them:
1. Treat the JSON context provided to you as the ONLY source of truth for
   vehicle-specific or OBD-specific facts. Never invent, estimate, or
   recalculate sensor readings, health scores, failure probability, RUL,
   SHAP values, or OBD fault codes.
2. If a field needed to answer is missing or null in the context, say so
   plainly rather than guessing.
3. Clearly distinguish model PREDICTIONS (health scores, failure
   probability, RUL, risk percentages) from CONFIRMED mechanical
   diagnosis. Predictions are estimates, not certainties.
4. Never claim a vehicle is "definitely safe" or "definitely unsafe" to
   drive. Describe the risk/urgency level from the data and suggest
   appropriate caution, but leave the final call to the driver or a
   mechanic.
5. If the question is general automotive knowledge (not tied to the
   selected vehicle's specific data), answer from general knowledge but
   clearly label it as general information, separate from any
   vehicle-specific facts in the same reply.
6. Keep answers concise, plain-language, and actionable. Avoid jargon
   unless you explain it.
7. If vehicle_error is present in the context, explain to the user what
   data is missing/unavailable rather than fabricating an answer.
"""


class LLMService:

    @staticmethod
    def is_configured() -> bool:
        return bool(ANTHROPIC_API_KEY)

    @staticmethod
    def generate(
        intent: str,
        context: dict,
        conversation_history: list[dict],
        user_message: str,
    ) -> str:
        if not LLMService.is_configured():
            return LLMService._debug_answer(intent, context, user_message)

        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        context_block = json.dumps(context, default=str, indent=2)

        messages = []
        for turn in conversation_history:
            messages.append({"role": turn["role"], "content": turn["content"]})

        user_content = (
            f"GROUNDED CONTEXT (JSON - this is the only source of truth for facts):\n"
            f"{context_block}\n\n"
            f"USER QUESTION:\n{user_message}"
        )
        messages.append({"role": "user", "content": user_content})

        response = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(text_parts).strip()

    @staticmethod
    def _debug_answer(intent: str, context: dict, user_message: str) -> str:
        """
        No API key configured - deterministic, LLM-free response so the
        retrieval/context pipeline can be validated (Step 6: context-debug
        flow without an LLM).
        """
        lines = [
            "[DEBUG MODE - no ANTHROPIC_API_KEY set, showing raw grounded context instead of an LLM answer]",
            f"Intent: {intent}",
            f"User message: {user_message}",
            "",
            "Context that would be sent to the LLM:",
            json.dumps(context, default=str, indent=2),
        ]
        return "\n".join(lines)
