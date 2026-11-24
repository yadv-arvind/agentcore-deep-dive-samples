"""The agents' file tools. They act on the repository in the Code Interpreter sandbox, never on this container's disk."""
from strands import tool

import sandbox

MAX_READ_CHARS = 100_000          # write_file replaces a whole file, so a read must never be cut short


@tool
def list_files() -> str:
    """List every file in the repository, as relative paths, one per line."""
    try:
        return "\n".join(sandbox.active().list_files()) or "(the repository is empty)"
    except sandbox.SandboxError as exc:
        return f"error: {exc}"


@tool
def read_file(path: str) -> str:
    """Read one file from the repository and return its full contents.

    Args:
        path: Relative path from the repository root, for example "app/main.py".
    """
    try:
        text = sandbox.active().read_file(path)
    except sandbox.SandboxError as exc:
        return f"error: {exc}"
    if len(text) > MAX_READ_CHARS:
        return f"error: {path} is larger than {MAX_READ_CHARS} characters, so it cannot be read safely"
    return text


@tool
def write_file(path: str, content: str) -> str:
    """Write a file in the repository, replacing it if it exists, and creating its directories.

    Args:
        path: Relative path from the repository root, for example "tests/test_items.py".
        content: The complete new contents of the file.
    """
    try:
        sandbox.active().write_file(path, content)
    except sandbox.SandboxError as exc:
        return f"error: {exc}"
    return f"wrote {path} ({len(content)} characters)"
