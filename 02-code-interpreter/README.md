# Run the coder's tests in AgentCore Code Interpreter

Move test execution out of the agent's own container and into a managed [Amazon Bedrock AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html) sandbox. The planner, coder and reviewer from [`01-runtime`](../01-runtime/) are unchanged. Only where pytest runs is different.

| Information | Details |
|:------------|:--------|
| Type        | Feature demo |
| Language    | Python 3.12 locally, `PYTHON_3_14` on Runtime |
| Framework   | Strands Agents (`strands-agents` 1.62.x, `strands-agents-tools` below 0.9) |
| Model       | Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) on Amazon Bedrock |
| Components  | AgentCore Runtime, AgentCore Code Interpreter |
| Complexity  | Intermediate |

> [!NOTE]
> This sample has not been run against AWS yet. The sandbox logic is tested against a local fake of the Code Interpreter API, and the CDK change type-checks. The response shape and the packages in the sandbox come from the SDK source and are unconfirmed. Step 1 checks them before you deploy.

## Overview

- **The same agents.** `01-runtime` copied to this folder, deployed as its own stack, so both samples can exist side by side.
- **One sandbox per job.** `main.py` starts a Code Interpreter session before planning and stops it after the independent check, or when the job fails.
- **A narrow tool.** The coder still writes files in the job's working copy with `file_write`. `run_pytest` copies the working copy into the sandbox and runs pytest there. The model cannot run any other command in the sandbox.
- **An independent check that stays independent.** `verify.py` runs its test collection and final pytest in the same sandbox, so model-written code never runs in the Runtime container.
- **Sandbox network mode.** The sample uses the AWS-managed interpreter `aws.codeinterpreter.v1`. It fails early with a clear message if the sandbox lacks the test packages.

## Architecture

```
client (agentcore invoke --session-id <id>)
   │
   ▼
AgentCore Runtime session (one microVM per session ID)        ← holds the agent's credentials
   └─ main.py: background job
        ├─ sandbox_started ──────────────────────────────┐
        ├─ make_spec → orchestrator → coder              │   Code Interpreter session
        │                 └─ file_write (working copy)   │   (isolated, no credentials)
        │                 └─ run_pytest ── copy files ───►├─ repo/   pytest runs here
        ├─ reviewer                                      │
        ├─ verify.py: diff + collect + final pytest ────►│
        └─ sandbox_stopped ──────────────────────────────┘
```

| Component | Purpose |
|:----------|:--------|
| `sandbox.py` | `Sandbox`: starts and stops the session, checks packages, copies the working copy, runs pytest, reads the exit code |
| `tools/run_pytest.py` | The coder's tool, and `pytest_output()` for `verify.py`. Both call the job's sandbox. |
| `main.py` | Starts the sandbox first, so a broken sandbox fails the job before any model call |
| `agentcore/cdk/lib/cdk-stack.ts` | Grants the runtime's execution role the Code Interpreter actions |
| `scripts/probe_sandbox.py` | Checks what the sandbox provides, before you deploy |

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
| 4. `writeFiles` | `hi` | The service does not create parent directories. `sandbox.py` already creates them with `mkdir -p`. |
| 5. Packages | `pytest`, `fastapi` and `httpx` all `True` | Go to Step 1b |
| 6. pip | an install plan, not a network error | If it fails, sandbox network mode blocks pip |

### 1b. If packages are missing

In sandbox network mode the interpreter may not have `fastapi` or `httpx`, and pip may be blocked. The job then stops at `sandbox_started` with `the sandbox is missing ...`. Your choices:

- **Drop the target's imports.** Change `code_interpreter.packages` in `app/devagent/resources.yaml` to match what the target repo's tests import.
- **Use a custom interpreter with public network access.** Create it, put its ID in `code_interpreter.identifier`, and set `install_missing: true`. This leaves sandbox network mode.

### 2. Run it locally

`--skip-deploy` stops the CLI from creating a stack. The sandbox session is real, so this uses your credentials against AWS.

```bash
agentcore dev --skip-deploy
```

In a second terminal, start a job and stream its events:

```bash
curl -N -X POST localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: local-session-0000000000000000000001" \
  -d '{"action":"run","request":"Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"}'
```

You should see `sandbox_started` right after `accepted`, `tests_passed` or `tests_failed` events from the sandbox, and `sandbox_stopped` before `verified`.

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

The `sandbox_started` event carries the Code Interpreter session ID. The runtime's logs show the same job without any pytest process in the container.

```bash
agentcore logs --since 30m
```

## How it works

