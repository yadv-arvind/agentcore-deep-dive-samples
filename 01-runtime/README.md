# Spec-first coding agents on AgentCore Runtime

Host the planner, coder and reviewer agents from [`00-strands-spec-coder`](../00-strands-spec-coder/) on Amazon Bedrock AgentCore Runtime, so a long build runs as a background job behind a serverless endpoint. After each job, plain code compares the result with the original repo, because the agents' own report is not enough to trust.

| Information | Details |
|:------------|:--------|
| Type        | Feature demo |
| Language    | Python 3.12 locally, `PYTHON_3_14` on Runtime |
| Framework   | Strands Agents (`strands-agents` 1.62.x, `strands-agents-tools` below 0.9) |
| Model       | Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) on Amazon Bedrock |
| Components  | AgentCore Runtime |
| Complexity  | Intermediate |

> [!NOTE]
> The session and rollback experiments and the clean-up steps have not been run yet. Those sections say so.

## Overview

- **An entrypoint** (`app/devagent/main.py`) wraps the agents with the `bedrock-agentcore` SDK, so Runtime can call them over HTTP.
- **A background job per session.** A `start` call returns a job ID at once. `status` reads the job's progress, and `watch` streams it. A plain sentence runs the job and streams progress in the same response.
- **Streamed progress** as small JSON events: spec ready, task started, tests passed or failed, task reviewed.
- **An independent check.** After the agents finish, `verify.py` diffs the job's copy of the repo against the bundled snapshot, checks that no tests were lost, and runs pytest. Its `verified` event, not the agents' report, tells you whether the change is sound.

## Architecture

```
agentcore deploy:  agentcore.json → CDK → code zip (app/devagent/) → Runtime

client (agentcore invoke --session-id <id>)
   │
   ▼
AgentCore Runtime session (one microVM per session ID)
   └─ main.py: run | start | status | watch
        └─ background job
             make_spec → orchestrator → coder → run_pytest → reviewer
                                   └─ verify.py: diff + tests + final pytest
   app/devagent/workspace/shop-api   the snapshot the agents work on
```

| Component | Purpose |
|:----------|:--------|
| `main.py` | Runtime entrypoint and the job runner |
| `progress.py` | Turns tool calls into progress events |
| `verify.py` | Independent check of the job's result |
| `agents/`, `tools/` | The planner, coder, reviewer and orchestrator, and their tools |
| `workspace/shop-api/` | The repo the agents change, copied for each job |

## Prerequisites

