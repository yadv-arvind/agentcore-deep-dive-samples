"""Find out what the Code Interpreter sandbox gives you, before you deploy anything.

Starts one session on the interpreter named in app/devagent/resources.yaml (the AWS-managed one by default),
prints the raw shape of a command response, and checks each thing the sample relies on:
a shell, writing files, Python, the test packages, and pip. It stops the session when it ends.

Run from 02-code-interpreter:
    uv run --no-project --with "bedrock-agentcore>=1.18.1" --with pyyaml python scripts/probe_sandbox.py
"""
import json
import os
import shlex
from pathlib import Path

import yaml
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

cfg = yaml.safe_load((Path(__file__).parent.parent / "app" / "devagent" / "resources.yaml").read_text())["code_interpreter"]
region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def events(response: dict) -> list:
    return [event for event in response.get("stream", [])]


def text_of(response: dict) -> str:
    parts = []
    for event in events(response):
        result = event.get("result") or {}
        structured = result.get("structuredContent") or {}
        streams = [str(structured[k]) for k in ("stdout", "stderr") if structured.get(k)]
        parts += streams or [str(b.get("text", "")) for b in result.get("content") or [] if isinstance(b, dict)]
    return "\n".join(parts).strip()


def sh(client: CodeInterpreter, script: str) -> str:
    return text_of(client.invoke("executeCommand", {"command": f"bash -c {shlex.quote('exec 2>&1; ' + script)}"}))


client = CodeInterpreter(region)
session_id = client.start(identifier=cfg["identifier"], session_timeout_seconds=300)
print(f"region={region} interpreter={cfg['identifier']} session={session_id}\n")
try:
    raw = client.invoke("executeCommand", {"command": "echo hello; echo oops 1>&2; exit 3"})
    print("1. Raw executeCommand response events (check the field names the sample reads):")
    print(json.dumps(events(raw), indent=2, default=str)[:1500], "\n")

    print("2. bash and exit codes:", sh(client, "echo ok; false; echo exit=$?"))
    print("3. Python:", sh(client, f"{cfg['python']} --version"))

    client.invoke("writeFiles", {"content": [{"path": "probe/sub/hello.txt", "text": "hi"}]})
    print("4. writeFiles into a new subdirectory:", sh(client, "cat probe/sub/hello.txt"))

    check = ("import importlib.util as u,sys; print({m: u.find_spec(m) is not None for m in sys.argv[1:]})")
    print("5. Test packages importable:", sh(client, f"{cfg['python']} -c {shlex.quote(check)} {shlex.join(cfg['packages'])}"))

    print("6. pip install (sandbox network mode may refuse):")
    print("  ", sh(client, f"{cfg['python']} -m pip install -q --dry-run fastapi 2>&1 | tail -3"))
finally:
    client.stop()
    print("\nSession stopped.")
