import json

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
            last_line = text.splitlines()[-1] if text else ""
            self.emit("tests_passed" if text.startswith("exit code 0") else "tests_failed", summary=last_line)
        elif name == "review_change":
            self.emit("task_reviewed", approved=text.startswith("APPROVE"))
