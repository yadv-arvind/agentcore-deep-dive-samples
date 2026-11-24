# Keep the repo and its tests in AgentCore Code Interpreter

Host the planner, coder and reviewer from [`01-runtime`](../01-runtime/) on AgentCore Runtime, and move the repository itself into a managed [Amazon Bedrock AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html) sandbox. Runtime runs the agents and the check. Every file the agents read or write, and every test run, happens in the sandbox.

| Information | Details |
|:------------|:--------|
| Type        | Feature demo |
| Language    | Python 3.12 locally, `PYTHON_3_14` on Runtime |
| Framework   | Strands Agents (`strands-agents` 1.62.x, `strands-agents-tools` below 0.9) |
| Model       | Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) on Amazon Bedrock |
| Components  | AgentCore Runtime, AgentCore Code Interpreter |
| Complexity  | Intermediate |

> [!NOTE]
> One job has completed locally against the real Code Interpreter sandbox, and the output is in Step 2. The deploy steps (3 to 5) have not been run. Exact file round trips for unusual files, such as CRLF line endings or no final newline, are unchecked: Step 1 tests them.

## Overview

- **The same agents.** `01-runtime` copied to this folder, deployed as its own stack, so both samples can exist side by side.
- **The sandbox is the workspace.** `main.py` starts a Code Interpreter session before planning, uploads the bundled snapshot into it once, and stops the session after the check. The Runtime container never holds a working copy of the repo.
- **File tools that act on the sandbox.** `list_files`, `read_file` and `write_file` replace the local `file_read` and `file_write`. They reject any path outside the repository, so a model-chosen path cannot reach the agent's own code.
- **A narrow test tool.** `run_pytest` runs pytest in the sandbox. The model cannot run any other command there.
- **An independent check that stays independent.** `verify.py` runs in Runtime. It fetches the final files and runs its test collection and final pytest through the sandbox, then judges the result in trusted code. A check that ran inside the sandbox could be fooled by what it checks.
- **Sandbox network mode.** The sample uses the AWS-managed interpreter `aws.codeinterpreter.v1`, which has no network, so pip cannot install anything. `sandbox.py` uploads pytest's pure-Python files from the container into the sandbox at start, then checks that they run. It fails early with a clear message if the sandbox lacks `fastapi` or `httpx`.

## Architecture

```
client (agentcore invoke --session-id <id>)
   │
   ▼
AgentCore Runtime session (trusted: has the execution role's credentials)
   └─ main.py: background job
        planner / orchestrator / coder / reviewer   (LLM loops, call Bedrock)
        verify.py                                    (judges the result)
              │  list_files · read_file · write_file · run_pytest · download
              ▼
Code Interpreter session (untrusted: no credentials, sandbox network mode)
   └─ repo/   the only copy of the repository. Files are written and tests run here.
```

| Component | Purpose |
|:----------|:--------|
| `sandbox.py` | `Sandbox`: starts and stops the session, uploads pytest, checks packages, loads the snapshot, reads, writes and lists files, dumps the repo, runs pytest, reads exit codes |
| `tools/files.py` | `list_files`, `read_file`, `write_file`: the agents' only way to touch the repo |
| `tools/run_pytest.py` | The coder's test tool, and `pytest_output()` for `verify.py` |
| `verify.py` | The independent check. It compares the sandbox's final files with the bundled snapshot. |
| `main.py` | Starts the sandbox first, so a broken sandbox fails the job before any model call |
| `agentcore/cdk/lib/cdk-stack.ts` | Grants the runtime's execution role the Code Interpreter actions |
| `scripts/probe_sandbox.py` | Checks what the sandbox provides, before you deploy |

Why the agents stay in Runtime: they call Amazon Bedrock, so they need credentials and network access, and the sandbox has neither. Code Interpreter is a tool environment, not an agent host.

## Prerequisites

