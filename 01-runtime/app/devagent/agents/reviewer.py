from strands import Agent
from strands_tools import file_read

from .model import model

reviewer = Agent(model=model, tools=[file_read], system_prompt=(
    "Review a change against its spec. The changed files and their contents are in the message: judge them, "
    "and use file_read only for a file that is not shown. Reply APPROVE, or list concrete problems. "
    "Start with the verdict and do not show your reasoning. Do not rewrite code."))
