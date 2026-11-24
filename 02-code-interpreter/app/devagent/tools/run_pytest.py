from strands import tool

import sandbox

MAX_CHARS = 4000


def pytest_output(args: str = "") -> tuple[int, str]:
    """Run pytest on the job's working copy inside the Code Interpreter sandbox. Returns (exit code, output)."""
    return sandbox.active().pytest(args)


@tool
def run_pytest(args: str = "") -> str:
    """Run pytest on the current working copy of the repository, in an isolated sandbox, and return its output.

    The sandbox gets a fresh copy of every file you have written so far, so call this after each change.

    Args:
        args: Extra pytest arguments, for example "tests/test_items.py -k health".
    """
    try:
        code, output = pytest_output(args)
    except sandbox.SandboxError as exc:
        return f"exit code 2\n[sandbox error] {exc}"
    if len(output) > MAX_CHARS:
        # Keep the tail: the failure details and the summary line come last.
        output = "[output truncated]\n" + output[-MAX_CHARS:]
    return f"exit code {code}\n{output}"
