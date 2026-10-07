import shlex
import subprocess
import sys
from pathlib import Path

from strands import tool

MAX_CHARS = 4000


@tool
def run_pytest(args: str = "", cwd: str = ".") -> str:
    """Run pytest in a directory and return its output.

    Args:
        args: Extra pytest arguments, for example "tests/test_items.py -k health".
        cwd: Directory to run pytest in. Defaults to the current directory.
    """
    project = Path(cwd).resolve()
    # Prefer the target project's own virtual environment over this one.
    project_python = project / ".venv" / "bin" / "python"
    python = str(project_python) if project_python.exists() else sys.executable
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "-q", *shlex.split(args)],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "pytest timed out after 120 seconds"
    output = result.stdout + result.stderr
    if len(output) > MAX_CHARS:
        # Keep the tail: the failure details and the summary line come last.
        output = "[output truncated]\n" + output[-MAX_CHARS:]
    return f"exit code {result.returncode}\n{output}"
