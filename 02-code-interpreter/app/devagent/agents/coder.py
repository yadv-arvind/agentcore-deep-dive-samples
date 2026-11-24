from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from tools.files import list_files, read_file, write_file
from tools.run_pytest import run_pytest
from .model import model

coder = Agent(model=model, tools=[list_files, read_file, write_file, run_pytest],
    conversation_manager=SlidingWindowConversationManager(window_size=20),
    system_prompt=("Implement exactly one task. Write code and tests, run the tests, read the real "
                   "failure output, fix only what is broken. Stop after 4 attempts and report the last failure. "
                   "Never claim tests pass without having just run them. "
                   "Paths are relative to the repository root. Before changing a file, read it. write_file replaces the whole file, so write back the complete "
                   "file with every existing function, endpoint and test kept exactly as it was, and add or change "
                   "only what the task needs. Add new tests to the existing test file. Never delete or rewrite "
                   "existing tests, and never create a new file when the task names an existing one. "
                   "In FastAPI, routes match in the order they are declared. A 422 from a new route such as "
                   "/items/count usually means an earlier route with a path parameter, such as /items/{item_id}, "
                   "matched first: declare fixed paths above parameterised ones with the same prefix, and when "
                   "you add a route, place it above any such route."))
