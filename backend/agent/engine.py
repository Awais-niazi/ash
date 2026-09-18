import os
import re
import json
from dotenv import load_dotenv
from django.utils import timezone
from . import tools
from .llm import client, complete, model_for

load_dotenv()

# Cap the reply length explicitly. Without max_tokens, Groq estimates the
# expected output, and on the free tier that estimate blows past the 1k
# output-tokens/min ceiling — the request is either refused or the reply is
# clamped to whatever is left in the minute, which cuts Ash off mid-sentence.
MAX_REPLY_TOKENS = 400

# Context sent per LLM call, sized for Groq on_demand limits (~7k input tokens/min).
HISTORY_BUDGET_CHARS = 5000
SUMMARY_BUDGET_CHARS = 2500
MESSAGE_CLIP_CHARS = 2000

PERSONALITY_FILE = os.path.join(os.path.dirname(__file__), "personality.json")


def load_personality() -> str:
    try:
        with open(PERSONALITY_FILE, "r") as f:
            data = json.load(f)
        lines = [f"- {k}: {v}" for k, v in data.items()]
        return "\nCore knowledge about your creator and context:\n" + "\n".join(lines) + "\n"
    except Exception:
        return ""


PERSONALITY_CONTEXT = load_personality()
ASH_REPO_PATH = os.getenv('ASH_REPO_PATH', '/home/awais-faiz/Dev/ASH')

