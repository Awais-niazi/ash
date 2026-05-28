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