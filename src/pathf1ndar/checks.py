"""Read-only inspection using fixed argument vectors, never a shell."""
import shutil
import subprocess
import sys

COMMANDS = {"git": ("git", "--version"), "node": ("node", "--version"), "npm": ("npm", "--version")}


def inspect_environment() -> dict:
    results = {"python": {"available": sys.version_info >= (3, 11), "version": sys.version.split()[0], "detail": sys.executable}}
    for name, command in COMMANDS.items():
        executable = shutil.which(command[0])
        if executable is None:
            results[name] = {"available": False, "version": "", "detail": "Not found on PATH"}
            continue
        try:
            result = subprocess.run([executable, *command[1:]], capture_output=True, text=True, timeout=5, shell=False)
            version = result.stdout.strip() or result.stderr.strip()
            results[name] = {"available": result.returncode == 0, "version": version[:500], "detail": f"Exit code {result.returncode}"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            results[name] = {"available": False, "version": "", "detail": type(exc).__name__}
    return results