| Requirement | Version | Install |
|:------------|:--------|:--------|
| Python | 3.12 (tested) | [python.org](https://www.python.org/downloads/) |
| uv | any current version | `brew install uv` or [astral.sh/uv](https://astral.sh/uv) |
| Node.js | v26.0.0 (tested with `01-runtime`) | [nodejs.org](https://nodejs.org/) |
| AgentCore CLI | 0.31.1 (tested with `01-runtime`) | `npm install -g @aws/agentcore@0.31.1` |
| AWS CLI | any current version | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |

- AWS credentials, model access for Amazon Nova Pro in a US region, and a CDK-bootstrapped account and region, as in [`01-runtime`](../01-runtime/README.md#prerequisites).
- Your own credentials need `bedrock-agentcore:StartCodeInterpreterSession`, `InvokeCodeInterpreter` and `StopCodeInterpreterSession` for Steps 1 and 2. The deployed runtime gets them from the stack.

```bash
agentcore --version
aws sts get-caller-identity
```

## Quick start

Run these from `02-code-interpreter`. The first three steps cost a few cents at most. Step 4 creates AWS resources.

### 1. Probe the sandbox

The script starts one session on the AWS-managed interpreter, prints the raw response of a command, and checks bash, file writes, Python, the test packages and pip. It stops the session when it ends.

```bash
cd 02-code-interpreter
export AWS_REGION=us-east-1
uv run --no-project --with "bedrock-agentcore>=1.18.1" --with pyyaml python scripts/probe_sandbox.py
```

Read the output before you go on:

| Check | What to look for | If it fails |
|:------|:-----------------|:------------|
| 1. Raw events | `result` with `structuredContent` or `content` text | `sandbox.py` reads both. Tell me the shape if it differs. |
| 2. bash | `ok` then `exit=1` | `sandbox.py` runs every command through `bash -c` |
| 4. `writeFiles` and read-back | `OK` | `DIFFERENT` means files do not round trip exactly, so diffs and rewrites would be wrong. Stop and report it. |
| 5. Packages | `fastapi` and `httpx` `True`. `pytest` is not expected: it is uploaded, not installed. | Go to Step 1b |
| 6. pip | A network error is expected in sandbox network mode. It is not a failure. | Nothing to do: the sample does not use pip |

### 1b. If `fastapi` or `httpx` are missing

The default interpreter has no network, so pip cannot add them. A job stops at `starting_sandbox` with `the sandbox is missing ...`. Your choices:

- **Drop the target's imports.** Change `code_interpreter.packages` in `app/devagent/resources.yaml` to what the target repo's tests import. Anything missing that is pure Python can also go in `upload_packages`, which copies it from this container.
- **Use a custom interpreter with public network access.** Create it, put its ID in `code_interpreter.identifier`, and set `install_missing: true`. This leaves sandbox network mode.

### 2. Run it locally

`--skip-deploy` stops the CLI from creating a stack. The sandbox session is real, so this uses your credentials against AWS.

```bash
agentcore dev --skip-deploy
```

In a second terminal, start a job and stream its events. The curl uses port `8080`. Use the port that `agentcore dev` prints if it differs.

```bash
curl -N -X POST localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-Agentcore-Local: 1" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: local-session-0000000000000000000001" \
  -d '{"action":"run","request":"Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"}'
```

You should see events like these, trimmed. The curl prints each as an SSE `data:` line, and the lines here are decoded. The run took about 45 seconds:

```text
{"event": "accepted", "job_id": "fcbfc7ee-5f9a-4ee8-bd52-66b4834db69a"}
{"event": "sandbox_started", "at": 1795533018.3, "session_id": "01M871PZ50PBR63E45ECK3AG4H", "identifier": "aws.codeinterpreter.v1", "python": "Python 3.12.13", "pytest": "pytest 9.2.0"}
{"event": "snapshot_loaded", "at": 1795533018.9, "files": 6}
{"event": "planning", "at": 1795533019.3}
{"event": "spec_ready", "at": 1795533025.6, "tasks": ["Add GET /items/count endpoint", "Add test for GET /items/count endpoint"]}
{"event": "baseline", "at": 1795533027.0, "tests": 6}
{"event": "task_started", "at": 1795533029.3, "title": "Add GET /items/count endpoint"}
{"event": "file_written", "at": 1795533038.3, "path": "app/main.py"}
{"event": "tests_passed", "at": 1795533038.7, "summary": "exit code 0: 6 passed, 2 warnings in 0.32s"}
{"event": "file_written", "at": 1795533048.2, "path": "tests/test_items.py"}
{"event": "tests_passed", "at": 1795533048.4, "summary": "exit code 0: 6 passed, 2 warnings in 0.29s"}
{"event": "task_started", "at": 1795533051.0, "title": "Add test for GET /items/count endpoint"}
{"event": "task_reviewed", "at": 1795533055.6, "approved": true}
{"event": "task_reviewed", "at": 1795533058.3, "approved": true}
{"event": "sandbox_stopped", "at": 1795533063.0, "session_id": "01M871PZ50PBR63E45ECK3AG4H"}
{"event": "changes", "at": 1795533063.0, "diff": "--- a/app/main.py\n+++ b/app/main.py\n@@ -37,4 +37,9 @@ ..."}
{"event": "verified", "at": 1795533063.0, "ok": true, "problems": [], "files": {"app/main.py": {"added": 5, "deleted": 0}, "tests/test_items.py": {"added": 8, "deleted": 0}}, "tests_before": 6, "tests_after": 7, "pytest": "exit code 0: 7 passed, 2 warnings in 0.31s"}
{"event": "done", "at": 1795533063.0, "verified": true}
```

What the output shows:

- **The sandbox's life.** `sandbox_started` reports Python 3.12.13 and the uploaded `pytest 9.2.0`. `sandbox_stopped` comes before `changes` and `verified`, because the check has already fetched the files it needs.
- **The check.** `verified` compares the sandbox's final files with the snapshot: two files changed, both named in the spec, and the test count rose from 6 to 7.
- **What the check does not prove.** It proves that the tests pass and that only files in the spec changed. It does not prove the change matches the request. In this run the endpoint returns the bare number, and the request asked for `{"count": n}`. The reviewer approved it, and the test asserts the same bare number. Read the `changes` diff before you keep a change.

### 3. Set the deployment target and install the CDK dependencies

```bash
cp agentcore/aws-targets.example.json agentcore/aws-targets.json
# Edit agentcore/aws-targets.json: set account to your 12-digit account ID and region

cd agentcore/cdk
npm install
cd ../..
```

### 4. Deploy and invoke

```bash
# Check that the project builds and synthesizes. Nothing is created.
agentcore deploy --dry-run

# Create the stack AgentCore-codeinterpreterdevagent-default
agentcore deploy -v
agentcore status

agentcore invoke --session-id sandbox-session-00000000000000000001 --stream "Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"
```

### 5. Check that the tests ran in the sandbox

The `sandbox_started` event carries the Code Interpreter session ID, and `file_written` events name each file the coder wrote. Nothing is written to the container's disk, and the container runs no pytest process.

```bash
agentcore logs --since 30m
```

## How it works

### Why the repo lives in the sandbox

The coder's `write_file` and `run_pytest` act on one copy, so there is nothing to sync and nothing to go stale. `file_write` from `strands_tools` ran in the Runtime container and accepted any path, including one that overwrote the agent's own code. `write_file` rejects absolute paths and `..`, and it writes only inside the sandbox's `repo/` directory.

The session persists between calls, so the uploaded pytest and the repo survive a retry.

### How pytest gets into the sandbox

The default interpreter has no network and no `pytest`: a pip install there fails with `Failed to resolve 'pypi.org'`. So at start `sandbox.py` copies pytest into the sandbox.

1. `pyproject.toml` declares `pytest` as a dependency of this package. It is never run in the container. It is installed so its files can be read.
2. `vendored_files()` reads the `.py` files of `pytest`, `_pytest`, `pluggy`, `iniconfig`, `packaging` and `py` from the container's site-packages. The list is `code_interpreter.upload_packages`.
3. The files go to `vendor/` in the sandbox, in calls of up to about 400,000 characters. This is about 2 MB and 120 files.
4. pytest imports a few `pygments` names at start-up, only to colour output. The sample runs pytest with `--color=no`, so `sandbox.py` uploads small stubs for those names instead of the real package, which is 340 files.
5. Every pytest command runs with `PYTHONPATH` set to `vendor/`. After the upload, `python3 -m pytest --version` must work, or the job fails with `the pytest uploaded to the sandbox does not run`. The version appears in the `sandbox_started` event.

`vendor/` sits next to `repo/`, so the dump that `verify.py` diffs never includes it. The `pytest >= 9.2, < 9.3` cap in `pyproject.toml` matters: `agentcore package` ignores `uv.lock`, and the stubs fit this pytest version.

### What stays in Runtime

| Stays in Runtime | Why |
|:-----------------|:----|
| The planner, orchestrator, coder and reviewer | They call Bedrock, which needs the execution role |
| `verify.py`'s judgement | The check must run outside the thing it checks. A `conftest.py` that fakes passing tests is caught by the diff, not by pytest. |
| The bundled snapshot | The baseline for the diff. The sandbox gets a copy. |

The check fetches the final files and runs the final pytest in the sandbox, and it reads the files after the pytest run, so the diff reflects the state the tests left.

### Reading the exit code and file contents

`executeCommand` runs inside `bash -c` with stderr merged into stdout, and the script's last line prints `[exit code N]`. `sandbox.py` reads that marker instead of relying on how the service reports exit codes. A run with no marker raises `SandboxError`, and the job fails with the output. File contents are read with `cat` and returned exactly as printed, and the whole repo is fetched in one call as JSON, so trailing newlines and line endings survive. Probe check 4 confirms the service preserves them.

### New events

| Event | Meaning |
|:------|:--------|
| `sandbox_started` | The session ID, the interpreter identifier and the sandbox's Python version |
| `snapshot_loaded` | The number of files uploaded from the bundled snapshot |
| `file_written` | A `write_file` call succeeded, with the path |
| `sandbox_stopped` | The session ended cleanly. `sandbox_stop_failed` carries the error. |

A job whose sandbox cannot start ends in `failed` before any model call, with the cause in `error`.

### What changed from `01-runtime`

| File | Difference |
|:-----|:-----------|
| `sandbox.py` | New |
| `tools/files.py` | New. Replaces `file_read` and `file_write` from `strands_tools`. |
| `tools/run_pytest.py` | Runs in the sandbox. The `cwd` argument and the Runtime launcher and `LD_LIBRARY_PATH` workarounds are gone. |
| `agents/planner.py`, `coder.py`, `reviewer.py` | Use the sandbox file tools. The prompts name them. |
| `tools/review_change.py` | Reads the changed files from the sandbox |
| `verify.py` | Compares the sandbox's files with the snapshot. Paths are checked against the sandbox's file list. |
| `main.py` | No temp directory or `chdir`. Starts the sandbox, loads the snapshot, stops the sandbox, and adds the `starting_sandbox` status. |
| `progress.py` | Emits `file_written` |
| `settings.py`, `resources.yaml` | A `code_interpreter` section |
| `pyproject.toml`, `uv.lock` | `fastapi`, `httpx` and `strands-agents-tools` removed. `pytest` stays, capped at 9.2.x, only so `sandbox.py` can upload its files. |
| `agentcore.json` | Project `codeinterpreterdevagent`, runtime `code_interpreter_devagent_sandbox`, so the stack does not collide with `01-runtime` |
| `cdk-stack.ts` | The Code Interpreter policy statement on the execution role |

## Experiments

**Experiment 1: a failure comes back from the sandbox.** Ask for a change that breaks a test, such as "Make GET /health return {\"status\": \"up\"}". Expect `tests_failed` with the `FAILED` line, then a fix on a later attempt in the same session.

**Experiment 2: an orphaned session.** Set `session_timeout_seconds` to `3600` in `resources.yaml`, then kill the local dev server in the middle of a job. In the console, find the session that never reached `sandbox_stopped`. A job that fails normally always stops its session.

**Experiment 3: the package gap.** Add a package the sandbox lacks, such as `requests`, to `code_interpreter.packages`. The job fails at `starting_sandbox` with `the sandbox is missing requests`. Then use a custom interpreter in public network mode with `install_missing: true`, as in Step 1b, and compare.

## Configuration

| Setting | Where | Description |
|:--------|:------|:------------|
| `AWS_REGION` | environment | Required by `settings.py`. `main.py` falls back to `AWS_DEFAULT_REGION`, then the SDK's region. |
| `code_interpreter.identifier` | `app/devagent/resources.yaml` | `aws.codeinterpreter.v1` for the AWS-managed interpreter, or a custom interpreter's ID |
| `code_interpreter.session_timeout_seconds` | `app/devagent/resources.yaml` | How long a session lives. It is `1800`, and the SDK default is `900`. |
| `code_interpreter.python` | `app/devagent/resources.yaml` | The interpreter command in the sandbox, `python3` |
| `code_interpreter.packages` | `app/devagent/resources.yaml` | Modules that must already import in the sandbox: `fastapi`, `httpx` |
| `code_interpreter.upload_packages` | `app/devagent/resources.yaml` | Modules copied from the container into the sandbox: pytest and its dependencies |
| `code_interpreter.install_missing` | `app/devagent/resources.yaml` | Try `pip install` for a missing module. It is `false`, because it needs a custom interpreter with public network access. |
| `aws-targets.json` | `agentcore/` | The account and region to deploy to. Git ignores it. |

## Troubleshooting

### Issue: `Forbidden: missing X-Agentcore-Local header`
**Solution**: The local dev server in CLI 0.31.1 rejects any `POST` without an `X-Agentcore-Local` header, to stop other web pages from calling your local agent. It only checks that the header is present. Add `-H "X-Agentcore-Local: 1"` to the curl.

### Issue: `pytest is not installed in this container, so it cannot be uploaded to the sandbox`
**Solution**: The local dev server reuses `app/devagent/.venv`, which was built before `pytest` was added to `pyproject.toml`. Run `uv sync` in `app/devagent`, then restart `agentcore dev`. A deployed package installs its dependencies fresh, so this only affects local runs.

### Issue: `AccessDeniedException` on `StartCodeInterpreterSession`
**Solution**: In Steps 1 and 2 your own credentials need the Code Interpreter actions listed in Prerequisites. On a deployed runtime the execution role needs them, and `cdk-stack.ts` adds them. Check that the deploy finished.

### Issue: `the sandbox is missing fastapi, httpx ...`
**Solution**: The interpreter lacks the packages, and it has no network to install them. See Step 1b. The message includes pip's output when `install_missing` is `true`.

### Issue: `the pytest uploaded to the sandbox does not run`
**Solution**: The uploaded files imported something the sandbox lacks, or the sandbox's Python is older than pytest 9.2 supports (3.10 or later). Read the output in the message, and check the Python version in the probe.

### Issue: `not a path inside the repository`
**Solution**: A tool call used an absolute path or `..`. The tool returns the error to the model, which retries with a relative path. Repeated errors mean the prompt or the spec has absolute paths.

### Issue: `the sandbox gave no exit code for ...`
**Solution**: `bash` is missing, or the command was not run through a shell. Run the probe and read check 2.

### Issue: a job stays in `starting_sandbox`
**Solution**: Session start, the pytest upload (about 2 MB) or the package check is slow. Read `agentcore logs --since 30m`.

## Clean up

Remove the stack:

```bash
aws cloudformation delete-stack --stack-name AgentCore-codeinterpreterdevagent-default --region <your-region>
```

This deletes the runtime, its execution role and the role's policy. The CDK bootstrap resources remain, and so can the runtime's CloudWatch log group. Code Interpreter sessions end by themselves at `session_timeout_seconds`. List any left running in the console, and a session that has not ended still bills until then.

> [!WARNING]
> Deploying creates AWS resources, and model calls and sandbox sessions cost money. Run the clean-up when you finish.

## Next steps

- **Compare** → run the same request against [`01-runtime`](../01-runtime/) and diff the event streams.
- **Break it on purpose** → work through the experiments above, and note what you see in each.

## Additional resources

- [AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html)
- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [bedrock-agentcore SDK for Python](https://github.com/aws/bedrock-agentcore-sdk-python)
- [AgentCore CLI on GitHub](https://github.com/aws/agentcore-cli)
