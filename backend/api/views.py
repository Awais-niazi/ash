from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from agent.engine import AgentEngine
import traceback

agent_sessions = {}

def get_agent(user):
    if user.id not in agent_sessions:
        agent_sessions[user.id] = AgentEngine(user=user)
    return agent_sessions[user.id]


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_message = request.data.get("message")

        if not user_message:
            return Response(
                {"error": "No message provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            agent = get_agent(request.user)
            reply = agent.chat(user_message)
            return Response({
                "message": user_message,
                "reply": reply
            }, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        agent = get_agent(request.user)
        agent.reset()
        return Response({"status": "conversation reset"})


class MorningBriefingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            from agent.tools import get_weather, get_news
            from agent.models import Memory

            # Get real data directly
            weather = get_weather("Lahore Pakistan")
            news = get_news("world news today")

            # Get memories
            memories = Memory.objects.filter(
                user=request.user
            ).order_by('-confidence_score')[:5]
            memory_text = "\n".join([f"- {m.key}: {m.value}" for m in memories])

            # Build briefing prompt with real data already injected
            briefing_prompt = f"""Generate a warm morning briefing for Awais. Use this real data:

WEATHER:
{weather.get('output', 'Weather unavailable')}

NEWS:
{news.get('output', 'News unavailable')}

WHAT YOU KNOW ABOUT AWAIS:
{memory_text}

Instructions:
- Warm personal greeting
- Summarize the weather in 1 sentence
- Give top 3 news headlines
- Mention any tasks deadlines or reminders from memory
- End with a motivational thought
- Keep it concise and friendly
- Speak directly to Awais
- Do NOT call any tools, all data is already provided above"""

            agent = get_agent(request.user)
            reply = agent.chat(briefing_prompt)

            return Response({"briefing": reply}, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class SpeakView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            from gtts import gTTS
            from django.http import HttpResponse
            import io

            text = request.data.get("text", "")
            if not text:
                return Response({"error": "No text provided"}, status=400)

            text = text[:2000]

            tts = gTTS(text=text, lang='en', slow=False)
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)

            return HttpResponse(
                audio_buffer.read(),
                content_type="audio/mpeg"
            )

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                return Response(
                    {"error": "Ash is taking a short break. Try again in a few minutes."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            return Response(
                {"error": error_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )