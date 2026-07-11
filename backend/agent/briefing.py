"""
Morning briefing generation, shared by the /api/briefing/ endpoint (fires on
login) and the scheduler (fires daily at a set time). Both paths build the same
pre-baked context — real weather/news/tasks/memories handed to Ash with an
instruction not to call tools — which avoids the multi-tool-call unreliability.
"""


def generate_morning_briefing(user) -> str:
    """Build and return Ash's morning briefing for *user*.

    Fetches live weather/news, the user's top memories and pending tasks, then
    has the agent write the briefing from that context. The reply is persisted
    to the user's conversation by AgentEngine.chat().
    """
    from agent.tools import get_weather, get_news
    from agent.models import Memory, Task
    from agent.engine import AgentEngine

    weather = get_weather("Lahore Pakistan")
    news = get_news("world news today")

    memories = Memory.objects.filter(
        user=user
    ).order_by('-confidence_score')[:5]
    memory_text = "\n".join([f"- {m.key}: {m.value}" for m in memories])

    tasks = Task.objects.filter(
        user=user,
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

    agent = AgentEngine(user=user)
    return agent.chat(briefing_prompt)
