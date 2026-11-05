from strands import tool

from agents.coder import coder


@tool
def implement_task(task_json: str) -> str:
    """Implement one task from the spec and return a summary including the final test result."""
    return str(coder(task_json))
