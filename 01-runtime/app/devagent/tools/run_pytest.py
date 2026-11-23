import os
import shlex
import subprocess
import sys
import sysconfig
from pathlib import Path

from strands import tool

MAX_CHARS = 4000
# Shared libraries that the runtime's own Python build needs and the container's system libraries do not provide.
RUNTIME_LIBS = ("libpython*.so*", "libffi.so*")


def _runtime_lib_dirs() -> list[str]:
    """Directories that hold the shared libraries (libpython, libffi) of the running interpreter.

    AgentCore Runtime starts Python through a launcher that makes these findable. A child process
    that runs sys.executable directly does not get that, so it fails with "cannot open shared object file".
    """
    candidates = [sysconfig.get_config_var("LIBDIR"), str(Path(sys.base_prefix) / "lib")]
    candidates += [str(parent / "lib") for parent in Path(sys.executable).resolve().parents[:5]]
    found: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in found and Path(candidate).is_dir() and any(any(Path(candidate).glob(pattern)) for pattern in RUNTIME_LIBS):
            found.append(candidate)
    return found


def _python() -> str:
    """The interpreter for child processes. In Runtime, sys.executable is the binary inside bin/real/,
    and the launcher next to it (bin/python3.14) is what sets up its libraries, so prefer the launcher."""
    exe = Path(sys.executable)
    launcher = exe.parent.parent / exe.name
    return str(launcher) if exe.parent.name == "real" and launcher.is_file() else sys.executable


def _child_env() -> dict:
    env = os.environ.copy()
    # The Runtime launcher auto-instruments Python with OpenTelemetry, which adds log lines to the output.
    env["OTEL_SDK_DISABLED"] = "true"
    dirs = _runtime_lib_dirs()
    if dirs:
        env["LD_LIBRARY_PATH"] = ":".join(dirs + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    return env


def pytest_output(args: str = "", cwd: str = ".", timeout: int = 120) -> tuple[int, str]:
    """Run pytest in a directory. Returns (exit code, output), with code 124 when it times out."""
    project = Path(cwd).resolve()
    # Prefer the target project's own virtual environment over this one.
    project_python = project / ".venv" / "bin" / "python"
    python = str(project_python) if project_python.exists() else _python()
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "-q", *shlex.split(args)],
            cwd=project,
            env=_child_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"pytest timed out after {timeout} seconds"
    output = "\n".join(line for line in (result.stdout + result.stderr).splitlines() if "trace_id=" not in line)
    if "shared object file" in output and not _runtime_lib_dirs():
        output += f"\n[run_pytest] no runtime libraries found near {sys.executable}, LIBDIR={sysconfig.get_config_var('LIBDIR')}"
    return result.returncode, output


@tool
def run_pytest(args: str = "", cwd: str = ".") -> str:
    """Run pytest in a directory and return its output.

    Args:
        args: Extra pytest arguments, for example "tests/test_items.py -k health".
        cwd: Directory to run pytest in. Defaults to the current directory.
    """
    code, output = pytest_output(args, cwd)
    if len(output) > MAX_CHARS:
        # Keep the tail: the failure details and the summary line come last.
        output = "[output truncated]\n" + output[-MAX_CHARS:]
    return f"exit code {code}\n{output}"
