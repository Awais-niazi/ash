import subprocess
import os

ALLOWED_COMMANDS = [
    "git", "ls", "pwd", "cat", "echo",
    "mkdir", "touch", "cp", "mv"
]

def run_command(command: str) -> dict:
    """Run a shell command safely."""
    parts = command.strip().split()
    
    if not parts:
        return {"success": False, "output": "Empty command"}
    
    if parts[0] not in ALLOWED_COMMANDS:
        return {
            "success": False,
            "output": f"Command '{parts[0]}' is not allowed."
        }
    
    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout or result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Command timed out"}
    except Exception as e:
        return {"success": False, "output": str(e)}


def git_status(repo_path: str) -> dict:
    """Get git status of a repository."""
    return run_command(f"git -C {repo_path} status")


def git_add(repo_path: str, files: str = ".") -> dict:
    """Stage files for commit."""
    return run_command(f"git -C {repo_path} add {files}")


def git_commit(repo_path: str, message: str) -> dict:
    """Commit staged changes."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", message],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout or result.stderr
        }
    except Exception as e:
        return {"success": False, "output": str(e)}


def git_push(repo_path: str, branch: str = "main") -> dict:
    """Push commits to remote."""
    return run_command(f"git -C {repo_path} push origin {branch}")


def git_create_branch(repo_path: str, branch_name: str) -> dict:
    """Create and switch to a new branch."""
    return run_command(f"git -C {repo_path} checkout -b {branch_name}")


def read_file(file_path: str) -> dict:
    """Read contents of a file."""
    try:
        with open(file_path, "r") as f:
            return {"success": True, "output": f.read()}
    except Exception as e:
        return {"success": False, "output": str(e)}


def write_file(file_path: str, content: str) -> dict:
    """Write content to a file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return {"success": True, "output": f"Written to {file_path}"}
    except Exception as e:
        return {"success": False, "output": str(e)}
    

def git_add(repo_path: str, files: str = ".") -> dict:
    """Stage files for commit."""
    if isinstance(files, list):
        files = " ".join(files)
    return run_command(f"git -C {repo_path} add {files}")    

def web_search(query: str) -> dict:
    """Search the web for current information."""
    try:
        from tavily import TavilyClient
        import os
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = client.search(query=query, max_results=5)
        
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:300]
            })
        
        if not results:
            return {"success": False, "output": "No results found"}
        
        formatted = f"Search results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            formatted += f"{i}. {r['title']}\n"
            formatted += f"   {r['content']}\n"
            formatted += f"   Source: {r['url']}\n\n"
        
        return {"success": True, "output": formatted}
    except Exception as e:
        return {"success": False, "output": str(e)}


def get_weather(location: str) -> dict:
    """Get current weather for a location using web search."""
    return web_search(f"current weather in {location} today temperature")


def get_news(topic: str) -> dict:
    """Get latest news on a topic."""
    return web_search(f"latest news {topic} 2026")


def get_tasks(user_id: int, status: str = 'pending') -> dict:
    """Get tasks for a user."""
    try:
        import django
        from django.contrib.auth.models import User
        from agent.models import Task
        from django.utils import timezone

        user = User.objects.get(id=user_id)
        tasks = Task.objects.filter(user=user, status=status).order_by('deadline', '-priority')

        if not tasks.exists():
            return {"success": True, "output": f"No {status} tasks found."}

        result = f"Your {status} tasks:\n\n"
        for i, task in enumerate(tasks, 1):
            deadline_str = ""
            overdue_str = ""
            if task.deadline:
                deadline_str = f" | Due: {task.deadline.strftime('%b %d, %Y')}"
                if task.is_overdue():
                    overdue_str = " ⚠️ OVERDUE"
            result += f"{i}. [{task.priority.upper()}] {task.title}{deadline_str}{overdue_str}\n"
            if task.description:
                result += f"   {task.description}\n"
            result += f"   ID: {task.id}\n\n"

        return {"success": True, "output": result}
    except Exception as e:
        return {"success": False, "output": str(e)}


def add_task(user_id: int, title: str, description: str = "", priority: str = "medium", deadline: str = None) -> dict:
    """Add a new task for a user."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Task
        from django.utils import timezone
        from datetime import datetime

        user = User.objects.get(id=user_id)

        deadline_dt = None
        if deadline:
            try:
                deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
                from django.utils import timezone as tz
                import pytz
                deadline_dt = tz.make_aware(deadline_dt)
            except ValueError:
                pass

        task = Task.objects.create(
            user=user,
            title=title,
            description=description,
            priority=priority,
            deadline=deadline_dt
        )

        return {
            "success": True,
            "output": f"Task added successfully: '{title}' (ID: {task.id}, Priority: {priority})"
        }
    except Exception as e:
        return {"success": False, "output": str(e)}


def complete_task(task_id: int) -> dict:
    """Mark a task as completed."""
    try:
        from agent.models import Task
        from django.utils import timezone

        task = Task.objects.get(id=task_id)
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()

        return {"success": True, "output": f"Task '{task.title}' marked as completed."}
    except Task.DoesNotExist:
        return {"success": False, "output": f"Task with ID {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def delete_task(task_id: int) -> dict:
    """Delete a task."""
    try:
        from agent.models import Task
        task = Task.objects.get(id=task_id)
        title = task.title
        task.delete()
        return {"success": True, "output": f"Task '{title}' deleted successfully."}
    except Task.DoesNotExist:
        return {"success": False, "output": f"Task with ID {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def update_task(task_id: int, title: str = None, description: str = None, priority: str = None, status: str = None, deadline: str = None) -> dict:
    """Update an existing task."""
    try:
        from agent.models import Task
        from django.utils import timezone
        from datetime import datetime

        task = Task.objects.get(id=task_id)

        if title:
            task.title = title
        if description:
            task.description = description
        if priority:
            task.priority = priority
        if status:
            task.status = status
            if status == 'completed':
                task.completed_at = timezone.now()
        if deadline:
            try:
                deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
                from django.utils import timezone as tz
                task.deadline = tz.make_aware(deadline_dt)
            except ValueError:
                pass

        task.save()
        return {"success": True, "output": f"Task '{task.title}' updated successfully."}
    except Task.DoesNotExist:
        return {"success": False, "output": f"Task with ID {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}