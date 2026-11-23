import re
from pathlib import Path

from strands import tool

from agents.reviewer import reviewer

MAX_FILE_CHARS = 8000


def file_blocks(changed_files: str) -> str:
    """The current contents of the named files, read here so the reviewer does not depend on finding them."""
    blocks = []
    for name in dict.fromkeys(n for n in re.split(r"[,\s]+", changed_files) if n and n != "none"):
        path = Path(name)
        if path.is_file() and ".." not in path.parts and not path.is_absolute():
            blocks.append(f"File: {name}\n```\n{path.read_text(errors='ignore')[:MAX_FILE_CHARS]}\n```")
        else:
            blocks.append(f"File: {name}\n(not found in the repository)")
    return "\n\n".join(blocks)


@tool
def review_change(spec_json: str, changed_files: str) -> str:
    """Ask the reviewer whether the changed files satisfy the spec."""
    return str(reviewer(f"Spec:\n{spec_json}\n\nChanged files, with their current contents:\n{file_blocks(changed_files)}"))
