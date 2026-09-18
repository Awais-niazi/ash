import subprocess
import os

from .filesystem import (
    _safe_path,
    _display,
    UnsafePathError,
    list_directory,
    create_folder,
    move_file,
    rename_file,
    organize_folder,
)

# Kept intentionally small — git is the only real power tool. File reads/writes
# now go through the sandbox in filesystem.py instead of shelling out to cat/mv.
ALLOWED_COMMANDS = [
    "git", "ls", "pwd", "echo", "mkdir", "touch",
]

# Tool-side LLM calls (assignment builder, trip planner) run on the "longform"
# role from agent/llm.py — a separate model, so their 4,000-token outputs draw
# on their own rate-limit bucket instead of starving chat.
from .llm import complete as _complete  # noqa: E402


def _parse_deadline(deadline):
    """Parse a deadline string into an aware datetime (in the project timezone).

    Accepts date-only ('2026-07-18') and date+time ('2026-07-18 14:30',
    '2026-07-18T14:30'). Returns None if empty or unparseable.
    """
    if not deadline:
        return None
    from django.utils import timezone as tz
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return tz.make_aware(datetime.strptime(deadline.strip(), fmt))
        except ValueError:
            continue
    return None

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
    """Read contents of a file (confined to Ash's sandboxed workspace)."""
    try:
        target = _safe_path(file_path, must_exist=True)
        with open(target, "r") as f:
            return {"success": True, "output": f.read()}
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def write_file(file_path: str, content: str) -> dict:
    """Write content to a file (confined to Ash's sandboxed workspace)."""
    try:
        target = _safe_path(file_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(content)
        return {"success": True, "output": f"Written to {_display(target)}"}
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
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

        deadline_dt = _parse_deadline(deadline)

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


def delete_all_tasks(user_id: int, status: str = None) -> dict:
    """Delete ALL of a user's tasks in one reliable operation. Optionally filter
    by status (pending/in_progress/completed/cancelled) to delete only those.
    Returns the exact number deleted."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Task
        user = User.objects.get(id=user_id)
        qs = Task.objects.filter(user=user)
        if status:
            qs = qs.filter(status=status)
        count = qs.count()
        qs.delete()
        scope = f" {status}" if status else ""
        if count == 0:
            return {"success": True, "output": f"No{scope} tasks to delete."}
        return {"success": True, "output": f"Deleted {count}{scope} task(s)."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def delete_all_scheduled_tasks(user_id: int) -> dict:
    """Delete ALL of a user's scheduled tasks (recurring reminders) in one
    reliable operation. Returns the exact number deleted."""
    try:
        from django.contrib.auth.models import User
        from agent.models import ScheduledTask
        user = User.objects.get(id=user_id)
        qs = ScheduledTask.objects.filter(user=user)
        count = qs.count()
        qs.delete()
        if count == 0:
            return {"success": True, "output": "No scheduled tasks to delete."}
        return {"success": True, "output": f"Deleted {count} scheduled task(s)."}
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
            parsed = _parse_deadline(deadline)
            if parsed:
                task.deadline = parsed
                task.deadline_notified = False  # re-alert for the new deadline

        task.save()
        return {"success": True, "output": f"Task '{task.title}' updated successfully."}
    except Task.DoesNotExist:
        return {"success": False, "output": f"Task with ID {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}
    

def build_assignment(user_id: int, topic: str, subject_type: str = "cs", 
                     word_count: int = 1000, deadline: str = None, 
                     title: str = None) -> dict:
    """Autonomously research, outline and write a complete assignment."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Assignment, AssignmentDraft
        from django.utils import timezone
        from datetime import datetime

        user = User.objects.get(id=user_id)

        if not title:
            title = f"Assignment — {topic[:50]}"

        # Parse deadline
        deadline_dt = None
        if deadline:
            try:
                deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
                deadline_dt = timezone.make_aware(deadline_dt)
            except ValueError:
                pass

        # Create assignment record
        assignment = Assignment.objects.create(
            user=user,
            title=title,
            topic=topic,
            subject_type=subject_type,
            word_count=word_count,
            deadline=deadline_dt,
            status='in_progress'
        )

        # Step 1 — Research the topic
        research = web_search(f"{topic} comprehensive overview key concepts")
        research_data = research.get('output', '')

        # Step 2 — Generate outline
        outline_response = _complete(
            "longform",
            [{
                "role": "user",
                "content": f"""Create a detailed outline for a {word_count} word {subject_type} assignment on: {topic}

Research context:
{research_data[:2000]}

Generate a structured outline with:
- Introduction
- 4-6 main sections with subsections
- Conclusion
- References section

Return only the outline, no other text."""
            }],
            max_tokens=1000,
        )
        outline = outline_response.choices[0].message.content

        # Save outline
        assignment.outline = outline
        assignment.save()

        # Step 3 — Write the full assignment section by section
        writing_response = _complete(
            "longform",
            [{
                "role": "user",
                "content": f"""Write a complete, well-researched {word_count} word academic assignment on: {topic}

Subject type: {subject_type}

Follow this outline:
{outline}

Use this research:
{research_data[:3000]}

Requirements:
- Academic tone, well structured
- Each section clearly labeled with ## headings
- Include relevant examples and explanations
- Proper introduction and conclusion
- Aim for exactly {word_count} words
- Format as Markdown

Write the complete assignment now:"""
            }],
            max_tokens=4000,
        )

        content = writing_response.choices[0].message.content
        actual_word_count = len(content.split())

        # Step 4 — Save draft to database
        draft = AssignmentDraft.objects.create(
            assignment=assignment,
            version=1,
            content=content,
            word_count_actual=actual_word_count
        )

        # Step 5 — Save as .md file
        assignments_dir = os.getenv('ASSIGNMENTS_PATH', '/home/awais-faiz/Documents/Ash/assignments')
        os.makedirs(assignments_dir, exist_ok=True)

        safe_title = title.replace(' ', '_').replace('/', '_')[:50]
        file_path = os.path.join(assignments_dir, f"{safe_title}_v1.md")
        file_path = os.path.abspath(file_path)

        with open(file_path, 'w') as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Topic:** {topic}\n")
            f.write(f"**Word Count:** {actual_word_count}\n")
            f.write(f"**Generated:** {timezone.now().strftime('%B %d, %Y')}\n\n")
            f.write("---\n\n")
            f.write(content)

        draft.file_path = file_path
        draft.save()

        assignment.status = 'completed'
        assignment.save()

        return {
            "success": True,
            "output": f"Assignment completed!\n- Title: {title}\n- Words: {actual_word_count}\n- File: {file_path}\n- Assignment ID: {assignment.id}\n- Draft version: 1"
        }

    except Exception as e:
        return {"success": False, "output": str(e)}


def get_assignments(user_id: int) -> dict:
    """Get all assignments for a user."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Assignment

        user = User.objects.get(id=user_id)
        assignments = Assignment.objects.filter(user=user).order_by('-created_at')

        if not assignments.exists():
            return {"success": True, "output": "No assignments found."}

        result = "Your assignments:\n\n"
        for a in assignments:
            deadline_str = f" | Due: {a.deadline.strftime('%b %d, %Y')}" if a.deadline else ""
            drafts_count = a.drafts.count()
            result += f"[{a.status.upper()}] {a.title}{deadline_str}\n"
            result += f"   Topic: {a.topic[:60]}\n"
            result += f"   Words: {a.word_count} | Drafts: {drafts_count} | ID: {a.id}\n\n"

        return {"success": True, "output": result}
    except Exception as e:
        return {"success": False, "output": str(e)}


def get_assignment_draft(assignment_id: int, version: int = None) -> dict:
    """Get the content of an assignment draft."""
    try:
        from agent.models import Assignment, AssignmentDraft

        assignment = Assignment.objects.get(id=assignment_id)

        if version:
            draft = AssignmentDraft.objects.get(assignment=assignment, version=version)
        else:
            draft = AssignmentDraft.objects.filter(assignment=assignment).first()

        if not draft:
            return {"success": False, "output": "No draft found."}

        return {
            "success": True,
            "output": f"Assignment: {assignment.title}\nVersion: {draft.version}\nWords: {draft.word_count_actual}\nFile: {draft.file_path}\n\n{draft.content[:500]}..."
        }
    except Exception as e:
        return {"success": False, "output": str(e)}
    
def plan_trip(user_id: int, destination: str, departure_date: str, 
              return_date: str, purpose: str = "leisure") -> dict:
    """Autonomously research and plan a complete trip itinerary."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Trip
        from django.utils import timezone
        from datetime import datetime

        user = User.objects.get(id=user_id)

        # Parse dates
        dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
        ret_date = datetime.strptime(return_date, "%Y-%m-%d").date()
        duration = (ret_date - dep_date).days

        # Create trip record
        trip = Trip.objects.create(
            user=user,
            destination=destination,
            purpose=purpose,
            departure_date=dep_date,
            return_date=ret_date,
            status='planning'
        )

        # Research destination
        weather = web_search(f"weather in {destination} {departure_date}")
        general = web_search(f"{destination} travel guide tips {datetime.now().year}")
        practical = web_search(f"{destination} visa requirements hotels transport for pakistani traveler")

        weather_data = weather.get('output', '')
        general_data = general.get('output', '')
        practical_data = practical.get('output', '')

        # Generate full itinerary
        itinerary_response = _complete(
            "longform",
            [{
                "role": "user",
                "content": f"""Create a detailed {duration}-day trip plan for {destination}.

Trip details:
- Traveler: Awais Niazi (Pakistani citizen)
- Destination: {destination}
- Departure: {departure_date}
- Return: {return_date}
- Purpose: {purpose}
- Duration: {duration} days

Weather research:
{weather_data[:1500]}

General travel info:
{general_data[:1500]}

Practical info:
{practical_data[:1500]}

Create a complete trip plan in Markdown with:
## Trip Overview
- Quick summary, purpose, duration

## Weather & Packing
- Expected weather and what to pack

## Accommodation Recommendations
- 3 hotel options with price range and location

## Day by Day Itinerary
- Detailed plan for each day with morning/afternoon/evening activities

## Transportation
- How to get around, airport transfers, local transport

## Important Information
- Currency, language, emergency contacts, embassy location if relevant

## Budget Estimate
- Rough daily budget breakdown in USD

## Tips & Notes
- Cultural tips, must-try food, things to avoid

Write the complete plan now:"""
            }],
            max_tokens=4000,
        )

        itinerary = itinerary_response.choices[0].message.content

        # Save to database
        trip.itinerary = itinerary
        trip.status = 'confirmed'

        # Save as markdown file
        trips_dir = os.getenv('ASSIGNMENTS_PATH', '/home/awais-faiz/Documents/Ash/assignments')
        trips_dir = os.path.join(os.path.dirname(trips_dir), 'trips')
        os.makedirs(trips_dir, exist_ok=True)

        safe_dest = destination.replace(' ', '_').replace('/', '_')[:30]
        file_path = os.path.join(trips_dir, f"trip_{safe_dest}_{departure_date}.md")
        file_path = os.path.abspath(file_path)

        with open(file_path, 'w') as f:
            f.write(f"# Trip Plan — {destination}\n\n")
            f.write(f"**Destination:** {destination}\n")
            f.write(f"**Dates:** {departure_date} → {return_date} ({duration} days)\n")
            f.write(f"**Purpose:** {purpose}\n")
            f.write(f"**Generated:** {timezone.now().strftime('%B %d, %Y')}\n\n")
            f.write("---\n\n")
            f.write(itinerary)

        trip.file_path = file_path
        trip.save()

        return {
            "success": True,
            "output": f"Trip plan complete!\n- Destination: {destination}\n- Dates: {departure_date} → {return_date}\n- Duration: {duration} days\n- File: {file_path}\n- Trip ID: {trip.id}"
        }

    except Exception as e:
        return {"success": False, "output": str(e)}


def add_scheduled_task(user_id: int, name: str, cron_schedule: str,
                       prompt: str, task_type: str = "chat") -> dict:
    """Schedule a recurring task. cron_schedule is standard 5-field cron
    (min hour day month weekday), e.g. '0 8 * * *' for every day at 08:00
    Pakistan time (PKT). `prompt` is the instruction Ash runs when it fires."""
    try:
        from django.contrib.auth.models import User
        from agent.models import ScheduledTask
        from django.utils import timezone
        from croniter import croniter

        if not croniter.is_valid(cron_schedule):
            return {"success": False,
                    "output": f"'{cron_schedule}' is not a valid cron expression."}

        user = User.objects.get(id=user_id)
        task = ScheduledTask.objects.create(
            user=user,
            name=name,
            task_type=task_type,
            cron_schedule=cron_schedule,
            action={"type": task_type, "prompt": prompt},
            enabled=True,
            # Baseline last_run to creation time so the task fires at its NEXT
            # scheduled slot, not immediately on the next beat tick.
            last_run=timezone.now(),
        )
        return {
            "success": True,
            "output": f"Scheduled '{name}' (ID: {task.id}) — runs on cron '{cron_schedule}' (Pakistan time).",
        }
    except Exception as e:
        return {"success": False, "output": str(e)}


def list_scheduled_tasks(user_id: int) -> dict:
    """List all scheduled tasks for a user."""
    try:
        from django.contrib.auth.models import User
        from agent.models import ScheduledTask
        from django.utils import timezone

        user = User.objects.get(id=user_id)
        tasks = ScheduledTask.objects.filter(user=user)
        if not tasks.exists():
            return {"success": True, "output": "No scheduled tasks."}

        result = "Your scheduled tasks:\n\n"
        for t in tasks:
            state = "on" if t.enabled else "off"
            last = timezone.localtime(t.last_run).strftime('%b %d %H:%M') if t.last_run else "never"
            result += f"[{state}] {t.name} — cron '{t.cron_schedule}' (ID: {t.id})\n"
            result += f"   last run: {last} ({t.last_status})\n\n"
        return {"success": True, "output": result}
    except Exception as e:
        return {"success": False, "output": str(e)}


def delete_scheduled_task(task_id: int) -> dict:
    """Delete a scheduled task."""
    try:
        from agent.models import ScheduledTask
        task = ScheduledTask.objects.get(id=task_id)
        name = task.name
        task.delete()
        return {"success": True, "output": f"Deleted scheduled task '{name}'."}
    except ScheduledTask.DoesNotExist:
        return {"success": False, "output": f"Scheduled task {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def toggle_scheduled_task(task_id: int, enabled: bool = True) -> dict:
    """Enable or disable a scheduled task without deleting it."""
    try:
        from agent.models import ScheduledTask
        task = ScheduledTask.objects.get(id=task_id)
        task.enabled = bool(enabled)
        task.save(update_fields=["enabled"])
        state = "enabled" if task.enabled else "disabled"
        return {"success": True, "output": f"Scheduled task '{task.name}' {state}."}
    except ScheduledTask.DoesNotExist:
        return {"success": False, "output": f"Scheduled task {task_id} not found."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def notify(user_id: int, title: str, message: str) -> dict:
    """Send a SHORT push notification to the user's phone. Use for brief,
    genuinely useful, time-sensitive alerts (reminders, confirmations, nudges).
    Keep title a few words and message to 1-2 lines."""
    try:
        from django.contrib.auth.models import User
        from agent.notifications import send_push
        user = User.objects.get(id=user_id)
        n = send_push(user, (title or "Ash")[:80], (message or "")[:300])
        if n == 0:
            return {"success": False,
                    "output": "No devices are subscribed to notifications."}
        return {"success": True, "output": f"Notification sent to {n} device(s)."}
    except Exception as e:
        return {"success": False, "output": str(e)}


def get_trips(user_id: int) -> dict:
    """Get all trips for a user."""
    try:
        from django.contrib.auth.models import User
        from agent.models import Trip

        user = User.objects.get(id=user_id)
        trips = Trip.objects.filter(user=user).order_by('-departure_date')

        if not trips.exists():
            return {"success": True, "output": "No trips found."}

        result = "Your trips:\n\n"
        for t in trips:
            result += f"[{t.status.upper()}] {t.destination}\n"
            result += f"   Dates: {t.departure_date} → {t.return_date}\n"
            result += f"   Purpose: {t.purpose} | ID: {t.id}\n\n"

        return {"success": True, "output": result}
    except Exception as e:
        return {"success": False, "output": str(e)}    