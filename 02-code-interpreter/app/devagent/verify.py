"""Check a job's result from the outside, without trusting what the agents report.

The job works in a Code Interpreter sandbox that started as a copy of the bundled snapshot, so the snapshot is
the baseline: every difference between the two is a change the agents made. The judgement runs here, in the
Runtime container. The sandbox only supplies the files and runs the tests, because a check that ran inside the
thing it checks could be fooled by it.
"""
import difflib
from pathlib import Path, PurePosixPath

from progress import _test_summary
from sandbox import SandboxError, clean_path, local_files
from tools.run_pytest import pytest_output

MAX_DIFF_CHARS = 6000


def compare(before: dict[str, str], after: dict[str, str]) -> tuple[dict[str, tuple[int, int]], str]:
    """({path: (lines added, lines deleted)}, unified diff) for files that differ. Both map path to contents."""
    changes, diffs = {}, []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, "").splitlines(), after.get(name, "").splitlines()
        if before.get(name) == after.get(name):
            continue
        lines = list(difflib.unified_diff(old, new, f"a/{name}", f"b/{name}", lineterm="", n=2))
        added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        deleted = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
        changes[name] = (added, deleted)
        diffs.append("\n".join(lines))
    diff = "\n".join(diffs)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[diff truncated]"
    return changes, diff


def collect_tests() -> set[str]:
    """Test ids such as tests/test_items.py::test_health."""
    _, output = pytest_output("--collect-only")
    return {line.strip() for line in output.splitlines() if "::" in line}


def _relative(name: str) -> str | None:
    """A spec path as a path inside the repository, or None when it points outside."""
    try:
        return clean_path(name)
    except SandboxError:
        return None


def spec_files(spec) -> set[str]:
    """The files the spec names, as paths relative to the repo."""
    return {rel for task in spec.tasks for name in task.files if (rel := _relative(name)) is not None}


def check_spec_paths(spec, files: list[str]) -> list[str]:
    """Problems with the paths in a spec: outside the repo, or in a directory that does not exist."""
    known = set(files)
    directories = {"."} | {parent.as_posix() for name in files for parent in PurePosixPath(name).parents}
    problems = []
    for task in spec.tasks:
        for name in task.files:
            rel = _relative(name)
            if rel is None:
                problems.append(f"{name}: outside the repository")
            elif rel not in known and PurePosixPath(rel).parent.as_posix() not in directories:
                problems.append(f"{name}: directory {PurePosixPath(rel).parent.as_posix()} does not exist")
    return problems


def verify(baseline: Path, box, spec, tests_before: set[str]) -> dict:
    """Compare the sandbox's repo with the baseline and run its tests. Returns the report that main.py emits."""
    tests_after = collect_tests()
    code, output = pytest_output("")
    changes, diff = compare(local_files(baseline), box.download_all())   # read last, so it is the final state

    in_scope = spec_files(spec)
    problems = []
    if not changes:
        problems.append("no files changed")
    for name, (added, deleted) in changes.items():
        if name not in in_scope:
            problems.append(f"{name} changed but is not in the spec")
        if deleted > added:
            problems.append(f"{name} lost more lines than it gained (+{added} -{deleted})")
    removed = sorted(tests_before - tests_after)
    if removed:
        problems.append("tests that existed before are gone: " + ", ".join(removed))
    if code != 0:
        problems.append("pytest fails")
    return {
        "ok": not problems,
        "problems": problems,
        "files": {name: {"added": a, "deleted": d} for name, (a, d) in changes.items()},
        "tests_before": len(tests_before),
        "tests_after": len(tests_after),
        "pytest": _test_summary(f"exit code {code}\n{output}"),
        "diff": diff,
    }
