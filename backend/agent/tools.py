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