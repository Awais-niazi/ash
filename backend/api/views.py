from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.utils.decorators import method_decorator
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
            from agent.tools import get_weather, get_news
            from agent.models import Memory, Task

            weather = get_weather("Lahore Pakistan")
            news = get_news("world news today")

            memories = Memory.objects.filter(
                user=request.user
            ).order_by('-confidence_score')[:5]
            memory_text = "\n".join([f"- {m.key}: {m.value}" for m in memories])

            # Get pending tasks
            tasks = Task.objects.filter(
                user=request.user,
                status='pending'
            ).order_by('deadline', '-priority')[:10]

            if tasks.exists():
                task_text = "PENDING TASKS:\n"
                for task in tasks:
                    deadline_str = f" (due {task.deadline.strftime('%b %d')})" if task.deadline else ""
                    overdue = " OVERDUE" if task.is_overdue() else ""
                    task_text += f"- [{task.priority.upper()}] {task.title}{deadline_str}{overdue}\n"
            else:
                task_text = "PENDING TASKS:\nNo pending tasks."

            briefing_prompt = f"""Generate a warm morning briefing for Awais. Use this real data:

WEATHER:
{weather.get('output', 'Weather unavailable')}

NEWS:
{news.get('output', 'News unavailable')}

WHAT YOU KNOW ABOUT AWAIS:
{memory_text}

{task_text}

Instructions:
- Warm personal greeting
- Summarize the weather in 1 sentence
- Give top 3 news headlines
- Mention pending tasks and any overdue ones
- End with a motivational thought
- Keep it concise and friendly
- Speak directly to Awais
- Do NOT call any tools, all data is already provided above"""

            agent = get_agent(request.user)
            reply = agent.chat(briefing_prompt)
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