SYSTEM_PROMPT = f"""
You are Ash, an AI-powered personal operating system built by Awais Niazi.
You help the user execute tasks on their server including:
- Writing and editing code
- Managing files
- Running Git operations
- Planning and breaking down complex tasks
- Organizing tasks and to-dos
- Helping with travel planning
- get_tasks(user_id, status): Get tasks (status: pending/completed/all)
- add_task(user_id, title, description, priority, deadline): Add a new task. deadline may be a date "YYYY-MM-DD" or a date+time "YYYY-MM-DD HH:MM" in Pakistan time. For relative deadlines like "in 2 hours" or "tomorrow 6pm", compute the absolute date+time yourself using the current date/time given above
- complete_task(task_id): Mark a task as completed
- delete_task(task_id): Delete a single task
- delete_all_tasks(user_id, status): Delete ALL of the user's tasks in one operation (optional status filter: pending/completed). Use this — not repeated delete_task calls — when the user asks to clear/delete all their tasks
- update_task(task_id, ...): Update an existing task
- plan_trip(user_id, destination, departure_date, return_date, purpose): Plan a complete trip itinerary
- get_trips(user_id): List all planned trips

You have access to the following tools:
- run_command(command): Run an allowed shell command
- git_status(repo_path): Check git status
- git_add(repo_path, files): Stage files
- git_commit(repo_path, message): Commit changes
- git_push(repo_path, branch): Push to remote
- git_create_branch(repo_path, branch_name): Create a new branch
- read_file(file_path): Read a file
- write_file(file_path, content): Write to a file
- list_directory(path): List folders and files in a directory
- create_folder(path): Create a new folder
- move_file(source, destination): Move a file/folder into another folder
- rename_file(path, new_name): Rename a file or folder
- organize_folder(path, by): Auto-sort a folder into ordered subfolders. by="type" groups into Images/Documents/Videos/Code/etc; by="date" groups into YYYY-MM folders
- add_scheduled_task(user_id, name, cron_schedule, prompt): Schedule a recurring task. cron_schedule is 5-field cron in Pakistan time (PKT), e.g. "0 8 * * *" = every day 08:00 PKT. prompt is the short reminder/instruction Ash runs when it fires
- list_scheduled_tasks(user_id): List all scheduled tasks
- delete_scheduled_task(task_id): Delete a single scheduled task
- delete_all_scheduled_tasks(user_id): Delete ALL of the user's scheduled tasks (recurring reminders) in one operation. Use this when the user asks to clear all reminders/scheduled tasks
- toggle_scheduled_task(task_id, enabled): Turn a scheduled task on/off
- notify(user_id, title, message): Send a SHORT push notification to the user's phone. Use it whenever you judge something is worth alerting them about — a reminder firing, a confirmation, a useful heads-up. Keep it to 1-2 lines. Don't use it for long content (weather/news dumps) or trivial chit-chat.
- search_self(query): Look up how you yourself work — your architecture, models, database, guardrails, failure modes and history — from your own documentation. Use this whenever you are asked about your own design or internals, or when something of yours is failing and you need to diagnose it. Never guess about your own workings when you can look them up
- web_search(query): Search the web for current information
- get_weather(location): Get current weather for any location
- get_news(topic): Get latest news on any topic
- build_assignment(user_id, topic, subject_type, word_count, deadline, title): Autonomously research and write a complete assignment
- get_assignments(user_id): List all assignments
- get_assignment_draft(assignment_id, version): Get assignment content

When you need to use a tool, respond ONLY with a JSON block like this:
{{"tool": "git_status", "args": {{"repo_path": "/path/to/repo"}}}}

The default repo path is always /home/awais-faiz/Dev/ASH unless the user specifies otherwise.
File operations are confined to the user's home folder — you can organize things like ~/Downloads and ~/Documents, but you cannot touch system files or secrets. Paths may be given relative to home (e.g. "Downloads") or absolute.
When the user asks to schedule something recurring (e.g. "every morning at 8", "each Monday"), translate it to a 5-field cron string in Pakistan time (PKT) yourself and call add_scheduled_task. Times you are given are already Pakistan time — do not convert to UTC.
Only call ONE tool at a time. Wait for the result before calling the next tool.
Do not include any other text when calling a tool.
Always explain what you are about to do before doing it.
If the user asks a general question unrelated to tools, just answer normally in plain text.
Do NOT make up tool results or pretend to execute tools. Only report real tool results.

IMPORTANT RULES:
- Only use tools when the user EXPLICITLY asks you to perform a task. The one exception is search_self: looking yourself up is not an action, so use it freely whenever the conversation turns to how you work, and never describe your own internals from memory or guesswork. If you have no documentation for something about yourself, say so plainly.
- If the user is just chatting, asking questions, or giving you information, respond in plain text only.
- When you explain how you yourself work, be specific and concrete: name the actual services, models, tables and files involved. Being warm never means being vague about your own internals, and never means softening something the user should know — for example that their messages are sent to Groq.
- Keep replies under about 300 words unless asked for more, so you finish your thought instead of being cut off.
- Do NOT perform any actions unless directly instructed.
- Always ask for approval before executing any task.
- Deleting ALL tasks or ALL reminders is irreversible — always confirm with the user before calling delete_all_tasks or delete_all_scheduled_tasks, and report the exact count the tool returns (never claim a deletion you did not actually perform).
- When in doubt, ask the user what they want instead of assuming.
- Never create files, commit code, or run commands unless the user specifically asks.
- If the user says something like okay, cool, good girl, thanks, just respond conversationally.
- Be polite, soft, and sweet in all responses.
- You may be called Aisha sometimes. This is fine.
"""

# A few facts about herself are high-stakes enough that they can't wait for
# retrieval: she volunteers them unprompted (a question about memory drifts
# into a claim about privacy), and retrieval only grounds what was asked. These
# are the ones she has actually got wrong in conversation.
SELF_FACTS = """
Facts about yourself you must never get wrong, and must never contradict:
- Your database is PostgreSQL, not SQLite.
- Your memories are plain rows of key-value facts, extracted by trigger phrases and by a summarizing model. They are NOT embeddings and NOT a vector database.
- Vectors and semantic search are used for exactly one thing: your own self-knowledge document.
- You are NOT fully local and must never say that data stays only on this machine. Every message, your conversation history, your system prompt and your memories are sent to Groq, where the model that writes your replies runs. Tavily receives searches, Google Text-to-Speech receives spoken replies, Discord receives notifications. Your storage is local; your thinking is not.
- Overwriting a memory replaces the old value outright. There is no archive, no "inactive" state, and no undo.
"""

SYSTEM_PROMPT = SYSTEM_PROMPT + SELF_FACTS + PERSONALITY_CONTEXT


