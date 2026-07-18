from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from agent.engine import AgentEngine
import traceback

def get_agent(user):
    """Build a fresh agent per request.

    Ash is single-user, but the engine still rehydrates its conversation and
    memories from the database on every call, so there is nothing to cache.
    Building per request keeps state correct across Gunicorn workers and avoids
    the unbounded in-memory session dict this used to hold.
    """
    return AgentEngine(user=user)


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='20/m', method='POST', block=True))
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

        except Ratelimited:
            return Response(
                {"error": "Too many messages. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
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


class ResetView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='10/h', method='POST', block=True))
    def post(self, request):
        try:
            agent = get_agent(request.user)
            agent.reset()
            return Response({"status": "conversation reset"})
        except Ratelimited:
            return Response(
                {"error": "Too many resets. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )


class MorningBriefingView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='2/h', method='GET', block=True))
    def get(self, request):
        try:
            from agent.briefing import generate_morning_briefing

            reply = generate_morning_briefing(request.user)
            return Response({"briefing": reply}, status=status.HTTP_200_OK)

        except Ratelimited:
            return Response(
                {"error": "Briefing already generated recently. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
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

class NotifyTestView(APIView):
    """Send a test notification to Discord to confirm the pipeline works."""
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='10/h', method='POST', block=True))
    def post(self, request):
        from agent.notifications import send_notification
        ok = send_notification(
            request.user,
            "Ash 🤖",
            "Notifications are working — I'll ping you here.",
        )
        if not ok:
            return Response(
                {"error": "DISCORD_WEBHOOK_URL not configured or Discord rejected it."},
                status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "sent"})


class SpeakView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='30/m', method='POST', block=True))
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

        except Ratelimited:
            return Response(
                {"error": "Too many speech requests. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )