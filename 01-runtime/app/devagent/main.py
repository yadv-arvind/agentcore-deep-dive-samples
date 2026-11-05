"""AgentCore Runtime entrypoint: run the spec-first coding agents as a background job.

Payload (the CLI sends a prompt string, so JSON goes inside "prompt"; a plain dict works too):
    {"action": "start",  "request": "Add a DELETE /items/{item_id} endpoint"}   returns a job ID at once
    {"action": "status"}                                                         returns the job's progress
    {"action": "watch"}                                                          streams events until the job ends
A job is keyed by the session ID, so each session runs one job at a time.
"""
import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import boto3

# settings.py needs AWS_REGION. Runtime and local dev may not set it, so fall back to the SDK's region.
os.environ.setdefault("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION") or boto3.Session().region_name or "us-west-2")
# file_write asks for confirmation before each write, and nobody can answer inside a container.
# This is safe here because the agents write only to a throwaway copy of the workspace.
os.environ.setdefault("BYPASS_TOOL_CONSENT", "true")

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents.coder import coder
from agents.orchestrator import orchestrator
from agents.planner import make_spec, planner
from agents.reviewer import reviewer
from progress import ProgressHook

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


def _list_files(root: Path) -> str:
    skip = {".git", ".venv", "__pycache__", ".pytest_cache"}
    names = [str(p.relative_to(root)) for p in root.rglob("*")
             if p.is_file() and not skip & set(p.relative_to(root).parts) and p.name != ".DS_Store"]
    return "\n".join(sorted(names))


def _run_job(job: dict, request: str) -> None:
    ping_task = app.add_async_task("devagent_build")        # /ping reports HealthyBusy until this completes
    _current["job"] = job
    try:
        repo = Path(tempfile.mkdtemp(prefix="job-")) / "shop-api"
        shutil.copytree(WORKSPACE, repo)
        os.chdir(repo)                                       # the agents use relative paths
        job["status"] = "planning"
        _emit(job, "planning")
        spec = make_spec(
            f"{request}\n\nThe current directory is the repository. Its files, as relative paths:\n"
            f"{_list_files(repo)}\n\nRead the files the change touches with exactly these relative paths before planning."
        )
        if not spec.tasks:
            raise RuntimeError("The planner returned a spec with no tasks.")
        _emit(job, "spec_ready", tasks=[t.title for t in spec.tasks])
        job["status"] = "coding"
        result = orchestrator(
            f"Repository: {repo}\n\nSpec:\n{spec.model_dump_json(indent=2)}\n\n"
            "Implement every task in the spec, reviewing each one, and report the outcome."
        )
        job["summary"] = str(result)
        job["status"] = "done"
        _emit(job, "done")
    except Exception as exc:                                 # report any failure through status
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        _emit(job, "failed", error=job["error"])
    finally:
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
        return {"action": "start", "request": prompt}        # a plain sentence means start
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


@app.entrypoint
async def invoke(payload, context):
    request = _parse(payload)
    job_id = getattr(context, "session_id", None) or "local"
    action = request.get("action", "start")

    if action == "start":
        existing = JOBS.get(job_id)
        if existing and existing["status"] in ("starting", "planning", "coding"):
            yield json.dumps({"event": "rejected", "reason": "a job is already running", "job_id": job_id})
            return
        text = request.get("request")
        if not isinstance(text, str) or not text.strip():
            yield json.dumps({"event": "rejected", "reason": 'start needs a non-empty "request"'})
            return
        job = {"job_id": job_id, "status": "starting", "events": []}
        JOBS[job_id] = job
        threading.Thread(target=_run_job, args=(job, text), daemon=True).start()
        yield json.dumps({"event": "accepted", "job_id": job_id})
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
