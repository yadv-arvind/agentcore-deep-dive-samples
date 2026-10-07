from strands import tool

from agents.reviewer import reviewer


@tool
def review_change(spec_json: str, changed_files: str) -> str:
    """Ask the reviewer whether the changed files satisfy the spec."""
    return str(reviewer(f"Spec:\n{spec_json}\n\nChanged files:\n{changed_files}"))
