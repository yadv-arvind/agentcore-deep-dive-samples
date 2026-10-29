# Spec-first coding agents on AgentCore Runtime

A sample that hosts the planner, coder and reviewer agents from [`00-strands-spec-coder`](../00-strands-spec-coder/) on Amazon Bedrock AgentCore Runtime, so a long build runs as a background job behind a serverless endpoint. The Runtime entrypoint is not written yet: this folder holds the starting state.

| Information | Details |
|:------------|:--------|
| Type        | Feature demo |
| Language    | Python 3.12 |
| Framework   | Strands Agents (`strands-agents` 1.58.1) |
| Model       | Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) on Amazon Bedrock |
| Components  | AgentCore Runtime |
| Complexity  | Intermediate |

> [!NOTE]
> Nothing in this folder is deployed, and there is no AgentCore project or entrypoint yet. The sections below describe what the folder contains and what you add next.

## What you'll build

- **An entrypoint** that wraps the agents with the `bedrock-agentcore` SDK, so Runtime can call them over HTTP.
- **A background job.** A `start` call begins a build and returns a job ID at once. A `status` call reads the job's progress later, so a five-minute build does not hold a request open.
- **Streamed progress** as small JSON events, such as spec ready, task started, tests failed and tests passed.
- **Session and version behavior** that you check by experiment: state shared within a session ID, state lost after the idle timeout, and a rollback to an earlier version.

## Architecture

Planned. The entrypoint box does not exist yet.

```
client (agentcore invoke --session-id <id>)
   │
   ▼
AgentCore Runtime session (one microVM per session ID)
   └─ entrypoint
        ├─ start  → background job: make_spec → orchestrator → coder and reviewer
        └─ status → progress of the job
   workspace/shop-api   the snapshot the agents work on
```

## Prerequisites

| Requirement | Version | Install |
|:------------|:--------|:--------|
| Python | 3.12 (tested) | [python.org](https://www.python.org/downloads/) |
| uv | any current version | `brew install uv` or [astral.sh/uv](https://astral.sh/uv) |
| Node.js | 20 or later | [nodejs.org](https://nodejs.org/) |
| AgentCore CLI | 0.31.1 (tested) | `npm install -g @aws/agentcore` |
| AWS CLI | any current version | [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |

- AWS credentials that can invoke Amazon Nova Pro on Amazon Bedrock, and model access for it in a US region. The model ID is a US cross-region inference profile.
- The root setup from the [repository README](../README.md): a `.venv` with `requirements.txt` installed, and a `.env` that sets `AWS_REGION`.

Verify the tools and your credentials:

```bash
agentcore --version
aws sts get-caller-identity
```

## Check the starting state

Run this from the repository root with the virtual environment active. It confirms that the copied agents import from inside this folder.

```bash
cd 01-runtime
PYTHONPATH=. PITWALL_RESOURCES=resources.yaml python -c "from agents.orchestrator import orchestrator; print(orchestrator.tool_names)"
```

You should see:

```text
['implement_task', 'review_change']
```

## Configuration

| Setting | Where | Description |
|:--------|:------|:------------|
| `AWS_REGION` | `.env` in the repository root | Required. `settings.py` exits if it is missing. How it reaches a deployed runtime is not set up yet. |
| `PITWALL_RESOURCES` | environment | Path to the resources file. The default is `resources.yaml` in the current directory. |
| `model_id` | `resources.yaml` | The Bedrock model ID, `us.amazon.nova-pro-v1:0` |

## Project structure

| Path | Description |
|:-----|:------------|
| `agents/` | Copy of `00-strands-spec-coder/agents`: planner, coder, reviewer, orchestrator, the `Spec` models and the shared Bedrock model |
| `tools/` | Copy of `00-strands-spec-coder/tools`: `implement_task`, `review_change` and `run_pytest` |
| `hooks.py` | Copy of the `ToolLog` hook that prints each tool call |
| `settings.py` | Copy of the root file. It exposes `region` and `model_id`. |
| `resources.yaml` | Copy of the root file. It holds `model_id`. |
| `requirements.txt` | Copy of the root file |
| `workspace/shop-api/` | Snapshot of the repo the agents work on |
| `workspace/SNAPSHOT.txt` | Where the snapshot came from |

The copies make this folder deployable on its own, because a deploy packages only the project folder. They match the originals today. When you change a shared file in one place, change the other copy too.

## Workspace snapshot

A Runtime session has no access to your local repositories, so the agents need a repo inside the deployment. `workspace/shop-api/` is a `git archive` of [`yadv-arvind/shop-api`](https://github.com/yadv-arvind/shop-api) at commit `f406de9`: tracked files only, with no `.git` and no `.venv`.

The snapshot's tests need `fastapi` and `httpx`. `requirements.txt` does not list them, or `bedrock-agentcore`, yet.

## Next steps

1. Add `bedrock-agentcore` and the snapshot's test dependencies to `requirements.txt`.
2. Write the entrypoint and run it locally with `agentcore dev`.
3. Deploy with `agentcore deploy` and call it with `agentcore invoke --session-id <id> --stream`.
4. Run the session and rollback experiments.

> [!WARNING]
> Deploying creates AWS resources through CDK, and they cost money. The removal steps are added here once the deploy works.

## Additional resources

- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
- [Runtime IAM permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
- [AgentCore CLI on GitHub](https://github.com/aws/agentcore-cli)
- [bedrock-agentcore SDK for Python](https://github.com/aws/bedrock-agentcore-sdk-python)
