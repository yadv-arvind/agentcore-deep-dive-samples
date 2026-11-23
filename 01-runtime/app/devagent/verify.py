"""Check a job's result from the outside, without trusting what the agents report.

The job works on a copy of the bundled snapshot, so the snapshot is the baseline: every difference between
the two is a change the agents made.
"""
import difflib
from pathlib import Path

from progress import _test_summary
from tools.run_pytest import pytest_output

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
MAX_DIFF_CHARS = 6000


def _read_files(root: Path) -> dict[str, list[str]]:
    files = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not SKIP_DIRS & set(rel.parts) and path.suffix != ".pyc" and path.name != ".DS_Store":
            try:
                files[rel.as_posix()] = path.read_text(errors="ignore").splitlines()
            except OSError:
                files[rel.as_posix()] = []
    return files


def compare(baseline: Path, repo: Path) -> tuple[dict[str, tuple[int, int]], str]:
    """({path: (lines added, lines deleted)}, unified diff) for files that differ from the baseline."""
    before, after = _read_files(baseline), _read_files(repo)
    changes, diffs = {}, []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, []), after.get(name, [])
        if old == new:
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


def collect_tests(repo: Path) -> set[str]:
    """Test ids such as tests/test_items.py::test_health."""
    _, output = pytest_output("--collect-only", str(repo), timeout=300)
    return {line.strip() for line in output.splitlines() if "::" in line}


def spec_files(spec, repo: Path) -> set[str]:
    """The files the spec names, as paths relative to the repo."""
    names = set()
    for task in spec.tasks:
        for name in task.files:
            path = (repo / name).resolve()                      # an absolute name replaces the repo prefix
            names.add(path.relative_to(repo).as_posix() if repo in path.parents else name)
    return names


def check_spec_paths(spec, repo: Path) -> list[str]:
    """Problems with the paths in a spec: outside the repo, or in a directory that does not exist."""
    problems = []
    for task in spec.tasks:
        for name in task.files:
            path = (repo / name).resolve()
            if path != repo and repo not in path.parents:
                problems.append(f"{name}: outside the repository")
            elif not path.exists() and not path.parent.is_dir():
                problems.append(f"{name}: directory {path.parent.relative_to(repo)} does not exist")
    return problems


def verify(baseline: Path, repo: Path, spec, tests_before: set[str]) -> dict:
    """Compare the repo with the baseline and run its tests. Returns the report that main.py emits."""
    changes, diff = compare(baseline, repo)
    in_scope = spec_files(spec, repo)
    problems = []
    if not changes:
        problems.append("no files changed")
    for name, (added, deleted) in changes.items():
        if name not in in_scope:
            problems.append(f"{name} changed but is not in the spec")
        if deleted > added:
            problems.append(f"{name} lost more lines than it gained (+{added} -{deleted})")

    tests_after = collect_tests(repo)
    removed = sorted(tests_before - tests_after)
    if removed:
        problems.append("tests that existed before are gone: " + ", ".join(removed))
    code, output = pytest_output("", str(repo), timeout=300)
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
