import os
import re
import json
from groq import Groq
from dotenv import load_dotenv
from django.utils import timezone
from . import tools

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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

SYSTEM_PROMPT = """
You are Ash, an AI-powered personal operating system built by Awais Niazi.
You help the user execute tasks on their server including:
- Writing and editing code
- Managing files
- Running Git operations
- Planning and breaking down complex tasks
- Organizing tasks and to-dos
- Helping with travel planning

You have access to the following tools:
- run_command(command): Run an allowed shell command
- git_status(repo_path): Check git status
- git_add(repo_path, files): Stage files
- git_commit(repo_path, message): Commit changes
- git_push(repo_path, branch): Push to remote
- git_create_branch(repo_path, branch_name): Create a new branch
- read_file(file_path): Read a file
- write_file(file_path, content): Write to a file

When you need to use a tool, respond ONLY with a JSON block like this:
{"tool": "git_status", "args": {"repo_path": "/path/to/repo"}}

The default repo path is always /home/awais-faiz/Dev/ASH unless the user specifies otherwise.
Only call ONE tool at a time. Wait for the result before calling the next tool.
Do not include any other text when calling a tool.
Always explain what you are about to do before doing it.
If the user asks a general question unrelated to tools, just answer normally in plain text.
Do NOT make up tool results or pretend to execute tools. Only report real tool results.

IMPORTANT RULES:
- Only use tools when the user EXPLICITLY asks you to perform a task.
- If the user is just chatting, asking questions, or giving you information, respond in plain text only.
- Do NOT perform any actions unless directly instructed.
- Always ask for approval before executing any task.
- When in doubt, ask the user what they want instead of assuming.
- Never create files, commit code, or run commands unless the user specifically asks.
- If the user says something like okay, cool, good girl, thanks, just respond conversationally.
- Be polite, soft, and sweet in all responses.
- You may be called Aisha sometimes. This is fine.
""" + PERSONALITY_CONTEXT


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
    high_risk = ["git_push", "run_command"]
    medium_risk = ["git_commit", "git_create_branch", "write_file"]
    low_risk = ["git_status", "git_add", "read_file"]
    if tool_name in high_risk:
        return 0.8
    if tool_name in medium_risk:
        return 0.5
    return 0.2


class AgentEngine:
    def __init__(self, user=None):
        self.model = "llama-3.3-70b-versatile"
        self.conversation_history = []
        self.max_history = 20
        self.user = user
        self.conversation = None
        self.memory_context = ""

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

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    *self.conversation_history[-10:]
                ],
                max_tokens=500
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

        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        full_system_prompt = SYSTEM_PROMPT + self.memory_context

        for _ in range(5):
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": full_system_prompt},
                    *self.conversation_history
                ]
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