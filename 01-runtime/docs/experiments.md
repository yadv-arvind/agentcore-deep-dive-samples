# Session and rollback experiments

Experiments for the deployed [`01-runtime`](../README.md) sample: how sessions keep state, when they lose it, and how versions and endpoints behave when a deploy breaks.

## Session experiments

These show that a session ID selects one microVM, that its memory lives only as long as the microVM, and that the idle timeout (60 seconds here) destroys it. Use session IDs of 33 or more characters. The expected results come from the code and the configuration.

### Experiment 1: state is shared within a session

Start a job, then ask for its status with the same session ID.

```bash
agentcore invoke --session-id exp-session-a-0000000000000000000001 '{"action":"start","request":"Add a GET /items/count endpoint that returns the number of items as {\"count\": n}, with a test"}'
agentcore invoke --session-id exp-session-a-0000000000000000000001 '{"action":"status"}'
agentcore invoke --session-id exp-session-a-0000000000000000000001 '{"action":"start","request":"another job"}'
```

Expect the same `job_id` and a growing `events` list from `status`, and a `rejected` event with "a job is already running" from the second `start`.

### Experiment 2: sessions are isolated

```bash
agentcore invoke --session-id exp-session-b-0000000000000000000001 '{"action":"status"}'
```

Expect `{"status": "unknown", "events": []}`. A new session ID starts a new microVM with empty memory, and the first call is slower because of the cold start.

### Experiment 3: state is lost after the idle timeout

Every request restarts the 60-second clock, so make one last call and then wait without calling.

```bash
agentcore invoke --session-id exp-session-a-0000000000000000000001 '{"action":"status"}'
sleep 90
time agentcore invoke --session-id exp-session-a-0000000000000000000001 '{"action":"status"}'
```

Expect `{"status": "unknown", "events": []}` and a slower response than before the wait. The microVM was destroyed, so the `JOBS` dictionary in `main.py` went with it. A running job does not count as idle, because `/ping` reports `HealthyBusy`.

> [!NOTE]
> Anything that must outlive a session, such as a finished job's diff, needs storage outside the microVM. This sample returns the diff in the event stream instead.

## Rollback experiment

Every deploy that changes the code creates a new runtime version, and versions do not change once created. An endpoint is a named alias for one version. The default endpoint follows the latest version, so a bad deploy breaks it. `agentcore invoke` in CLI 0.31.1 has no option to choose an endpoint, so the pinned endpoint is called through the SDK.

| Step | Action | Expected |
|:-----|:-------|:---------|
| 1 | Find the latest version number `N` with `agentcore status --json` | The `devagent` runtime and its version |
| 2 | Pin it: `agentcore add runtime-endpoint --runtime runtime_devagent --endpoint stable --version <N>`, then `agentcore deploy -y` | `agentcore status --type runtime-endpoint` lists `stable` |
| 3 | Add `raise RuntimeError("broken on purpose")` near the top of `main.py`, then `agentcore deploy -y` | A new version, `N+1`, and the default endpoint follows it |
| 4 | Invoke the default endpoint with `agentcore invoke` | `Runtime initialization time exceeded`, the error described in [Troubleshooting](../README.md#troubleshooting) |
| 5 | Invoke `stable` through boto3 (below) | Works: the old version still serves traffic |
| 6 | `git checkout -- app/devagent/main.py`, then `agentcore deploy -y` | A new version, `N+2`, with the good code. The default endpoint works again. |

Call a pinned endpoint with the `qualifier` argument:

```python
import boto3, json, os

client = boto3.client("bedrock-agentcore", region_name="us-east-1")
resp = client.invoke_agent_runtime(
    agentRuntimeArn=os.environ["RUNTIME_ARN"],
    qualifier="stable",
    runtimeSessionId="rollback-session-000000000000000000002",
    payload=json.dumps({"action": "status"}).encode(),
)
print(resp["response"].read().decode())
```

A rollback in this setup is a new version that holds old code, not a switch back to `N`. Pinning an endpoint to a known-good version gives clients a stable target while the default endpoint is broken.

After the experiment, revert `agentcore/agentcore.json`, which gains an `endpoints` block, and redeploy so AWS drops the endpoint.
