import json
import re

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry


def _result_text(result: dict) -> str:
    blocks = result.get("content") or []
    return " ".join(b.get("text", "") for b in blocks if isinstance(b, dict))


def _task_title(tool_input: dict) -> str:
    raw = tool_input.get("task_json", "")
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            parsed = None
    if isinstance(parsed, dict) and parsed.get("title"):
        return str(parsed["title"])
    # The model may pass plain text instead of JSON: use its first line.
    first_line = str(raw).strip().splitlines()[0] if str(raw).strip() else ""
    return first_line[:80]


PYTEST_SUMMARY = re.compile(r"\d+ (passed|failed|errors?|skipped)|no tests ran")


def _test_summary(text: str) -> str:
    """The exit code plus the pytest summary line, or the last line of output when there is none."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    summary = next((line for line in reversed(lines[1:]) if PYTEST_SUMMARY.search(line)), lines[-1])
    return f"{lines[0]}: {summary}" if len(lines) > 1 else lines[0]


def _failures(text: str, limit: int = 4) -> list[str]:
    """The FAILED and error lines pytest prints, so a failed run says which test and why."""
    lines = [line.strip() for line in text.splitlines()]
    picked = [line[:200] for line in lines if line.startswith(("FAILED", "ERROR", "E "))]
    return picked[:limit]


class ProgressHook(HookProvider):
    """Turn tool calls into progress events. emit(name, **fields) receives each event."""

    def __init__(self, emit):
        self.emit = emit

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event):
        if event.tool_use["name"] == "implement_task":
            self.emit("task_started", title=_task_title(event.tool_use.get("input", {})))

    def after(self, event):
        name = event.tool_use["name"]
        text = _result_text(event.result).strip()
        if name == "run_pytest":
            if text.startswith("exit code 0"):
                self.emit("tests_passed", summary=_test_summary(text))
            else:
                self.emit("tests_failed", summary=_test_summary(text), failures=_failures(text))
        elif name == "write_file":
            if text.startswith("wrote "):
                self.emit("file_written", path=str(event.tool_use.get("input", {}).get("path", "")))
        elif name == "review_change":
            approved = text.startswith("APPROVE")
            fields = {} if approved else {"reason": text[:400]}
            self.emit("task_reviewed", approved=approved, **fields)
