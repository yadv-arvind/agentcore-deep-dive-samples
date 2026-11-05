from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands_tools import file_read, file_write

from tools.run_pytest import run_pytest
from .model import model

coder = Agent(model=model, tools=[file_read, file_write, run_pytest],
    conversation_manager=SlidingWindowConversationManager(window_size=20),
    system_prompt=("Implement exactly one task. Write code and tests, run the tests, read the real "
                   "failure output, fix only what is broken. Stop after 4 attempts and report the last failure. "
                   "Never claim tests pass without having just run them. "
                   "Before changing a file, read it. file_write replaces the whole file, so write back the complete "
                   "file with every existing function, endpoint and test kept exactly as it was, and add or change "
                   "only what the task needs. Add new tests to the existing test file. Never delete or rewrite "
                   "existing tests, and never create a new file when the task names an existing one."))
