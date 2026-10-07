from strands import Agent

from tools.implement_task import implement_task
from tools.review_change import review_change
from .model import model

orchestrator = Agent(model=model, tools=[implement_task, review_change], system_prompt=(
    "You are devagent. For each task in the spec call implement_task, then call review_change once. "
    "Report which tasks passed and which did not."))
