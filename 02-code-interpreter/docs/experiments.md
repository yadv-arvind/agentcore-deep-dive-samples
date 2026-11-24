# Sandbox experiments

Experiments for the deployed [`02-code-interpreter`](../README.md) sample: what a failing test looks like from the sandbox, what an orphaned session looks like, and what happens when the sandbox lacks a package. Run them after the deploy works.

## Experiment 1: a failure comes back from the sandbox

Ask for a change that breaks a test. Expect `tests_failed` with pytest's assertion lines, then a fix on a later attempt in the same session. This run is on the deployed runtime:

```bash
agentcore invoke --session-id sandbox-session-00000000000000000002 --stream "Make GET /health return {\"status\": \"up\"}"
```

You should see events like these, trimmed. The run took about 42 seconds:

```text
{"event": "accepted", "job_id": "sandbox-session-00000000000000000002"}
{"event": "sandbox_started", "at": 1795534885.6, "session_id": "01M873G22XM3G14MR5EAP5EG6N", "identifier": "aws.codeinterpreter.v1", "python": "Python 3.12.13", "pytest": "pytest 9.2.0"}
{"event": "snapshot_loaded", "at": 1795534885.8, "files": 6}
{"event": "planning", "at": 1795534886.0}
{"event": "spec_ready", "at": 1795534890.8, "tasks": ["Update health endpoint to return {\"status\": \"up\"}", "Update test for health endpoint to assert {\"status\": \"up\"}"]}
{"event": "baseline", "at": 1795534892.0, "tests": 6}
{"event": "task_started", "at": 1795534893.2, "title": "Update health endpoint to return {\"status\": \"up\"}"}
{"event": "file_written", "at": 1795534899.5, "path": "app/main.py"}
{"event": "tests_failed", "at": 1795534901.2, "summary": "exit code 1: 1 failed, 5 passed, 2 warnings in 0.37s", "failures": ["E       AssertionError: assert {'status': 'up'} == {'status': 'ok'}", "E         Differing items:", "E         {'status': 'up'} != {'status': 'ok'}", "E         Use -v to get more diff"]}
{"event": "file_written", "at": 1795534909.6, "path": "tests/test_items.py"}
{"event": "tests_passed", "at": 1795534911.3, "summary": "exit code 0: 6 passed, 2 warnings in 0.29s"}
{"event": "task_reviewed", "at": 1795534916.6, "approved": true}
{"event": "task_started", "at": 1795534917.8, "title": "Update test for health endpoint to assert {\"status\": \"up\"}"}
{"event": "task_reviewed", "at": 1795534924.1, "approved": true}
{"event": "sandbox_stopped", "at": 1795534927.3, "session_id": "01M873G22XM3G14MR5EAP5EG6N"}
{"event": "changes", "at": 1795534927.3, "diff": "--- a/app/main.py\n+++ b/app/main.py\n@@ -20,5 +20,5 @@ ..."}
{"event": "verified", "at": 1795534927.3, "ok": true, "problems": [], "files": {"app/main.py": {"added": 1, "deleted": 1}, "tests/test_items.py": {"added": 1, "deleted": 1}}, "tests_before": 6, "tests_after": 6, "pytest": "exit code 0: 6 passed, 2 warnings in 0.30s"}
{"event": "done", "at": 1795534927.3, "verified": true}
```

What the output shows:

- **A failure from the sandbox.** After the coder changed `app/main.py`, `run_pytest` ran in the sandbox and returned `1 failed, 5 passed`. The `failures` field holds the first four pytest lines that start with `E`. The `FAILED` summary line is cut off by that limit of four.
- **A fix in the same session.** The existing test asserted the old response, so the coder updated it and the next run passed. The sandbox session and its files carried over between the two runs.
- **The check.** `verified` reports `tests_before` and `tests_after` both as 6, because no test was added or removed, and each of the two changed files gained one line and lost one.
- **Two tasks again.** The planner split the work into a code task and a test task. The first coder run changed both files, so the second task made no changes and ran no tests.

## Experiment 2: an orphaned session

Set `session_timeout_seconds` to `3600` in `app/devagent/resources.yaml`, then kill the local dev server in the middle of a job. In the console, find the session that never reached `sandbox_stopped`. A job that fails normally always stops its session.

## Experiment 3: the package gap

Add a package the sandbox lacks, such as `requests`, to `code_interpreter.packages`. The job fails at `starting_sandbox` with `the sandbox is missing requests`. Then use a custom interpreter in public network mode with `install_missing: true`, as in [Step 1b](../README.md#1b-if-fastapi-or-httpx-are-missing), and compare.
