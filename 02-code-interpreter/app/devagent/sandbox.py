"""The build sandbox: an AgentCore Code Interpreter session that runs the job's tests.

Model-written code never runs in the Runtime container, which holds the agent's credentials. The job keeps
its working copy of the repo in the container (the agents read and write it with file_read and file_write),
and every test run copies that working copy into the sandbox and runs pytest there.

One Sandbox per job. The session keeps its filesystem and installed packages between runs, and close()
stops it, because an idle session still bills.
"""
import re
import shlex
from pathlib import Path

from botocore.exceptions import ReadTimeoutError
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

from settings import settings

REPO_DIR = "repo"                     # where the working copy lands, relative to the sandbox's working directory
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".so"}
MAX_FILE_BYTES = 200_000
EXIT_MARKER = re.compile(r"^\[exit code (\d+)\]\s*$", re.MULTILINE)


class SandboxError(RuntimeError):
    """The sandbox could not start, was missing something, or answered in a way this code does not expect."""


def _read_response(response: dict) -> tuple[bool, str]:
    """(is_error, text) from an invoke_code_interpreter response, which is a stream of result events."""
    is_error, parts = False, []
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            continue
        is_error = is_error or bool(result.get("isError"))
        structured = result.get("structuredContent") or {}
        streams = [str(structured[key]) for key in ("stdout", "stderr") if structured.get(key)]
        if streams:
            parts.extend(streams)
        else:
            parts.extend(str(block.get("text", "")) for block in result.get("content") or [] if isinstance(block, dict))
    return is_error, "\n".join(part for part in parts if part)


class Sandbox:
    def __init__(self, repo: Path, emit=None):
        self.repo = Path(repo)
        self.emit = emit or (lambda name, **fields: None)
        self.client: CodeInterpreter | None = None
        self.session_id: str | None = None

    # -- lifecycle ---------------------------------------------------------------------------------------

    def start(self) -> None:
        cfg = settings.code_interpreter
        self.client = CodeInterpreter(settings.region)
        try:
            self.session_id = self.client.start(identifier=cfg.identifier, session_timeout_seconds=cfg.session_timeout_seconds)
        except Exception as exc:
            self.client = None
            raise SandboxError(f"could not start a Code Interpreter session ({cfg.identifier}): {exc}") from exc
        self._ensure_packages()
        _, python_version = self._shell(f"{cfg.python} --version")
        self.emit("sandbox_started", session_id=self.session_id, identifier=cfg.identifier, python=python_version.strip())

    def close(self) -> None:
        """Stop the session. Safe to call more than once, and never raises."""
        if self.client is None:
            return
        client, session_id, self.client = self.client, self.session_id, None
        try:
            client.stop()
        except Exception as exc:
            self.emit("sandbox_stop_failed", session_id=session_id, error=f"{type(exc).__name__}: {exc}")
        else:
            self.emit("sandbox_stopped", session_id=session_id)

    # -- running things ----------------------------------------------------------------------------------

    def _invoke(self, method: str, arguments: dict) -> str:
        if self.client is None:
            raise SandboxError("the sandbox session is not running")
        is_error, text = _read_response(self.client.invoke(method, arguments))
        if is_error:
            raise SandboxError(f"{method} failed: {text[-1000:]}")
        return text

    def _shell(self, script: str) -> tuple[int, str]:
        """Run a shell script in the sandbox. Returns (exit code, output).

        The exit code is read from a marker that the script prints last, so it does not depend on how the
        service reports exit codes.
        """
        wrapped = f'exec 2>&1\n{script}\necho "[exit code $?]"'          # one stream, so the marker is the last line
        text = self._invoke("executeCommand", {"command": f"bash -c {shlex.quote(wrapped)}"})
        matches = list(EXIT_MARKER.finditer(text))
        if not matches:
            raise SandboxError(f"the sandbox gave no exit code for `{script[:80]}`. Output: {text[-500:]}")
        marker = matches[-1]
        return int(marker.group(1)), (text[: marker.start()] + text[marker.end():]).strip()

    def _ensure_packages(self) -> None:
        """Check that the test dependencies are importable. Install the missing ones only if the config allows it."""
        cfg = settings.code_interpreter
        check = (f"{cfg.python} -c \"import importlib.util as u,sys; print(' '.join(m for m in sys.argv[1:] "
                 f"if u.find_spec(m) is None))\" {shlex.join(cfg.packages)}")
        _, missing_out = self._shell(check)
        missing = missing_out.split()
        if missing and cfg.install_missing:
            self._shell(f"{cfg.python} -m pip install -q {shlex.join(missing)}")
            _, missing_out = self._shell(check)
            missing = missing_out.split()
        if missing:
            raise SandboxError(
                f"the sandbox is missing {', '.join(missing)}, and it has no way to install them "
                f"(code_interpreter.install_missing is {cfg.install_missing}). Use a custom interpreter with "
                "PUBLIC network mode, or change code_interpreter.packages in resources.yaml. See the README."
            )

    def _working_files(self) -> dict[str, str]:
        files = {}
        for path in sorted(self.repo.rglob("*")):
            rel = path.relative_to(self.repo)
            if not path.is_file() or SKIP_DIRS & set(rel.parts) or path.suffix in SKIP_SUFFIXES or path.name == ".DS_Store":
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                files[rel.as_posix()] = path.read_text()
            except UnicodeDecodeError:
                continue                                   # binary file: tests do not need it
        return files

    def sync(self) -> int:
        """Replace the sandbox's copy of the repo with the working copy. Returns the number of files written."""
        files = self._working_files()
        directories = sorted({f"{REPO_DIR}/{Path(name).parent.as_posix()}" for name in files} | {REPO_DIR})
        self._shell(f"rm -rf {REPO_DIR} && mkdir -p {shlex.join(directories)}")   # a deleted file must disappear there too
        if files:
            self._invoke("writeFiles", {"content": [{"path": f"{REPO_DIR}/{name}", "text": text} for name, text in files.items()]})
        return len(files)

    def pytest(self, args: str = "") -> tuple[int, str]:
        """Copy the working copy into the sandbox and run pytest there. Returns (exit code, output)."""
        try:
            arguments = shlex.join(shlex.split(args))
        except ValueError as exc:
            return 2, f"could not read the pytest arguments: {exc}"
        self.sync()
        try:
            return self._shell(f"cd {REPO_DIR} && {settings.code_interpreter.python} -m pytest -q --color=no -p no:cacheprovider {arguments}")
        except ReadTimeoutError:
            return 124, "pytest timed out inside the sandbox"


# The job that is running right now. A session runs one job at a time, so a module-level holder is enough.
_active: Sandbox | None = None


def activate(box: Sandbox | None) -> None:
    global _active
    _active = box


def active() -> Sandbox:
    if _active is None:
        raise SandboxError("no sandbox is running for this job")
    return _active