### Why `run_pytest` copies the files

The coder and the independent check both need the working copy, and `verify.py` compares it with the snapshot in the container. So the container keeps the working copy, and each test run replaces `repo/` in the sandbox with it: `rm -rf repo`, `mkdir -p`, then one `writeFiles` call. A file the coder deletes disappears in the sandbox too, and the model cannot forget to upload a change.

The session persists between runs, so anything installed with pip survives a retry.

### Reading the exit code

`executeCommand` runs inside `bash -c` with stderr merged into stdout, and the script's last line prints `[exit code N]`. `sandbox.py` reads that marker instead of relying on how the service reports exit codes. A run with no marker raises `SandboxError`, and the job fails with the output.

### New events

| Event | Meaning |
|:------|:--------|
| `sandbox_started` | The session ID, the interpreter identifier and the sandbox's Python version |
| `sandbox_stopped` | The session ended cleanly. `sandbox_stop_failed` carries the error. |

A job whose sandbox cannot start ends in `failed` before any model call, with the cause in `error`.

### What changed from `01-runtime`

| File | Difference |
|:-----|:-----------|
| `sandbox.py` | New |
| `tools/run_pytest.py` | Runs in the sandbox. The `cwd` argument and the Runtime launcher and `LD_LIBRARY_PATH` workarounds are gone. |
| `verify.py` | Calls `pytest_output(args)` without `cwd`, which now runs in the sandbox |
| `main.py` | Starts and stops the sandbox, and adds the `starting_sandbox` status |
| `settings.py`, `resources.yaml` | A `code_interpreter` section |
| `pyproject.toml`, `uv.lock` | `pytest`, `fastapi` and `httpx` removed. The container no longer runs tests. |
| `agentcore.json` | Project `codeinterpreterdevagent`, runtime `code_interpreter_devagent_sandbox`, so the stack does not collide with `01-runtime` |
| `cdk-stack.ts` | The Code Interpreter policy statement on the execution role |

## Experiments

**Experiment 1: a failure comes back from the sandbox.** Ask for a change that breaks a test, such as "Make GET /health return {\"status\": \"up\"}". Expect `tests_failed` with the `FAILED` line, then a fix on a later attempt in the same session.

**Experiment 2: an orphaned session.** Set `session_timeout_seconds` to `3600` in `resources.yaml`, then kill the local dev server in the middle of a job. In the console, find the session that never reached `sandbox_stopped`. A job that fails normally always stops its session.

**Experiment 3: the package gap.** Add a package the sandbox lacks, such as `requests`, to `code_interpreter.packages` and set `install_missing` to `false`. The job fails at `starting_sandbox` with `the sandbox is missing requests`. Then use a custom interpreter in public network mode, as in Step 1b, and compare.

## Configuration

| Setting | Where | Description |
|:--------|:------|:------------|
| `AWS_REGION` | environment | Required by `settings.py`. `main.py` falls back to `AWS_DEFAULT_REGION`, then the SDK's region. |
| `code_interpreter.identifier` | `app/devagent/resources.yaml` | `aws.codeinterpreter.v1` for the AWS-managed interpreter, or a custom interpreter's ID |
| `code_interpreter.session_timeout_seconds` | `app/devagent/resources.yaml` | How long a session lives. It is `1800`, and the SDK default is `900`. |
| `code_interpreter.python` | `app/devagent/resources.yaml` | The interpreter command in the sandbox, `python3` |
| `code_interpreter.packages` | `app/devagent/resources.yaml` | Modules that must import before the first test run |
| `code_interpreter.install_missing` | `app/devagent/resources.yaml` | Try `pip install` for a missing module. It is `true`. |
| `aws-targets.json` | `agentcore/` | The account and region to deploy to. Git ignores it. |

## Troubleshooting

### Issue: `AccessDeniedException` on `StartCodeInterpreterSession`
**Solution**: In Steps 1 and 2 your own credentials need the Code Interpreter actions listed in Prerequisites. On a deployed runtime the execution role needs them, and `cdk-stack.ts` adds them. Check that the deploy finished.

### Issue: `the sandbox is missing fastapi, httpx ...`
**Solution**: The interpreter lacks the packages and cannot install them. See Step 1b.

### Issue: `the sandbox gave no exit code for ...`
**Solution**: `bash` is missing, or the command was not run through a shell. Run the probe and read check 2.

### Issue: a job stays in `starting_sandbox`
**Solution**: Session start or the package check is slow. Read `agentcore logs --since 30m`. A pip install in a restricted network can wait for a timeout.

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
