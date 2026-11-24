from strands import Agent
from strands.tools.executors import SequentialToolExecutor

from tools.implement_task import implement_task
from tools.review_change import review_change
from .model import model

# Strands runs tool calls from one model turn in parallel by default. The review must wait for the
# implementation, so run them in order.
orchestrator = Agent(model=model, tools=[implement_task, review_change], tool_executor=SequentialToolExecutor(),
    system_prompt=(
    "You are devagent. For each task in the spec call implement_task, then call review_change once. "
    "Report which tasks passed and which did not."))
