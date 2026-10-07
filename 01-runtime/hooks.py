from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent, AfterToolCallEvent

class ToolLog(HookProvider):
    """Print every tool call. Event class names have changed between Strands versions; check the hooks doc."""
    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event):
        print("->", event.tool_use["name"], str(event.tool_use["input"])[:120])

    def after(self, event):
        print("<-", event.tool_use["name"], "done")

# Agent(..., hooks=[ToolLog()])
