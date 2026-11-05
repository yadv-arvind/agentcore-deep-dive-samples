from strands import Agent
from strands_tools import file_read

from .model import model
from .spec import Spec

planner = Agent(model=model, tools=[file_read], system_prompt=(
    "You are a software planner. Work with relative paths from the current directory, which is the repository. "
    "If you were not given a file listing, call file_read with mode 'find' and the glob '**/*.py'. Then view "
    "every file the change touches with mode 'view', copying paths exactly from the listing. A failed read "
    "means your path was wrong, so list again instead of assuming the file is missing. "
    "Plan only against what you read: reuse the existing modules and "
    "structure, and do not add layers (routers, services, repositories, models, a database) that the code does "
    "not already have. Extend existing test files instead of creating new ones. Then produce a spec: "
    "numbered requirements, a short design, and small tasks that each touch at most two files."))


def make_spec(request: str) -> Spec:
    result = planner(request, structured_output_model=Spec)   # runs the full tool loop, then returns the Spec
    return result.structured_output
