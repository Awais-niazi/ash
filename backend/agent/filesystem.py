"""
Sandboxed file-management for Ash.

Everything the agent does on the filesystem goes through _safe_path(), which
confines operations to ASH_FILES_ROOT (default: the user's home directory) and
refuses to touch sensitive paths (.ssh, .env, private keys, etc). This is the
single choke point that keeps a chatty/confused model from reading secrets or
writing outside the workspace.
"""

import os
import shutil

# Root that all file operations are confined to. Defaults to the user's home so
# Ash can organise Downloads/Documents, but never /etc, /, or another user.
ASH_FILES_ROOT = os.path.realpath(
    os.path.expanduser(os.getenv("ASH_FILES_ROOT", "~"))
)

# Path components that are always off-limits, anywhere under the root.
_DENY_PARTS = {
    ".ssh", ".gnupg", ".aws", ".pki", ".password-store", ".config/gcloud",
}
# Exact filenames that are always off-limits.
_DENY_FILES = {
    ".env", ".pgpass", ".netrc", "credentials",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
# Suffixes that are always off-limits (private keys / secrets).
_DENY_SUFFIXES = (".pem", ".key")


class UnsafePathError(ValueError):
    """Raised when a requested path escapes the sandbox or hits a secret."""


def _safe_path(path: str, must_exist: bool = False) -> str:
    """Resolve *path* and guarantee it stays inside the sandbox.

    Returns the absolute, symlink-resolved path. Raises UnsafePathError on any
    attempt to escape ASH_FILES_ROOT or touch a denied file.
    """
    if not path or not str(path).strip():
        raise UnsafePathError("Empty path")

    expanded = os.path.expanduser(str(path).strip())
    if not os.path.isabs(expanded):
        expanded = os.path.join(ASH_FILES_ROOT, expanded)

    # Resolve symlinks so a link can't smuggle us out of the root.
    resolved = os.path.realpath(expanded)

    # Must live inside the root (or be the root itself).
    if os.path.commonpath([resolved, ASH_FILES_ROOT]) != ASH_FILES_ROOT:
        raise UnsafePathError(
            f"Path is outside Ash's allowed workspace ({ASH_FILES_ROOT})"
        )

    # Reject sensitive components / filenames anywhere in the path.
    rel = os.path.relpath(resolved, ASH_FILES_ROOT)
    parts = [] if rel == "." else rel.split(os.sep)
    for part in parts:
        if part in _DENY_PARTS:
            raise UnsafePathError(f"'{part}' is a protected location")
    name = os.path.basename(resolved)
    if name in _DENY_FILES or name.endswith(_DENY_SUFFIXES):
        raise UnsafePathError(f"'{name}' is a protected file")

    if must_exist and not os.path.exists(resolved):
        raise UnsafePathError(f"Path does not exist: {path}")

    return resolved


def _display(path: str) -> str:
    """Show paths relative to home when possible, for friendlier output."""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    return path


# How organise_folder groups files when sorting by type.
CATEGORY_MAP = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
               ".heic", ".tiff", ".ico"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt",
                  ".tex", ".epub"],
    "Spreadsheets": [".xls", ".xlsx", ".csv", ".ods"],
    "Presentations": [".ppt", ".pptx", ".odp", ".key"],
    "Videos": [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv"],
    "Audio": [".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"],
    "Archives": [".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz"],
    "Code": [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
             ".sh", ".c", ".cpp", ".h", ".java", ".go", ".rs", ".rb", ".php",
             ".sql", ".yml", ".yaml"],
    "Installers": [".deb", ".appimage", ".exe", ".dmg", ".msi", ".rpm", ".pkg"],
}


