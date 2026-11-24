# Inspecting a deployed agent

Where to find the [`01-runtime`](../README.md) agent in the AWS console after `agentcore deploy`, and how to look inside a live session.

## Find your agent in the AWS console

The deploy creates one runtime, `runtimedevagent_runtime_devagent`, plus a role and a policy. They show up in four services. Sign in to the account and region from `aws-targets.json` and select that region in the console's region menu first, because every list below is empty in the wrong region.

The AWS documentation names the AgentCore console pages but not every tab, so steps marked "not documented" are the ones the docs do not describe.

### 1. The runtime in the AgentCore console

1. Open the [Agent Runtime page](https://console.aws.amazon.com/bedrock-agentcore/agents) in the Amazon Bedrock AgentCore console.
2. In the **Runtime agents** list, find `runtimedevagent_runtime_devagent`. Its ID is the `ApplicationAgent...RuntimeIdOutput...` value printed by `agentcore deploy`, and `agentcore status` shows the same agent with its ARN.
3. Open it. The documentation names a **Tracing** pane with an **Edit** button, a **Log delivery** pane with an **Add** menu, and an **Identity** tab on this page.

Not documented: where the console shows the versions, the `DEFAULT` endpoint and the sessions. The API lists versions and endpoints with `ListAgentRuntimeVersions` and `ListAgentRuntimeEndpoints`. Every deploy that changes the code adds a version, and the `DEFAULT` endpoint follows the latest.

### 2. The stack in CloudFormation

1. Open **CloudFormation** and choose **Stacks**.
2. Select `AgentCore-runtimedevagent-default`.
3. Open the **Resources** tab. You should see three resources: the execution role, its policy, and the runtime.
4. Open the **Outputs** tab for the runtime ID, the runtime ARN and the role ARN.

### 3. The execution role in IAM

1. Open **IAM**, then **Roles**.
2. Search for `AgentCore-runtimedevagent`. The full name is in the role ARN under **Outputs**.
3. Open the role. The trust policy allows `bedrock-agentcore.amazonaws.com`, and the permissions cover model invocation, logs, X-Ray tracing and the configuration-bundle actions the CLI template adds.

### 4. Logs in CloudWatch

1. Open **CloudWatch**, then **Logs**, then **Log groups**.
2. Search for `/aws/bedrock-agentcore/runtimes/`. The group for this runtime is `/aws/bedrock-agentcore/runtimes/<runtime-id>-DEFAULT`.
3. Open it. The docs say it holds the service logs, the spans and standard output. The same lines appear in the terminal with `agentcore logs --since 30m`.

### 5. Sessions and traces

Traces are how you see one session's tool calls, including the planner, coder and reviewer as separate spans.

1. Turn on Transaction Search once per account and region: in **CloudWatch**, expand **Application Signals (APM)**, choose **Transaction search**, choose **Enable Transaction Search**, tick the box to ingest spans as structured logs, and choose **Save**. The deploy output said it takes about 10 minutes before traces show up.
2. Open the [AgentCore observability page](https://console.aws.amazon.com/bedrock-agentcore/observability), or the generative AI observability page in CloudWatch, and filter by your runtime. The documentation says session metrics appear on both.

Not documented: the exact tab names for sessions and traces on those pages, and a console view of individual microVMs. A microVM is not a listed resource. To look inside one, use `agentcore exec`, below.

## Inspecting a session

The console lists the runtime, its versions and endpoints, but not the microVMs behind them and not the files the agents write. Each job edits a copy of the repo in a temp folder inside the session's microVM, and that folder is deleted with the session. `agentcore exec` runs a command inside a live session, so you can look at the copy while the session exists.

Start a job, then run the commands within 60 seconds of your last call to that session. `exec` does not run a shell, so pipes, redirects and variables do not work.

```bash
agentcore invoke --session-id peek-session-000000000000000000000001 '{"action":"start","request":"Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"}'
```

Find the job folder. Each job creates `/tmp/job-<random>/shop-api`.

```bash
agentcore exec --session-id peek-session-000000000000000000000001 "find /tmp -maxdepth 2 -name job-*"
```

List the files in it:

```bash
agentcore exec --session-id peek-session-000000000000000000000001 "ls -R /tmp/<job-folder>/shop-api"
```

You should see:

```text
/tmp/job-nkil2en7/shop-api:
app
pyproject.toml
tests
uv.lock

/tmp/job-nkil2en7/shop-api/app:
__init__.py
main.py

/tmp/job-nkil2en7/shop-api/tests:
test_items.py
```

That is the repo the agents edit, with the same layout as `workspace/shop-api/`. The `changes` event holds the diff, because the folder does not outlive the session.

The agents are not separate AWS resources. The planner, coder, reviewer and orchestrator are `Agent` objects in one process in one runtime, so they appear separately only in traces, in CloudWatch GenAI observability.
