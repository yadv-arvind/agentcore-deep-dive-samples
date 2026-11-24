from strands import Agent
from tools.files import list_files, read_file
from .model import model
from .spec import Spec

planner = Agent(model=model, tools=[list_files, read_file], system_prompt=(
    "You are a software planner. Work with relative paths from the repository root. "
    "If you were not given a file listing, call list_files. Then call read_file on "
    "every file the change touches, copying paths exactly from the listing. A failed read "
    "means your path was wrong, so list again instead of assuming the file is missing. "
    "Plan only against what you read: reuse the existing modules and "
    "structure, and do not add layers (routers, services, repositories, models, a database) that the code does "
    "not already have. Extend existing test files instead of creating new ones. Then produce a spec: "
    "numbered requirements, a short design, and small tasks that each touch at most two files. "
    "Each task includes its own tests, because the coder writes code and tests together. "
    "Never create a task that only adds tests for another task."))


def make_spec(request: str) -> Spec:
    result = planner(request, structured_output_model=Spec)   # runs the full tool loop, then returns the Spec
    return result.structured_output
