import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are Ash, an AI-powered personal operating system.
You help the user execute tasks on their server including:
- Writing and editing code
- Managing files
- Running Git operations
- Planning and breaking down complex tasks

Always respond clearly and concisely.
When asked to perform a task, explain what you will do before doing it.
"""

class AgentEngine:
    def __init__(self):
        self.model = "llama-3.3-70b-versatile"
        self.conversation_history = []

    def chat(self, user_message: str) -> str:
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Call Groq API
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history
            ]
        )

        # Extract reply
        reply = response.choices[0].message.content

        # Add reply to history
        self.conversation_history.append({
            "role": "assistant",
            "content": reply
        })

        return reply

    def reset(self):
        self.conversation_history = []