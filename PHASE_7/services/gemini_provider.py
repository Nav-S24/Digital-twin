import os
import json
from google import genai

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

SYSTEM_PROMPT = """
You are an AI Vehicle Digital Twin assistant.

STRICT RULES:
1. Use ONLY the provided JSON context for vehicle-specific information.
2. Never invent vehicle values.
3. Distinguish predictions from confirmed faults.
4. If data is missing, clearly state that.
5. Keep responses concise and actionable.
"""

class GeminiProvider:

    @staticmethod
    def is_configured():
        return bool(os.environ.get("GEMINI_API_KEY"))

    @staticmethod
    def generate(intent, context, conversation_history, user_message):

        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"]
        )

        context_json = json.dumps(context, indent=2, default=str)

        history = ""

        for turn in conversation_history:
            history += f"{turn['role']}: {turn['content']}\n"

        prompt = f"""
{SYSTEM_PROMPT}

Conversation History:
{history}

Grounded Context:
{context_json}

User Question:
{user_message}
"""

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        return response.text