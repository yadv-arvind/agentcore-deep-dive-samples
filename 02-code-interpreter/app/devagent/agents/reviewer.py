from strands import Agent
from tools.files import read_file
from .model import model

reviewer = Agent(model=model, tools=[read_file], system_prompt=(
    "Review a change against its spec. The changed files and their contents are in the message: judge them, "
    "and use read_file only for a file that is not shown. Reply APPROVE, or list concrete problems. "
    "Start with the verdict and do not show your reasoning. Do not rewrite code."))
