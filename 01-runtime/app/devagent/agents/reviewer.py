from strands import Agent
from strands_tools import file_read

from .model import model

reviewer = Agent(model=model, tools=[file_read], system_prompt=(
    "Review a change against its spec. Reply APPROVE or list concrete problems. Do not rewrite code."))