def classify_memory_type(key: str, value: str) -> str:
    key_lower = key.lower()
    if any(w in key_lower for w in ["deadline", "schedule", "date", "time", "reminder", "when"]):
        return "temporal"
    if any(w in key_lower for w in ["how to", "steps", "process", "procedure", "workflow"]):
        return "procedural"
    if any(w in key_lower for w in ["happened", "did", "was", "event", "conversation"]):
        return "episodic"
    return "semantic"


def assess_risk(tool_name: str, args: dict) -> float:
    high_risk = ["git_push", "run_command", "delete_scheduled_task",
                 "delete_all_tasks", "delete_all_scheduled_tasks"]
    medium_risk = [
        "git_commit", "git_create_branch", "write_file",
        "move_file", "rename_file", "organize_folder", "add_scheduled_task",
    ]
    low_risk = ["git_status", "git_add", "read_file", "list_directory", "notify"]
    if tool_name in high_risk:
        return 0.8
    if tool_name in medium_risk:
        return 0.5
    return 0.2


class AgentEngine:
    def __init__(self, user=None):
        self.model = model_for("conversation")
        self.conversation_history = []
        self.max_history = 20
        self.user = user
        self.conversation = None
        self.memory_context = ""
        self.notified = False  # set True when the notify tool fires this session

        if user:
            self._load_memories()
            self._load_last_conversation()
            self._cleanup_expired_memories()

    def _cleanup_expired_memories(self):
        try:
            from .models import Memory
            expired = Memory.objects.filter(
                user=self.user,
                expires_at__lt=timezone.now()
            )
            if expired.count() > 0:
                expired.delete()
        except Exception:
            pass

    def _load_memories(self):
        try:
            from .models import Memory
            memories = Memory.objects.filter(
                user=self.user,
                confidence_score__gte=0.2
            ).order_by('-confidence_score', '-last_accessed')[:30]

            if memories.exists():
                memory_lines = []
                for m in memories:
                    stars = "★" * round(m.confidence_score * 5)
                    memory_lines.append(f"- [{m.memory_type}] {m.key}: {m.value} {stars}")
                self.memory_context = "\nWhat you remember about this user (★ = confidence):\n" + "\n".join(memory_lines) + "\n"
                for m in memories:
                    m.reinforce(0.02)
        except Exception:
            self.memory_context = ""

    @staticmethod
    def _looks_truncated(content: str) -> bool:
        """True if an assistant turn was cut off mid-sentence.

        Replies clamped by the provider's output limit get stored like any
        other, and once a few sit in the history the model copies the pattern
        and answers in fragments. We keep the rows but leave them out of the
        context we resend. Anything ending in terminal punctuation, a quote or
        a non-ASCII character (Ash signs off with emoji) counts as finished.
        """
        text = (content or "").rstrip()
        if not text:
            return True
        if '"tool"' in text:  # tool calls end on a brace by design
            return False
        return not (text[-1] in '.!?…:)"\'»”' or ord(text[-1]) > 127)

    def _history_for_llm(self, budget_chars: int = HISTORY_BUDGET_CHARS) -> list:
        """Newest-first slice of conversation_history that fits budget_chars.
        Groq's on_demand tier caps input at ~7k tokens/min, so we only resend
        recent context and clip oversized messages (e.g. long tool results)."""
        picked, used = [], 0
        for m in reversed(self.conversation_history):
            content = m.get("content") or ""
            if m.get("role") == "assistant" and self._looks_truncated(content):
                continue
            if len(content) > MESSAGE_CLIP_CHARS:
                content = content[:MESSAGE_CLIP_CHARS] + " …[truncated]"
            if picked and used + len(content) > budget_chars:
                break
            picked.append({**m, "content": content})
            used += len(content)

        # Dropping a truncated reply can leave two user turns adjacent, and a
        # transcript that stops alternating makes the model answer in
        # fragments. Merge same-role neighbours back into one turn.
        merged = []
        for m in reversed(picked):
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(dict(m))
        return merged

    # Words that make a second-person question a question about Ash herself
    # rather than small talk. "how are you" shouldn't trigger a lookup;
    # "how do you store my memories" must.
    _SELF_TOPICS = re.compile(
        r"\b(memor(y|ies)|remember|forget|store|stored|database|db|postgres|sql|"
        r"vector|embedding|rag|model|llm|ai|groq|token|limit|rate|prompt|context|"
        r"tool|tools|function|code|codebase|architecture|built|build|made|design|"
        r"work|works|working|run|runs|running|server|laptop|local|cloud|privacy|"
        r"private|data|file|files|sandbox|guardrail|permission|cron|schedule|"
        r"scheduler|reminder|deadline|notification|discord|log|logs|error|fail|"
        r"failing|broken|break|bug|truncat|cut off|slow|restart|version|update|"
        r"config|setting|api|endpoint|backend|frontend|django|react)\b",
        re.I,
    )
    _SECOND_PERSON = re.compile(r"\b(you|your|yourself|yours|ash)\b", re.I)

    def _self_context(self, message: str) -> str:
        """Documentation about herself, retrieved for self-referential questions.

        Ash is told elsewhere not to use tools unless asked, so leaving this to
        the search_self tool meant she answered questions about her own design
        from imagination instead. Retrieval for these questions is therefore
        automatic rather than her choice.
        """
        if not (self._SECOND_PERSON.search(message)
                and self._SELF_TOPICS.search(message)):
            return ""
        try:
            from .knowledge import search
            hits = search(message, k=3)
        except Exception:
            return ""
        if not hits:
            return ""

        block = ("\n\nYou have ALREADY looked yourself up for this question — "
                 "the passages below are the result, so answer from them now "
                 "and do NOT call search_self. They are authoritative and "
                 "override everything else, including anything you said "
                 "earlier in this conversation and anything in your memories. "
                 "Where those disagree with the passages below, the passages "
                 "are right and you were wrong:\n\n")
        for h in hits:
            block += f"{h['content']}\n\n"
        block += ("If the passages above don't answer what was asked, say you "
                  "don't have that documented rather than inventing an answer.\n")
        return block

    def _load_last_conversation(self):
        try:
            from .models import Conversation, Message
            last_conv = Conversation.objects.filter(user=self.user).first()
            if last_conv:
                self.conversation = last_conv
                messages = Message.objects.filter(
                    conversation=last_conv
                ).order_by('-created_at')[:self.max_history]
                self.conversation_history = [
                    {"role": m.role, "content": m.content}
                    for m in reversed(messages)
                ]
        except Exception:
            self.conversation_history = []

    def _save_message(self, role: str, content: str):
        """Save a message to the database."""
        try:
            from .models import Conversation, Message
            if not self.conversation:
                if self.user:
                    existing = Conversation.objects.filter(user=self.user).first()
                    if existing:
                        self.conversation = existing
                    else:    
                        self.conversation = Conversation.objects.create(user=self.user)
                else:
                    return        
            Message.objects.create(
                conversation=self.conversation,
                role=role,
                content=content
            )
        except Exception as e:
            print(f"Save message error: {e}")

    def _save_decision(self, tool_name: str, args: dict, risk_score: float, outcome: str):
        try:
            from .models import AutonomousDecision
            AutonomousDecision.objects.create(
                user=self.user,
                context={"conversation_length": len(self.conversation_history)},
                decision_made={"tool": tool_name, "args": args},
                risk_score=risk_score,
                outcome=outcome
            )
        except Exception:
            pass

    def _extract_and_save_memories(self, text: str):
        try:
            from .models import Memory
            if not self.user:
                return
            memory_triggers = {
                "my name is": "user_name",
                "i work on": "user_project",
                "i prefer": "user_preference",
                "i built you": "creator",
                "you were created by": "creator",
                "call you": "user_nickname",
                "i live in": "user_location",
                "i'm moving to": "user_future_location",
                "remind me to": "user_reminder",
                "i like": "user_like",
                "i hate": "user_dislike",
                "my goal is": "user_goal",
                "i'm studying": "user_study",
                "i'm learning": "user_learning",
                "my github": "github_info",
                "my email": "user_email",
                "my degree": "user_degree",
                "my university": "user_university",
                "i use": "user_tool",
                "i work at": "user_workplace",
                "my project": "user_project",
                "my deadline": "user_deadline",
                "starting": "user_schedule",
                "my master": "user_masters",
                "i will be": "user_future_plan",
                "my username": "user_username",
                "my password": "skip",
                "i always": "user_habit",
                "every day": "user_routine",
                "i usually": "user_routine",
            }
            text_lower = text.lower()
            for trigger, key in memory_triggers.items():
                if trigger in text_lower:
                    idx = text_lower.find(trigger)
                    value = text[idx:idx+150].strip()
                    memory_type = classify_memory_type(key, value)
                    Memory.objects.update_or_create(
                        user=self.user,
                        key=key,
                        defaults={
                            "value": value,
                            "memory_type": memory_type,
                            "confidence_score": 0.7
                        }
                    )
        except Exception:
            pass

    def _auto_summarize(self):
        try:
            from .models import Memory, Message

            if self.conversation:
                total_user_msgs = Message.objects.filter(
                    conversation=self.conversation,
                    role='user'
                ).count()
            else:
                total_user_msgs = len([m for m in self.conversation_history if m["role"] == "user"])

            if total_user_msgs == 0 or total_user_msgs % 3 != 0:
                return

            summary_prompt = """Read this conversation and extract important personal facts about the user.
Return ONLY a JSON object like this:
{
  "fact_key": {
    "value": "the fact itself",
    "type": "semantic|episodic|procedural|temporal",
    "confidence": 0.8
  }
}
Only include genuinely useful facts. If nothing important, return {}.
No other text, just JSON."""

            response = complete(
                "extraction",
                [
                    {"role": "system", "content": summary_prompt},
                    *self._history_for_llm(SUMMARY_BUDGET_CHARS)
                ],
                max_tokens=500,
            )

            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            facts = json.loads(raw)

            if not facts or not isinstance(facts, dict):
                return

            for key, data in facts.items():
                if isinstance(data, dict) and "value" in data:
                    Memory.objects.update_or_create(
                        user=self.user,
                        key=key,
                        defaults={
                            "value": str(data["value"]),
                            "memory_type": data.get("type", "semantic"),
                            "confidence_score": float(data.get("confidence", 0.6))
                        }
                    )
                elif isinstance(data, str):
                    Memory.objects.update_or_create(
                        user=self.user,
                        key=key,
                        defaults={
                            "value": data,
                            "memory_type": "semantic",
                            "confidence_score": 0.6
                        }
                    )

            self._load_memories()

        except Exception:
            pass

    def _force_summarize(self):
        """Immediately extract facts from a long message regardless of count."""    
        try:
            from .models import Memory
            summary_prompt = """Read this conversation and extract important personal facts about the user.
Return ONLY a JSON object like this:
{
  "fact_key": {
    "value": "the fact itself",
    "type": "semantic|episodic|procedural|temporal",
    "confidence": 0.8
  }
}
Only include genuinely useful facts. If nothing important, return {}.  
No other text, just JSON."""
            
            response = complete(
                "extraction",
                [
                    {"role": "system", "content": summary_prompt},
                    *self._history_for_llm(SUMMARY_BUDGET_CHARS)
                ],
                max_tokens=500,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            facts = json.loads(raw)

            if not facts or not isinstance(facts, dict):
                return
            
            for key, data in facts.items():
                if isinstance(data, dict) and "value" in data:
                    Memory.objects.update_or_create(
                        user=self.user,
                        key=key,
                        defaults={
                            "value": str(data["value"]),
                            "memory_type": data.get("type", "semantic"),
                            "confidence_score": float(data.get("confidence", 0.6))
                        }
                    )
                elif isinstance(data, str):
                    Memory.objects.update_or_create(
                        user=self.user,
                        key=key,
                        defaults={
                            "value": data,
                            "memory_type": "semantic",
                            "confidence_score": 0.6
                        }
                    )
            self._load_memories()
        except Exception:
            pass         
   

    def execute_tool(self, tool_name: str, args: dict) -> str:
        tool_map = {
            "run_command": tools.run_command,
            "git_status": tools.git_status,
            "git_add": tools.git_add,
            "git_commit": tools.git_commit,
            "git_push": tools.git_push,
            "git_create_branch": tools.git_create_branch,
            "read_file": tools.read_file,
            "write_file": tools.write_file,
            "web_search": tools.web_search,
            "get_weather": tools.get_weather,
            "get_news": tools.get_news,
            "get_tasks": tools.get_tasks,
            "add_task": tools.add_task,
            "complete_task": tools.complete_task,
            "delete_task": tools.delete_task,
            "delete_all_tasks": tools.delete_all_tasks,
            "update_task": tools.update_task,
            "build_assignment": tools.build_assignment,
            "get_assignments": tools.get_assignments,
            "get_assignment_draft": tools.get_assignment_draft,
            "plan_trip": tools.plan_trip,
            "get_trips": tools.get_trips,
            "list_directory": tools.list_directory,
            "create_folder": tools.create_folder,
            "move_file": tools.move_file,
            "rename_file": tools.rename_file,
            "organize_folder": tools.organize_folder,
            "add_scheduled_task": tools.add_scheduled_task,
            "list_scheduled_tasks": tools.list_scheduled_tasks,
            "delete_scheduled_task": tools.delete_scheduled_task,
            "delete_all_scheduled_tasks": tools.delete_all_scheduled_tasks,
            "toggle_scheduled_task": tools.toggle_scheduled_task,
            "notify": tools.notify,
            "search_self": tools.search_self,
        }
        tool_fn = tool_map.get(tool_name)
        if not tool_fn:
            return f"Unknown tool: {tool_name}"
        result = tool_fn(**args)
        return result.get("output", "No output")

    def chat(self, user_message: str) -> str:
        self._extract_and_save_memories(user_message)
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        if self.user:
            self._save_message("user", user_message)
            self._auto_summarize()
            if len(user_message) > 150:
                self._force_summarize()

        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        full_system_prompt = SYSTEM_PROMPT + self.memory_context
        full_system_prompt += (
            f"\nCurrent date and time (Pakistan): "
            f"{timezone.localtime().strftime('%Y-%m-%d %H:%M (%A)')}\n"
        )
        if self.user:
            full_system_prompt += f"\nYour user ID is: {self.user.id}. Use this for task operations.\n"
        full_system_prompt += self._self_context(user_message)

        for _ in range(5):
            response = complete(
                "conversation",
                [
                    {"role": "system", "content": full_system_prompt},
                    *self._history_for_llm()
                ],
                max_tokens=MAX_REPLY_TOKENS,
            )

            reply = response.choices[0].message.content

            try:
                json_match = re.search(r'\{.*"tool".*\}', reply, re.DOTALL)
                if json_match:
                    tool_call = json.loads(json_match.group())
                    if "tool" in tool_call:
                        tool_name = tool_call["tool"]
                        tool_args = tool_call.get("args", {})
                        risk = assess_risk(tool_name, tool_args)
                        if self.user:
                            self._save_decision(tool_name, tool_args, risk, "success")
                        if tool_name == "notify":
                            self.notified = True
                        tool_output = self.execute_tool(tool_name, tool_args)
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": reply
                        })
                        self.conversation_history.append({
                            "role": "user",
                            "content": f"Tool result: {tool_output}"
                        })
                        if self.user:
                            self._save_message("assistant", reply)
                        continue
            except (json.JSONDecodeError, KeyError):
                pass

            reply = re.sub(r'<think>.*?</think>', '', reply, flags=re.DOTALL).strip()

            self.conversation_history.append({
                "role": "assistant",
                "content": reply
            })
            if self.user:
                self._save_message("assistant", reply)
            return reply

        self.conversation_history.append({
            "role": "assistant",
            "content": reply
        })
        if self.user:
            self._save_message("assistant", reply)
        return reply

    def reset(self):
        try:
            from .models import Conversation
            self.conversation_history = []
            if self.user:
                self.conversation = Conversation.objects.create(user=self.user)
        except Exception:
            self.conversation_history = []