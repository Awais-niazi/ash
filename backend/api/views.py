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


class HistoryView(APIView):
    """Return the user's most recent conversation so the client can show past
    messages (including replies produced by scheduled tasks while the app was
    closed, and messages created on the other Ash instance)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from agent.models import Conversation, Message
        from django.utils import timezone

        conv = Conversation.objects.filter(user=request.user).first()
        if not conv:
            return Response({"messages": []})

        messages = Message.objects.filter(conversation=conv).order_by('created_at')[:200]
        data = [
            {
                "role": "ash" if m.role == "assistant" else "user",
                "text": m.content,
                "time": timezone.localtime(m.created_at).strftime("%H:%M"),
            }
            for m in messages
        ]
        return Response({"messages": data})


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

class VapidKeyView(APIView):
    """Expose the VAPID public key so the browser can subscribe."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings
        return Response({"publicKey": settings.VAPID_PUBLIC_KEY})


class PushSubscribeView(APIView):
    """Store (or refresh) a browser's Web Push subscription."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from agent.models import PushSubscription

        sub = request.data.get("subscription") or request.data
        endpoint = sub.get("endpoint")
        keys = sub.get("keys", {})
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")

        if not (endpoint and p256dh and auth):
            return Response({"error": "Invalid subscription"},
                            status=status.HTTP_400_BAD_REQUEST)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "user": request.user,
                "p256dh": p256dh,
                "auth": auth,
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
            },
        )
        return Response({"status": "subscribed"}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    """Remove a subscription (e.g. user turned notifications off)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from agent.models import PushSubscription
        endpoint = request.data.get("endpoint")
        if endpoint:
            PushSubscription.objects.filter(
                user=request.user, endpoint=endpoint).delete()
        return Response({"status": "unsubscribed"})


class PushTestView(APIView):
    """Send a test notification to confirm the pipeline works end-to-end."""
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='10/h', method='POST', block=True))
    def post(self, request):
        from agent.notifications import send_push
        count = send_push(
            request.user,
            "Ash 🤖",
            "Notifications are working — I'll ping you here.",
            url="/",
        )
        if count == 0:
            return Response(
                {"error": "No devices subscribed or VAPID not configured."},
                status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "sent", "devices": count})


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