| Requirement | Version | Install |
|:------------|:--------|:--------|
| Python | 3.12 (tested) | [python.org](https://www.python.org/downloads/) |
| uv | any current version | `brew install uv` or [astral.sh/uv](https://astral.sh/uv) |
| Node.js | v26.0.0 (tested) | [nodejs.org](https://nodejs.org/) |
| AgentCore CLI | 0.31.1 (tested) | `npm install -g @aws/agentcore@0.31.1` |
| AWS CLI | any current version | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |

- AWS credentials for the account you deploy to, and model access for Amazon Nova Pro in your region. The sample was run in `us-east-1`. The model ID is a US cross-region inference profile, so use a US region.
- A CDK-bootstrapped account and region. `agentcore deploy --dry-run` reports whether yours is.
- The root setup from the [repository README](../README.md): a `.venv` with `requirements.txt` installed.

Verify the tools and your credentials:

```bash
agentcore --version
aws sts get-caller-identity
```

## Quick start

### 1. Run it locally

Start the dev server from `01-runtime`. `--skip-deploy` stops the CLI from creating AWS resources first.

```bash
cd 01-runtime
export AWS_REGION=us-east-1
agentcore dev --skip-deploy
```

In a second terminal, start a job and stream its events. The session ID header becomes the job ID.

```bash
curl -N -X POST localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: local-session-0000000000000000000001" \
  -d '{"action":"run","request":"Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"}'
```

### 2. Set the deployment target

`aws-targets.json` holds your account ID, so git ignores it. Copy the example and edit it.

```bash
cp agentcore/aws-targets.example.json agentcore/aws-targets.json
# Edit agentcore/aws-targets.json: set account to your 12-digit account ID and region
```

### 3. Install the CDK dependencies

`agentcore deploy` builds the CDK project in `agentcore/cdk/`, and git ignores its `node_modules`.

```bash
cd agentcore/cdk
npm install
cd ../..
```

### 4. Deploy

```bash
# Check that the project builds and synthesizes. Nothing is created.
agentcore deploy --dry-run

# Create the stack
agentcore deploy -v
```

The deploy creates a CloudFormation stack named `AgentCore-devagentruntime-default` with three resources: the runtime's execution role, its policy, and the runtime `devagentruntime_devagent`. Confirm that it is ready:

```bash
agentcore status
```

### 5. Invoke it

Use a session ID of at least 33 characters, and reuse it to reach the same microVM.

```bash
agentcore invoke --session-id deploy-session-000000000000000000010 --stream "Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"
```

You should see events like these, trimmed:

```text
{"event": "accepted", "job_id": "deploy-session-000000000000000000010"}
{"event": "planning", ...}
{"event": "spec_ready", "tasks": ["Add GET /items/count endpoint", "Add test for GET /items/count endpoint"]}
{"event": "baseline", "tests": 6}
{"event": "task_started", "title": "Add GET /items/count endpoint"}
{"event": "tests_passed", "summary": "exit code 0: 7 passed, 2 warnings in 0.16s"}
{"event": "task_reviewed", "approved": true}
{"event": "changes", "diff": "--- a/app/main.py\n+++ b/app/main.py\n ..."}
{"event": "verified", "ok": true, "problems": [], "tests_before": 6, "tests_after": 7, ...}
{"event": "done", "verified": true}
```

## How it works

### Actions

Send these as JSON in the request body, or inside `{"prompt": "..."}`, which is how the CLI sends a prompt.

| Action | Behavior |
|:-------|:---------|
| `run` | Starts the job and streams events until it ends. A plain sentence means `run`. |
| `start` | Starts the job and returns `accepted` at once |
| `status` | Returns the job's snapshot, including its events and final summary |
| `watch` | Streams the job's events, from the first, until it ends |

A session runs one job at a time. A second `start` or `run` is rejected while one is running, and the job keeps going if the client disconnects. While a job runs, `/ping` reports `HealthyBusy`, so Runtime does not reclaim the session.

### Events

| Event | Emitted by | Meaning |
|:------|:-----------|:--------|
| `accepted`, `planning`, `spec_ready`, `done`, `failed` | `main.py` | Job lifecycle. `done` carries `verified`. |
| `baseline` | `main.py` | Tests found in the repo before the agents started |
| `task_started` | `progress.py` | The orchestrator called `implement_task`, with the task title |
| `tests_passed`, `tests_failed` | `progress.py` | `run_pytest` finished. A failure includes the `FAILED` and `E ...` lines. |
| `task_reviewed` | `progress.py` | The reviewer's verdict. A rejection includes its reason. |
| `final_review` | `main.py` | Only when the orchestrator skipped a review: the code ran the reviewer |
| `changes` | `main.py` | The unified diff against the snapshot, truncated to about 6,000 characters |
| `verified` | `verify.py` | `ok`, `problems`, changed files, test counts before and after, and the final pytest line |

### The independent check

The job works on a copy of `workspace/shop-api`, so the snapshot is the baseline. `verify.py` flags a change as a problem when:

- a file changed that the spec does not name
- a file lost more lines than it gained
- a test that existed before is gone
- the final pytest run fails
- no files changed

This exists because tests can pass after the agent rewrites the test file and drops the old tests. The diff and the test IDs catch that, and the agents' report does not.

### Run on Runtime's Python

`run_pytest` starts pytest as a child process. In Runtime, `sys.executable` is the binary in `bin/real/`, and the launcher next to it sets up its libraries, so the tool starts the launcher and also puts the folders holding `libpython` and `libffi` on `LD_LIBRARY_PATH`.

## Sample prompts

**Prompt**: "Add a GET /items/count endpoint that returns the number of items as {"count": n}, with a test"
**Expected behavior**: One new route above the parameterised item routes, one new test, `verified` with `ok: true` and 7 tests after.

**Prompt**: "Add a DELETE /items/{item_id} endpoint"
**Expected behavior**: The snapshot already has this endpoint, so expect a "verify" spec and a `verified` event with the problem `no files changed`.

## Configuration

| Setting | Where | Description |
|:--------|:------|:------------|
| `AWS_REGION` | environment | Required by `settings.py`. `main.py` falls back to `AWS_DEFAULT_REGION`, then the SDK's region, then `us-west-2`. |
| `PITWALL_RESOURCES` | environment | Path to the resources file. The default is `resources.yaml` in the current directory. |
| `model_id` | `app/devagent/resources.yaml` | The Bedrock model ID, `us.amazon.nova-pro-v1:0` |
| `runtimeVersion` | `agentcore/agentcore.json` | The Runtime's Python version, `PYTHON_3_14` |
| `idleRuntimeSessionTimeout` | `agentcore/agentcore.json` | Idle session timeout in seconds. It is `60` so the session-expiry experiment is quick. |
| `aws-targets.json` | `agentcore/` | The account and region to deploy to. Git ignores it. |
| `strands-agents`, `strands-agents-tools` | `app/devagent/pyproject.toml` | Capped below 1.63 and 0.9. See Troubleshooting. |

## Project structure

A deploy packages only `app/devagent/`. Git ignores `agentcore/aws-targets.json`, `agentcore/.cli/deployed-state.json` and the output of `agentcore package`.

| Path | Description |
|:-----|:------------|
| `agentcore/agentcore.json` | Runtime config: name, `CodeZip` build, `main.py` entrypoint, `PUBLIC` network, `HTTP` protocol and the idle timeout |
| `agentcore/aws-targets.example.json` | Example target with a placeholder account ID |
| `agentcore/cdk/` | The CDK project that `agentcore deploy` builds |
| `app/devagent/main.py` | The Runtime entrypoint and job runner |
| `app/devagent/progress.py` | `ProgressHook`, which turns tool calls into progress events |
| `app/devagent/verify.py` | The independent check |
| `app/devagent/pyproject.toml` | Dependencies, including the snapshot's test dependencies |
| `app/devagent/agents/`, `tools/` | Copies of the `00-strands-spec-coder` agents and tools, changed as listed below |
| `app/devagent/hooks.py` | Copy of the `ToolLog` hook. `main.py` does not use it. |
| `app/devagent/settings.py`, `resources.yaml` | Copies of the root files |
| `app/devagent/workspace/shop-api/` | Snapshot of [`yadv-arvind/shop-api`](https://github.com/yadv-arvind/shop-api) at commit `f406de9`: tracked files only |
| `app/devagent/workspace/SNAPSHOT.txt` | Where the snapshot came from |

### Differences from `00-strands-spec-coder`

The copies are no longer identical. A change in either place does not reach the other.

| File | Difference |
|:-----|:-----------|
| `agents/orchestrator.py` | Runs tool calls in order, so the review waits for the implementation |
| `agents/coder.py` | Prompt adds the FastAPI route-order rule |
| `agents/reviewer.py` | Prompt says the files are in the message and to start with the verdict |
| `tools/review_change.py` | Reads the named files and includes their contents in the reviewer's message |
| `tools/run_pytest.py` | Starts Runtime's launcher, sets `LD_LIBRARY_PATH`, drops OpenTelemetry log lines, and exposes `pytest_output()` |

## Troubleshooting

### Issue: `sh: tsc: command not found`
**Solution**: The CDK project's dependencies are not installed. Run `npm install` in `agentcore/cdk/`, then repeat the deploy.

### Issue: `Runtime initialization time exceeded. Please make sure that initialization completes in 30s.`
**Solution**: The entrypoint crashed while importing, so the server never started. Read the traceback with `agentcore logs --since 30m`. Here the cause was `ImportError: file_read was removed in v0.9.0`: an unpinned `strands-agents-tools` resolved to 0.9.0 in the deployed zip. The caps in `pyproject.toml` fix it. `agentcore package` ignores `uv.lock`, so the lockfile does not protect a deploy.

### Issue: `error while loading shared libraries: libpython3.14.so.1.0` or `libffi.so.6`
**Solution**: A child process started the interpreter binary directly, without the launcher that sets its library path. `tools/run_pytest.py` starts the launcher instead. To inspect the container, use `agentcore exec`, which does not run a shell, so pipes and redirects do not work.

### Issue: `tests_failed` with `assert 422 == 200` for a new route
**Solution**: FastAPI matches routes in declaration order, so `/items/count` after `/items/{item_id}` is read as an item ID. Declare fixed paths above parameterised ones. The coder prompt now says so.

### Issue: the reviewer rejects a change that the diff shows is correct
**Solution**: Trust the `verified` event and the `changes` diff. `review_change` now includes the files' contents in the reviewer's message, which removed the false rejections seen when it had to find the files itself.

### Issue: the `tests_failed` summary shows an OpenTelemetry log line
**Solution**: Runtime auto-instruments Python and adds log lines to the pytest output. `run_pytest` drops lines containing `trace_id=`, and the event summary looks for pytest's own summary line.

## Clean up

Not yet verified. The stack is a standard CloudFormation stack, so this removes it:

```bash
aws cloudformation delete-stack --stack-name AgentCore-devagentruntime-default --region <your-region>
```

This deletes the runtime, its execution role and the role's policy. The CDK bootstrap stack and the bootstrap bucket that holds the uploaded code zip remain, and so can the runtime's CloudWatch log group.

> [!WARNING]
> Deploying creates AWS resources through CDK, and model calls cost money. Run the clean-up when you finish.

## Next steps

1. Run the session experiments: state shared within a session ID, state lost after the 60-second idle timeout, and sessions isolated from each other.
2. Run the rollback experiment: deploy a broken version, then return to the previous one.
3. Verify the clean-up steps and the CLI's own removal command.

## Additional resources

- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Runtime IAM permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
- [AgentCore CLI on GitHub](https://github.com/aws/agentcore-cli)
- [bedrock-agentcore SDK for Python](https://github.com/aws/bedrock-agentcore-sdk-python)