def _category_for(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    for category, exts in CATEGORY_MAP.items():
        if ext in exts:
            return category
    return "Other"


def _unique_destination(dest_dir: str, filename: str) -> str:
    """Return a path in dest_dir that won't clobber an existing file."""
    target = os.path.join(dest_dir, filename)
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(filename)
    i = 1
    while True:
        candidate = os.path.join(dest_dir, f"{stem} ({i}){ext}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def list_directory(path: str = "~") -> dict:
    """List the contents of a directory (folders first, then files)."""
    try:
        target = _safe_path(path, must_exist=True)
        if not os.path.isdir(target):
            return {"success": False, "output": f"Not a directory: {path}"}

        dirs, files = [], []
        for entry in sorted(os.listdir(target)):
            full = os.path.join(target, entry)
            if os.path.isdir(full):
                dirs.append(entry)
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                files.append((entry, size))

        lines = [f"Contents of {_display(target)}:", ""]
        for d in dirs:
            lines.append(f"  📁 {d}/")
        for name, size in files:
            lines.append(f"  📄 {name}  ({_human_size(size)})")
        if not dirs and not files:
            lines.append("  (empty)")
        return {"success": True, "output": "\n".join(lines)}
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def create_folder(path: str) -> dict:
    """Create a folder (and any missing parents)."""
    try:
        target = _safe_path(path)
        os.makedirs(target, exist_ok=True)
        return {"success": True, "output": f"Created folder {_display(target)}"}
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def move_file(source: str, destination: str) -> dict:
    """Move a file or folder into destination.

    If destination is an existing directory, the item is moved inside it;
    otherwise destination is treated as the new path. Name collisions are
    resolved automatically instead of overwriting.
    """
    try:
        src = _safe_path(source, must_exist=True)
        dst = _safe_path(destination)

        if os.path.isdir(dst):
            dst = _unique_destination(dst, os.path.basename(src))
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                dst = _unique_destination(os.path.dirname(dst),
                                          os.path.basename(dst))

        shutil.move(src, dst)
        return {
            "success": True,
            "output": f"Moved {_display(src)} → {_display(dst)}",
        }
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def rename_file(path: str, new_name: str) -> dict:
    """Rename a file or folder in place (new_name is a bare name, not a path)."""
    try:
        src = _safe_path(path, must_exist=True)
        if os.sep in new_name or (os.altsep and os.altsep in new_name):
            return {"success": False,
                    "output": "new_name must be a name, not a path"}
        dst = _safe_path(os.path.join(os.path.dirname(src), new_name))
        if os.path.exists(dst):
            return {"success": False,
                    "output": f"'{new_name}' already exists here"}
        os.rename(src, dst)
        return {"success": True,
                "output": f"Renamed to {_display(dst)}"}
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def organize_folder(path: str, by: str = "type") -> dict:
    """Sort the loose files in a folder into ordered subfolders.

    by="type": group into Images/Documents/Videos/... by file extension.
    by="date": group into YYYY-MM subfolders by modification time.
    Subfolders already present are left untouched; only top-level files move.
    """
    try:
        target = _safe_path(path, must_exist=True)
        if not os.path.isdir(target):
            return {"success": False, "output": f"Not a directory: {path}"}
        if by not in ("type", "date"):
            return {"success": False, "output": "by must be 'type' or 'date'"}

        import datetime

        moved = 0
        buckets = {}
        for entry in os.listdir(target):
            full = os.path.join(target, entry)
            if entry.startswith(".") or not os.path.isfile(full):
                continue  # skip hidden files and existing subfolders
            if by == "type":
                bucket = _category_for(entry)
            else:
                mtime = os.path.getmtime(full)
                bucket = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m")

            dest_dir = os.path.join(target, bucket)
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(full, _unique_destination(dest_dir, entry))
            buckets[bucket] = buckets.get(bucket, 0) + 1
            moved += 1

        if moved == 0:
            return {"success": True,
                    "output": f"Nothing to organise in {_display(target)}."}

        summary = "\n".join(f"  📁 {name}/  ← {n} file(s)"
                            for name, n in sorted(buckets.items()))
        return {
            "success": True,
            "output": f"Organised {moved} file(s) in {_display(target)}:\n{summary}",
        }
    except UnsafePathError as e:
        return {"success": False, "output": str(e)}
    except Exception as e:
        return {"success": False, "output": str(e)}


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(num)} B"
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"
