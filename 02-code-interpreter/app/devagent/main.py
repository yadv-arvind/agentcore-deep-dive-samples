"""AgentCore Runtime entrypoint: run the spec-first coding agents as a background job.

The repository lives in an AgentCore Code Interpreter sandbox, one session per job: sandbox_started and sandbox_stopped
events mark its life. This container only hosts the agents and the check, and never holds a copy of the repo.

Payload (the CLI sends a prompt string, so JSON goes inside "prompt"; a plain dict works too):
    {"action": "start",  "request": "Add a DELETE /items/{item_id} endpoint"}   returns a job ID at once
    {"action": "run",    "request": "..."}                                       starts the job and streams events until it ends
    {"action": "status"}                                                         returns the job's progress
    {"action": "watch"}                                                          streams events until the job ends
A plain sentence means run, so a chat UI shows progress. A job is keyed by the session ID, so each session
runs one job at a time, and the job keeps going if the client disconnects: reconnect with watch.
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path

import boto3

# settings.py needs AWS_REGION. Runtime and local dev may not set it, so fall back to the SDK's region.
os.environ.setdefault("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION") or boto3.Session().region_name or "us-west-2")

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents.coder import coder
from agents.orchestrator import orchestrator
from agents.planner import make_spec, planner
from agents.reviewer import reviewer
import sandbox
from progress import ProgressHook
from sandbox import Sandbox
from tools.review_change import review_change
from verify import check_spec_paths, collect_tests, verify

app = BedrockAgentCoreApp()
log = app.logger

WORKSPACE = Path(__file__).parent / "workspace" / "shop-api"
JOBS: dict[str, dict] = {}          # lives as long as the session's microVM
_current = {"job": None}            # the job the progress hook writes to


def _emit(job: dict, name: str, **fields) -> None:
    job["events"].append({"event": name, "at": round(time.time(), 1), **fields})


# One hook on each agent that runs tools. It reports to whichever job is running.
_progress = ProgressHook(lambda name, **fields: _emit(_current["job"], name, **fields) if _current["job"] else None)
for _agent in (orchestrator, coder, reviewer):
    _agent.hooks.add_hook(_progress)


def _run_job(job: dict, request: str) -> None:
    ping_task = app.add_async_task("devagent_build")        # /ping reports HealthyBusy until this completes
    _current["job"] = job
    box = None
    try:
        box = Sandbox(emit=lambda name, **fields: _emit(job, name, **fields))
        sandbox.activate(box)
        job["status"] = "starting_sandbox"
        box.start()                                          # fail before any model call if the sandbox is unusable
        _emit(job, "snapshot_loaded", files=box.load(WORKSPACE))   # the only copy of the repo is now in the sandbox
        files = box.list_files()
        job["status"] = "planning"
        _emit(job, "planning")
        spec = make_spec(
            f"{request}\n\nThe repository's files, as relative paths from its root:\n"
            f"{chr(10).join(files)}\n\nRead the files the change touches with exactly these relative paths before planning."
        )
        if not spec.tasks:
            raise RuntimeError("The planner returned a spec with no tasks.")
        invented = check_spec_paths(spec, files)
        if invented:
            raise RuntimeError("The spec refers to paths that do not exist, so the plan is probably invented: " + "; ".join(invented))
        _emit(job, "spec_ready", tasks=[t.title for t in spec.tasks])
        tests_before = collect_tests()
        _emit(job, "baseline", tests=len(tests_before))
        job["status"] = "coding"
        spec_json = spec.model_dump_json(indent=2)
        result = orchestrator(
            f"Spec:\n{spec_json}\n\n"
            "Implement every task in the spec, then call review_change for that task, whatever the test result. "
            "Report the outcome."
        )
        job["summary"] = str(result)
        job["status"] = "verifying"
        report = verify(WORKSPACE, box, spec, tests_before)
        reviews = sum(1 for e in job["events"] if e["event"] == "task_reviewed")
        if reviews < len(spec.tasks):                        # the orchestrator skipped a review: do it from code
            verdict = str(review_change(spec_json, ", ".join(report["files"]) or "none"))
            _emit(job, "final_review", approved=verdict.strip().startswith("APPROVE"), reason=verdict[:400])
        box.close()                                          # everything that needs the repo is done
        _emit(job, "changes", diff=report.pop("diff"))
        _emit(job, "verified", **report)
        job["verified"] = report["ok"]
        job["status"] = "done"
        _emit(job, "done", verified=report["ok"])
    except Exception as exc:                                 # report any failure through status
        if box:
            box.close()
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        _emit(job, "failed", error=job["error"])
    finally:
        if box:
            box.close()                                      # a no-op when it is already stopped
        sandbox.activate(None)
        app.complete_async_task(ping_task)


def _parse(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        try:
            parsed = json.loads(prompt)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
        return {"action": "run", "request": prompt}          # a plain sentence means run
    return payload


def _view(job: dict | None) -> dict:
    if job is None:
        return {"status": "unknown", "events": []}
    return dict(job)


async def _follow(job: dict):
    sent = 0
    while True:
        while sent < len(job["events"]):
            yield json.dumps(job["events"][sent])
            sent += 1
        if job["status"] in ("done", "failed"):
            return
        await asyncio.sleep(1)


def _begin(job_id: str, text) -> tuple[dict | None, dict | None]:
    """Start a job for this session. Returns (job, None), or (None, rejection)."""
    existing = JOBS.get(job_id)
    if existing and existing["status"] in ("starting", "starting_sandbox", "planning", "coding", "verifying"):
        return None, {"event": "rejected", "reason": "a job is already running, send watch to follow it", "job_id": job_id}
    if not isinstance(text, str) or not text.strip():
        return None, {"event": "rejected", "reason": 'start and run need a non-empty "request"'}
    job = {"job_id": job_id, "status": "starting", "events": []}
    JOBS[job_id] = job
    threading.Thread(target=_run_job, args=(job, text), daemon=True).start()
    return job, None


@app.entrypoint
async def invoke(payload, context):
    request = _parse(payload)
    job_id = getattr(context, "session_id", None) or "local"
    action = request.get("action", "start")

    if action in ("start", "run"):
        job, rejection = _begin(job_id, request.get("request"))
        if rejection:
            yield json.dumps(rejection)
            return
        yield json.dumps({"event": "accepted", "job_id": job_id})
        if action == "run":
            async for line in _follow(job):
                yield line
    elif action == "status":
        yield json.dumps(_view(JOBS.get(job_id)))
    elif action == "watch":
        job = JOBS.get(job_id)
        if job is None:
            yield json.dumps({"status": "unknown", "events": []})
            return
        async for line in _follow(job):
            yield line
    else:
        yield json.dumps({"event": "rejected", "reason": f"unknown action {action!r}"})


if __name__ == "__main__":
    app.run()
