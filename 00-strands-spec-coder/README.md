# Spec-first coding agents with Strands Agents

A local multi-agent coder built with [Strands Agents](https://strandsagents.com/): a planner turns a request into a typed spec, an orchestrator drives a coder and a reviewer through each task in a repo you choose, and `run.py` verifies the result independently of what the agents report.

| Information | Details |
|:------------|:--------|
| Type        | Getting started |
| Language    | Python 3.12 |
| Framework   | Strands Agents (`strands-agents` 1.58.1) |
| Model       | Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) on Amazon Bedrock |
| Components  | Planner, coder, reviewer and orchestrator agents; local `pytest` tool; tool-call logging hook |
| Complexity  | Intermediate |

## Overview

- **Plan first.** The planner agent reads the target repo and returns a typed `Spec`: requirements, a short design, and tasks that each touch at most two files.
- **Agents as tools.** The orchestrator has two tools, `implement_task` and `review_change`. Each one wraps another agent with its own prompt, tools and context.
- **Real test output.** The coder writes code, runs `pytest` in the target repo and reads the actual failures. It stops after four attempts.
- **Independent check.** After the run, `run.py` compares the repo against a snapshot taken before the run. It checks which files changed, whether any test disappeared, and whether `pytest` passes.

## Architecture

```
run.py
  ├─ list_repo_files ──► request + file listing
  ├─ make_spec ────────► Planner agent (file_read) ──► Spec
  ├─ checks and y/N gate
  ├─ orchestrator ─────► implement_task ──► Coder agent (file_read, file_write, run_pytest)
  │                  └─► review_change ──► Reviewer agent (file_read)
  └─ verify ───────────► changed files, tests before and after, pytest
```

| Component | Purpose |
|:----------|:--------|
| Planner | Explores the repo with `file_read` and returns a `Spec`. It cannot write. |
| Orchestrator | Calls `implement_task`, then `review_change` once, for each task. It has no file access. |
| Coder | Implements one task. It reads and writes files and runs `run_pytest`. |
| Reviewer | Replies `APPROVE` or lists concrete problems. It reads only and does not rewrite code. |
| `run.py` | Lists the repo's files, calls the agents in order, asks for confirmation, and verifies the result. |

## Prerequisites

