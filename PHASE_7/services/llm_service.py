from services.gemini_provider import GeminiProvider
from services.offline_formatter import OfflineFormatter

class LLMService:

    @staticmethod
    def generate(intent, context, conversation_history, user_message):

        if GeminiProvider.is_configured():

            try:
                print("🟢 Using Gemini")

                return GeminiProvider.generate(
                    intent,
                    context,
                    conversation_history,
                    user_message
                )

            except Exception as e:

                print("Gemini Error:", e)
                print("⚠ Falling back to Offline Formatter")

        return OfflineFormatter.format(intent, context)