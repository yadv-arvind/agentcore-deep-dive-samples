from settings import settings
from pydantic import BaseModel
from strands import Agent, tool
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models import BedrockModel
from strands_tools import file_read, file_write
from local_tools import run_pytest                  # subprocess pytest, output truncated to 4k chars

model = BedrockModel(model_id=settings.model_id, region_name=settings.region)

class Task(BaseModel):
    title: str
    files: list[str]
    acceptance: str

class Spec(BaseModel):
    requirements: list[str]
    design: str
    tasks: list[Task]

planner = Agent(model=model, tools=[file_read], system_prompt=(
    "You are a software planner. Work with relative paths from the current directory, which is the repository. "
    "If you were not given a file listing, call file_read with mode 'find' and the glob '**/*.py'. Then view "
    "every file the change touches with mode 'view', copying paths exactly from the listing. A failed read "
    "means your path was wrong, so list again instead of assuming the file is missing. "
    "Plan only against what you read: reuse the existing modules and "
    "structure, and do not add layers (routers, services, repositories, models, a database) that the code does "
    "not already have. Extend existing test files instead of creating new ones. Then produce a spec: "
    "numbered requirements, a short design, and small tasks that each touch at most two files."))

coder = Agent(model=model, tools=[file_read, file_write, run_pytest],
    conversation_manager=SlidingWindowConversationManager(window_size=20),
    system_prompt=("Implement exactly one task. Write code and tests, run the tests, read the real "
                   "failure output, fix only what is broken. Stop after 4 attempts and report the last failure. "
                   "Never claim tests pass without having just run them. "
                   "Before changing a file, read it. file_write replaces the whole file, so write back the complete "
                   "file with every existing function, endpoint and test kept exactly as it was, and add or change "
                   "only what the task needs. Add new tests to the existing test file. Never delete or rewrite "
                   "existing tests, and never create a new file when the task names an existing one."))

reviewer = Agent(model=model, tools=[file_read], system_prompt=(
    "Review a change against its spec. Reply APPROVE or list concrete problems. Do not rewrite code."))

def make_spec(request: str) -> Spec:
    result = planner(request, structured_output_model=Spec)   # runs the full tool loop, then returns the Spec
    return result.structured_output

@tool
def implement_task(task_json: str) -> str:
    """Implement one task from the spec and return a summary including the final test result."""
    return str(coder(task_json))

@tool
def review_change(spec_json: str, changed_files: str) -> str:
    """Ask the reviewer whether the changed files satisfy the spec."""
    return str(reviewer(f"Spec:\n{spec_json}\n\nChanged files:\n{changed_files}"))

orchestrator = Agent(model=model, tools=[implement_task, review_change], system_prompt=(
    "You are devagent. For each task in the spec call implement_task, then call review_change once. "
    "Report which tasks passed and which did not."))