| Requirement | Version | Install |
|:------------|:--------|:--------|
| Python | 3.12 (tested) | [python.org](https://www.python.org/downloads/) |
| uv | any current version | `brew install uv` or [astral.sh/uv](https://astral.sh/uv) |
| AWS CLI | any current version | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |

- AWS credentials that can invoke Amazon Nova Pro on Amazon Bedrock (`bedrock:InvokeModel`). Verify them with:

  ```bash
  aws sts get-caller-identity
  ```

- Model access for Amazon Nova Pro in your region. See [Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html). The model ID is a US cross-region inference profile, so use a US region.
- A target repo with a `pytest` suite, committed to git so you can inspect and undo the agents' changes. The sample run uses a small FastAPI repo named `shop-api` (`app/main.py`, `tests/test_items.py`), cloned next to this repo. Give it its own `.venv` with `pytest` installed. `run_pytest` and the independent check use that environment when it exists.

## Quick start

Run these from the repository root, `agentcore-deep-dive-samples`.

```bash
# 1. Create the environment and install the pinned dependencies
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: set AWS_REGION. Uncomment AWS_PROFILE only if you use a named profile.

# 3. Plan only: prints the spec and writes nothing
cd 00-strands-spec-coder
python run.py "Add a DELETE /items/{item_id} endpoint" --repo ../../shop-api --plan-only --verbose

# 4. Plan, implement, review and verify
python run.py "Add a DELETE /items/{item_id} endpoint" --repo ../../shop-api --verbose
```

Step 4 prints the spec, then asks `Proceed with implementation? [y/N]`. Answer `y` to continue. Strands also asks `Do you want to proceed with the file write? [y/*]` before each file the coder writes. Review each path before you answer.

Each run calls Amazon Bedrock and is billed per invocation.

## Usage

| Option | Effect |
|:-------|:-------|
| `request` | What to build, in plain language. Required. |
| `--repo` | Path to the repository the agents work on. Required. |
| `--plan-only` | Print the spec and stop. Nothing is written. |
| `--yes` | Skip the `Proceed with implementation?` prompt. The file-write prompts still appear. |
| `--verbose` | Print every tool call, using the `ToolLog` hook from `hooks.py`. |

**Prompt**: "Add a DELETE /items/{item_id} endpoint"
**Expected behavior**: The planner reads the repo's files and returns two tasks, one for `app/main.py` and one for `tests/test_items.py`. The coder adds the endpoint and a test. The reviewer approves each task. The independent check reports the changed files and a passing suite.

## Sample run

This run used `shop-api` with four existing tests. The agents added eight lines to `app/main.py` and sixteen to `tests/test_items.py`, and the suite went from 4 to 6 passing tests. The full output follows.

<details>
<summary>Full output of the run</summary>

```text
python run.py "Add a DELETE /items/{item_id} endpoint" --repo ../../shop-api --verbose
Planning in /Users/arvindyadav/AIMasteryPersonal/shop-api ...
<thinking> To add a DELETE /items/{item_id} endpoint, I need to read the files that the change will touch. The files listed are.gitignore, app/__init__.py, app/main.py, pyproject.toml, tests/test_items.py, and uv.lock. I will use the file_read tool with mode 'view' to read these files. </thinking>

Tool #1: file_read

Tool #2: file_read

Tool #3: file_read

Tool #4: file_read

Tool #5: file_read

Tool #6: file_read
-> file_read {'mode': 'view', 'path': '.gitignore'}
-> file_read {'mode': 'view', 'path': 'app/__init__.py'}
-> file_read {'mode': 'view', 'path': 'app/main.py'}
-> file_read {'mode': 'view', 'path': 'pyproject.toml'}
-> file_read {'mode': 'view', 'path': 'tests/test_items.py'}
-> file_read {'mode': 'view', 'path': 'uv.lock'}
<- file_read done
<- file_read done
<- file_read done
<- file_read done
<- file_read done
<- file_read done
<thinking> Based on the file contents, I will plan the addition of the DELETE /items/{item_id} endpoint. The plan will include requirements, a short design, and small tasks that each touch at most two files. </thinking>


Tool #7: Spec
-> Spec {'requirements': ['Add a DELETE /items/{item_id} endpoint to remove an item by its ID.', 'Ensure the endpoint raises a 4
<- Spec done
{
  "requirements": [
    "Add a DELETE /items/{item_id} endpoint to remove an item by its ID.",
    "Ensure the endpoint raises a 404 error if the item does not exist.",
    "Update the tests to include a test for the DELETE endpoint."
  ],
  "design": "The DELETE /items/{item_id} endpoint will be added to the app/main.py file. It will remove the item with the specified ID from the _items dictionary. If the item does not exist, it will raise an HTTPException with a 404 status code. The tests/test_items.py file will be updated to include a test for this new endpoint.",
  "tasks": [
    {
      "title": "Add DELETE endpoint to app/main.py",
      "files": [
        "app/main.py"
      ],
      "acceptance": "The DELETE /items/{item_id} endpoint should remove the item with the specified ID from the _items dictionary. If the item does not exist, it should raise an HTTPException with a 404 status code."
    },
    {
      "title": "Update tests in tests/test_items.py",
      "files": [
        "tests/test_items.py"
      ],
      "acceptance": "The tests should include a test for the DELETE /items/{item_id} endpoint. The test should verify that the item is removed from the _items dictionary and that a 404 error is raised if the item does not exist."
    }
  ]
}

Proceed with implementation? [y/N] y

Baseline: 4 tests collected.

Implementing ...
<thinking> I need to implement and review each task in the spec. The first task is to add a DELETE endpoint to app/main.py. After implementing this task, I will review the change to ensure it meets the acceptance criteria. The second task is to update the tests in tests/test_items.py. After implementing this task, I will also review the change to ensure it meets the acceptance criteria. </thinking>

Tool #1: implement_task
-> implement_task {'task_json': '{"title": "Add DELETE endpoint to app/main.py", "files": ["app/main.py"], "acceptance": "The DELETE /item
<thinking> To complete this task, I need to add a DELETE endpoint to the app/main.py file. The endpoint should remove an item from the _items dictionary based on the item_id provided in the URL. If the item does not exist, it should raise an HTTPException with a 404 status code. I also need to add a test for this new endpoint to ensure it works as expected. </thinking>

Tool #1: file_read
-> file_read {'mode': 'view', 'path': 'app/main.py'}
<- file_read done
<thinking> The current app/main.py file does not have a DELETE endpoint. I will add the DELETE /items/{item_id} endpoint to remove the item with the specified ID from the _items dictionary. If the item does not exist, it will raise an HTTPException with a 404 status code. I will also add a test for this new endpoint. </thinking> 
Tool #2: file_write

Tool #3: file_read
-> file_write {'path': 'app/main.py', 'content': 'from fastapi import FastAPI, HTTPException\nfrom pydantic import BaseModel\n\napp = 
-> file_read {'mode': 'view', 'path': 'tests/test_items.py'}
<- file_read done
Do you want to proceed with the file write? [y/*] y
<- file_write done
<thinking> The DELETE endpoint has been added to app/main.py. Now, I need to add a test for this new endpoint in tests/test_items.py to ensure it works as expected. </thinking> 
Tool #4: file_write
-> file_write {'path': 'tests/test_items.py', 'content': 'import pytest\nfrom fastapi.testclient import TestClient\n\nfrom app import 
Do you want to proceed with the file write? [y/*] y
<- file_write done
<thinking> The test for the DELETE endpoint has been added to tests/test_items.py. Now, I need to run the tests to ensure everything works as expected. </thinking> 
Tool #5: run_pytest
-> run_pytest {'args': 'tests/test_items.py'}
<- run_pytest done
<thinking> All tests passed successfully, including the new test for the DELETE endpoint. There is a deprecation warning related to using `httpx` with `starlette.testclient`, but it does not affect the functionality of the tests. Since the task was completed successfully within the allowed attempts, I will report the last failure as "None". </thinking>

None<- implement_task done
<thinking> The first task to add the DELETE endpoint to app/main.py has been implemented successfully. Now, I need to review the change to ensure it meets the acceptance criteria. </thinking> 
Tool #2: review_change
-> review_change {'changed_files': 'app/main.py', 'spec_json': '{"requirements": ["Add a DELETE /items/{item_id} endpoint to remove an it
<thinking> To review the change against the spec, I need to check if the DELETE endpoint has been added to app/main.py and if it meets the requirements. Specifically, I need to verify that:
1. The DELETE /items/{item_id} endpoint has been added.
2. The endpoint removes the item with the specified ID from the _items dictionary.
3. The endpoint raises a 404 error if the item does not exist.
4. The tests have been updated to include a test for the DELETE endpoint. </thinking>

Tool #1: file_read

Tool #2: file_read
-> file_read {'mode': 'search', 'path': 'app/main.py', 'search_pattern': 'DELETE /items/{item_id}'}
-> file_read {'mode': 'search', 'path': 'tests/test_items.py', 'search_pattern': 'test_delete_item'}
<- file_read done
<- file_read done
<thinking> The tool results indicate that the DELETE /items/{item_id} endpoint has been added to app/main.py and that the tests/test_items.py file has been updated to include a test for the DELETE endpoint. However, I need to verify that the endpoint correctly removes the item from the _items dictionary and raises a 404 error if the item does not exist. </thinking> 
Tool #3: file_read

Tool #4: file_read
-> file_read {'mode': 'search', 'path': 'app/main.py', 'search_pattern': 'HTTPException'}
-> file_read {'mode': 'search', 'path': 'app/main.py', 'search_pattern': '_items.pop'}
<- file_read done
<- file_read done
<thinking> The tool results indicate that the DELETE endpoint correctly raises an HTTPException with a 404 status code if the item does not exist and that it removes the item from the _items dictionary using the del statement. This meets all the requirements specified in the spec. </thinking>

APPROVE<- review_change done
<thinking> The first task has been reviewed and approved. Now, I need to implement the second task to update the tests in tests/test_items.py. </thinking>

Tool #3: implement_task
-> implement_task {'task_json': '{"title": "Update tests in tests/test_items.py", "files": ["tests/test_items.py"], "acceptance": "The tes
<thinking> The tests in tests/test_items.py already include a test for the DELETE /items/{item_id} endpoint, as I added it in the previous step. The test verifies that the item is removed from the _items dictionary and that a 404 error is raised if the item does not exist. Since the tests already meet the acceptance criteria, I will report the last failure as "None". </thinking>

None<- implement_task done
<thinking> The second task to update the tests in tests/test_items.py has been implemented successfully. Now, I need to review the change to ensure it meets the acceptance criteria. </thinking>

Tool #4: review_change
-> review_change {'changed_files': 'tests/test_items.py', 'spec_json': '{"requirements": ["Add a DELETE /items/{item_id} endpoint to remo
<thinking> To review the change against the spec, I need to check if the tests for the DELETE endpoint have been added to tests/test_items.py and if they meet the requirements. Specifically, I need to verify that:
1. The tests include a test for the DELETE /items/{item_id} endpoint.
2. The test verifies that the item is removed from the _items dictionary.
3. The test verifies that a 404 error is raised if the item does not exist. </thinking>

Tool #5: file_read
-> file_read {'mode': 'search', 'path': 'tests/test_items.py', 'search_pattern': 'test_delete_item'}
<- file_read done
<thinking> The tool results indicate that a test for the DELETE endpoint has been added to tests/test_items.py. However, I need to verify that the test correctly verifies that the item is removed from the _items dictionary and that a 404 error is raised if the item does not exist. </thinking>

Tool #6: file_read

Tool #7: file_read
-> file_read {'mode': 'search', 'path': 'tests/test_items.py', 'search_pattern': 'assert response.status_code == 200'}
-> file_read {'mode': 'search', 'path': 'tests/test_items.py', 'search_pattern': 'assert response.status_code == 404'}
<- file_read done
<- file_read done
<thinking> The tool results indicate that the test for the DELETE endpoint correctly verifies that the item is removed from the _items dictionary (assert response.status_code == 200) and that a 404 error is raised if the item does not exist (assert response.status_code == 404). This meets all the requirements specified in the spec. </thinking>

APPROVE<- review_change done
<thinking> Both tasks have been implemented and reviewed successfully. The first task to add the DELETE endpoint to app/main.py was approved, and the second task to update the tests in tests/test_items.py was also approved. </thinking>

Both tasks passed and were approved. The DELETE endpoint was successfully added to app/main.py, and the tests in tests/test_items.py were updated to include a test for the DELETE endpoint. All acceptance criteria were met.
<thinking> Both tasks have been implemented and reviewed successfully. The first task to add the DELETE endpoint to app/main.py was approved, and the second task to update the tests in tests/test_items.py was also approved. </thinking>

Both tasks passed and were approved. The DELETE endpoint was successfully added to app/main.py, and the tests in tests/test_items.py were updated to include a test for the DELETE endpoint. All acceptance criteria were met.


== Independent check (not the agents' report) ==
Changed files:
  app/main.py: +8 -0
  tests/test_items.py: +16 -0
Tests: 4 before, 6 after. pytest: 6 passed, 1 warning in 0.11s
No problems found.
```

</details>

### What the output shows

- **Planning:** The planner viewed all six files from the listing, then returned a two-task spec that touches only `app/main.py` and `tests/test_items.py`.
- **Baseline:** `run.py` collected 4 tests before the orchestrator started.
- **Implementation:** The coder read `app/main.py`, wrote the whole file back with the new endpoint, wrote the test file the same way, and ran `run_pytest`. Each write waited for your `y`.
- **Review:** The reviewer searched the changed files for the endpoint, the `HTTPException` and the assertions, and replied `APPROVE` for both tasks.
- **Independent check:** The changes are additions only (+8 and +16 lines, nothing removed), and the suite went from 4 to 6 tests with all passing.
- **Duplicate summary:** The final summary appears twice. Strands streams it while the orchestrator runs, and `run.py` prints the result again.

## How it works

1. `run.py` — parses the arguments, adds the repo root to the import path, sets `PITWALL_RESOURCES` to `resources.yaml`, and changes into the target repo so relative paths resolve there.
2. `run.py` — builds a file listing with `git ls-files` (tracked and untracked, minus ignored files) and puts it in the planner's request, so the model does not type paths itself.
3. `agents/planner.py` — `make_spec` calls the planner with `structured_output_model=Spec`. This runs the full tool loop, so the planner can call `file_read` before it answers.
4. `run.py` — stops if the spec has no tasks or names a file in a directory that does not exist. It lists files the plan will create, and asks `Proceed with implementation? [y/N]`.
5. `run.py` — records the test ids and the changed files before the orchestrator starts.
6. `agents/orchestrator.py` — the orchestrator calls `tools/implement_task.py` and then `tools/review_change.py` for each task. Those tools run `agents/coder.py` and `agents/reviewer.py`. The coder prompt says to read a file before changing it, write back the whole file with existing code kept, and stop after four attempts.
7. `tools/run_pytest.py` — `run_pytest` runs `pytest -q` with the target repo's `.venv` when one exists. It has a 120-second timeout and returns the last 4,000 characters of output.
8. `run.py` — `verify` compares the repo with the snapshot and runs the suite again. It reports `NEEDS REVIEW`, and exits with code 1, if a file outside the spec changed, a file lost more lines than it gained, a test disappeared, or `pytest` fails.

## Key concepts

- **Spec first.** The planner returns a Pydantic `Spec` and not prose, so `run.py` can check it and the orchestrator can work through `spec.tasks` one at a time.
- **Agents as tools.** `implement_task` and `review_change` are `@tool` functions that call the coder and reviewer. Each agent keeps its own context and prompt.
- **Least privilege.** Only the coder has `file_write`. The planner and reviewer can only read, and the orchestrator has no file tools.
- **Verify outside the agents.** An agent's report can be wrong: an earlier run of this sample reported a passing task for an app that could not start. The independent check relies on `git` and `pytest` and not on what the model says.
- **Write consent.** The `file_write` tool from `strands-agents-tools` asks for confirmation before each write. Setting `BYPASS_TOOL_CONSENT=true` removes the prompt, but then the agents write without asking.

## Configuration

| Setting | Where | Description |
|:--------|:------|:------------|
| `AWS_REGION` | `.env` | Required. `settings.py` exits if it is missing. |
| `AWS_PROFILE` | `.env` | Optional. Commented out in `.env.example`. Set it only if you use a named profile. An empty value breaks `boto3`. |
| `PITWALL_RESOURCES` | environment | Path to the resources file. `run.py` defaults it to `resources.yaml` in the repository root. |
| `model_id` | `resources.yaml` | The Bedrock model ID, `us.amazon.nova-pro-v1:0`. |

## Project structure

| File | Description |
|:-----|:------------|
| `run.py` | Entry point: file listing, planning, spec checks, confirmation, orchestration and the independent check |
| `agents/planner.py` | The planner agent and `make_spec` |
| `agents/coder.py` | The coder agent |
| `agents/reviewer.py` | The reviewer agent |
| `agents/orchestrator.py` | The orchestrator agent |
| `agents/spec.py` | The `Spec` and `Task` Pydantic models |
| `agents/model.py` | The Bedrock model that every agent shares |
| `tools/implement_task.py` | Tool that runs the coder on one task |
| `tools/review_change.py` | Tool that runs the reviewer on a change |
| `tools/run_pytest.py` | Tool that runs `pytest` in the target repo |
| `hooks.py` | `ToolLog`, a hook that prints each tool call. `run.py --verbose` attaches it to every agent. |

`settings.py`, `resources.yaml` and `requirements.txt` live in the repository root.

## Troubleshooting

### Issue: `botocore.exceptions.ProfileNotFound: The config profile () could not be found`
**Solution**: `.env` contains an empty `AWS_PROFILE=` line, which sets the variable to an empty string. Delete the line or comment it out, then rerun.

### Issue: `Missing environment variable AWS_REGION. Copy .env.example to .env and fill it in.`
**Solution**: `.env` is missing or `AWS_REGION` is empty. Run `cp .env.example .env` from the repository root and set the region.

### Issue: `ModuleNotFoundError: No module named 'strands'`
**Solution**: The virtual environment is not active or the packages are not installed. Run `source .venv/bin/activate` and `uv pip install -r requirements.txt` from the repository root.

### Issue: `The spec has no tasks, so there is nothing to implement.`
**Solution**: The planner returned an empty plan. Rephrase the request with a concrete change, then rerun with `--plan-only` to check the spec before you implement.

### Issue: `The spec refers to paths that do not exist in the repo, so the plan is probably invented`
**Solution**: The planner named a file in a directory the repo does not have. Nothing was written. Rerun `--plan-only`, and make the request more specific if it repeats.

### Issue: `NEEDS REVIEW` after the independent check
**Solution**: Read the listed problems and run `git diff` in the target repo. Keep the change only if it matches what you asked for. To discard it, follow Clean up.

## Clean up

The sample deploys nothing and leaves no cloud resources. It changes files in the target repo. To undo those changes, run this inside the target repo:

```bash
git checkout -- . && git clean -fd
```

This discards every uncommitted change in that repo, including work that did not come from the agents. It also deletes untracked files that `.gitignore` does not cover. Commit anything you want to keep first.

## Next steps

- **Host the agents** → run the same planner and orchestrator on Amazon Bedrock AgentCore Runtime instead of your laptop.
- **Sandbox the tests** → replace the local `run_pytest` tool with AgentCore Code Interpreter, so model-written code does not run on your machine.

## Additional resources

- [Strands Agents](https://strandsagents.com/)
- [Strands Agents SDK for Python](https://github.com/strands-agents/sdk-python)
- [Strands Agents tools](https://github.com/strands-agents/tools)
- [Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)

## Disclaimer

This sample lets a language model write files in the target repo, so review the diff before you keep any change.
