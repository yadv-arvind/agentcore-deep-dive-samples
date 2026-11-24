"""The job's workspace: an AgentCore Code Interpreter session that holds the repo and runs its tests.

The Runtime container, which holds the agent's credentials, never has a working copy. It uploads the snapshot
once, and from then on every read, write and test run goes through this session. Model-written code, and the
files the model chooses to write, stay in the sandbox.

One Sandbox per job. The session keeps its filesystem and installed packages between calls, and close()
stops it, because an idle session still bills.
"""
import json
import re
import shlex
from pathlib import Path, PurePosixPath

from botocore.exceptions import ReadTimeoutError
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

from settings import settings

REPO_DIR = "repo"                     # the repository, relative to the sandbox's working directory
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".so"}
MAX_FILE_BYTES = 200_000
EXIT_MARKER = re.compile(r"^\[exit code (\d+)\]\s*$", re.MULTILINE)

# Runs inside the sandbox: lists the repo's files, or dumps them all as JSON, in one round trip.
TREE_SCRIPT = f"""
import json, os, sys
skip, out = {sorted(SKIP_DIRS)!r}, {{}}
for root, dirs, names in os.walk({REPO_DIR!r}):
    dirs[:] = sorted(d for d in dirs if d not in skip)
    for name in sorted(names):
        if name.endswith({tuple(sorted(SKIP_SUFFIXES))!r}) or name == ".DS_Store":
            continue
        path = os.path.join(root, name)
        rel = os.path.relpath(path, {REPO_DIR!r}).replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8", newline="") as f:
                out[rel] = f.read() if sys.argv[1] == "dump" else None
        except (UnicodeDecodeError, OSError):
            pass
print(json.dumps(out if sys.argv[1] == "dump" else sorted(out)))
"""


class SandboxError(RuntimeError):
    """The sandbox could not start, was missing something, or answered in a way this code does not expect."""


def clean_path(path: str) -> str:
    """A path inside the repository, as a relative POSIX path. Raises SandboxError for anything that escapes it."""
    posix = PurePosixPath(str(path).strip().replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts or posix.as_posix() == ".":
        raise SandboxError(f"{path!r} is not a path inside the repository. Use a relative path such as app/main.py.")
    return posix.as_posix()


def local_files(root: Path) -> dict[str, str]:
    """The text files under a local directory, with the same filters the sandbox uses."""
    files = {}
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or SKIP_DIRS & set(rel.parts) or path.suffix in SKIP_SUFFIXES or path.name == ".DS_Store":
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            files[rel.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue                                       # binary file: tests do not need it
    return files


def _read_response(response: dict) -> tuple[bool, str]:
    """(is_error, text) from an invoke_code_interpreter response, which is a stream of result events."""
    is_error, texts = False, []
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            continue
        is_error = is_error or bool(result.get("isError"))
        structured = result.get("structuredContent") or {}
        parts = [str(structured[key]) for key in ("stdout", "stderr") if structured.get(key)]
        if not parts:
            parts = [str(block.get("text", "")) for block in result.get("content") or [] if isinstance(block, dict)]
        texts.append("\n".join(part for part in parts if part))
    return is_error, "".join(texts)


class Sandbox:
    def __init__(self, emit=None):
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
        self._shell(f"rm -rf {REPO_DIR} && mkdir {REPO_DIR}")
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

    # -- low level ---------------------------------------------------------------------------------------

    def _invoke(self, method: str, arguments: dict) -> str:
        if self.client is None:
            raise SandboxError("the sandbox session is not running")
        is_error, text = _read_response(self.client.invoke(method, arguments))
        if is_error:
            raise SandboxError(f"{method} failed: {text[-1000:]}")
        return text

    def _shell(self, script: str, raw: bool = False) -> tuple[int, str]:
        """Run a shell script in the sandbox. Returns (exit code, output).

        stderr is merged into stdout, and the script prints its exit code as a marker on the last line, so the
        result does not depend on how the service reports exit codes. With raw=True the output is returned
        exactly as printed, which file contents need. Otherwise it is stripped.
        """
        wrapped = f"exec 2>&1\n{script}\nprintf '\\n[exit code %s]\\n' \"$?\""
        text = self._invoke("executeCommand", {"command": f"bash -c {shlex.quote(wrapped)}"})
        matches = list(EXIT_MARKER.finditer(text))
        if not matches:
            raise SandboxError(f"the sandbox gave no exit code for `{script[:80]}`. Output: {text[-500:]}")
        marker = matches[-1]
        before = text[: marker.start()]
        before = before[:-1] if before.endswith("\n") else before          # the newline the marker line added
        return int(marker.group(1)), (before if raw else before.strip())

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

    def _write(self, files: dict[str, str]) -> None:
        directories = sorted({f"{REPO_DIR}/{PurePosixPath(name).parent.as_posix()}" for name in files})
        self._shell(f"mkdir -p {shlex.join(directories)}")
        self._invoke("writeFiles", {"content": [{"path": f"{REPO_DIR}/{name}", "text": text} for name, text in files.items()]})

    def _tree(self, mode: str):
        code, out = self._shell(f"{settings.code_interpreter.python} -W ignore -c {shlex.quote(TREE_SCRIPT)} {mode}", raw=True)
        try:
            if code != 0:
                raise ValueError(out[-300:])
            return json.loads(out)
        except ValueError as exc:
            raise SandboxError(f"could not read the repository's files from the sandbox: {exc}") from exc

    # -- the workspace -----------------------------------------------------------------------------------

    def load(self, root: Path) -> int:
        """Upload a local directory as the repository. Returns the number of files."""
        files = local_files(root)
        if files:
            self._write(files)
        return len(files)

    def list_files(self) -> list[str]:
        return self._tree("list")

    def read_file(self, path: str) -> str:
        rel = clean_path(path)
        code, out = self._shell(f"cat -- {shlex.quote(f'{REPO_DIR}/{rel}')}", raw=True)
        if code != 0:
            raise SandboxError(f"{rel}: no such file in the repository")
        return out

    def write_file(self, path: str, content: str) -> None:
        self._write({clean_path(path): content})

    def download_all(self) -> dict[str, str]:
        """Every text file in the repository, as it is now."""
        return self._tree("dump")

    def pytest(self, args: str = "") -> tuple[int, str]:
        """Run pytest on the repository in the sandbox. Returns (exit code, output)."""
        try:
            arguments = shlex.join(shlex.split(args))
        except ValueError as exc:
            return 2, f"could not read the pytest arguments: {exc}"
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
