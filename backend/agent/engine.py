import os
import json
from groq import Groq
from dotenv import load_dotenv
from . import tools

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are Ash, an AI-powered personal operating system.
You help the user execute tasks on their server including:
- Writing and editing code
- Managing files
- Running Git operations
- Planning and breaking down complex tasks

You have access to the following tools:
- run_command(command): Run an allowed shell command
- git_status(repo_path): Check git status
- git_add(repo_path, files): Stage files
- git_commit(repo_path, message): Commit changes
- git_push(repo_path, branch): Push to remote
- git_create_branch(repo_path, branch_name): Create a new branch
- read_file(file_path): Read a file
- write_file(file_path, content): Write to a file

When you need to use a tool, respond with a JSON block like this:
{"tool": "git_status", "args": {"repo_path": "/path/to/repo"}}

Otherwise respond normally in plain text.
Always explain what you are about to do before doing it.
"""

class AgentEngine:
    def __init__(self):
        self.model = "llama-3.3-70b-versatile"
        self.conversation_history = []

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
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *self.conversation_history
            ]
        )

        reply = response.choices[0].message.content

        # Check if reply contains a tool call
        try:
            tool_call = json.loads(reply)
            if "tool" in tool_call:
                tool_result = self.execute_tool(
                    tool_call["tool"],
                    tool_call.get("args", {})
                )
                # Feed result back to Ash
                self.conversation_history.append({
                    "role": "assistant",
                    "content": reply
                })
                self.conversation_history.append({
                    "role": "user",
                    "content": f"Tool result: {tool_result}"
                })
                # Get final response
                final = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        *self.conversation_history
                    ]
                )
                reply = final.choices[0].message.content
        except (json.JSONDecodeError, KeyError):
            pass

        self.conversation_history.append({
            "role": "assistant",
            "content": reply
        })

        return reply

    def reset(self):
        self.conversation_history = []