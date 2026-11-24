import re

from strands import tool

import sandbox
from agents.reviewer import reviewer

MAX_FILE_CHARS = 8000


def file_blocks(changed_files: str) -> str:
    """The current contents of the named files, read from the sandbox so the reviewer does not depend on finding them."""
    blocks = []
    for name in dict.fromkeys(n for n in re.split(r"[,\s]+", changed_files) if n and n != "none"):
        try:
            text = sandbox.active().read_file(name)
        except sandbox.SandboxError:
            blocks.append(f"File: {name}\n(not found in the repository)")
        else:
            blocks.append(f"File: {name}\n```\n{text[:MAX_FILE_CHARS]}\n```")
    return "\n\n".join(blocks)


@tool
def review_change(spec_json: str, changed_files: str) -> str:
    """Ask the reviewer whether the changed files satisfy the spec."""
    return str(reviewer(f"Spec:\n{spec_json}\n\nChanged files, with their current contents:\n{file_blocks(changed_files)}"))
