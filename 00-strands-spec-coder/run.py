"""Plan a change with the planner agent, then implement it with the orchestrator.

    python run.py "Add a DELETE /items/{item_id} endpoint" --repo ../../shop-api
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT)]                       # settings.py lives in the repo root
os.environ.setdefault("PITWALL_RESOURCES", str(ROOT / "resources.yaml"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plan, implement and review a change in a local repo.")
    p.add_argument("request", help="what to build, in plain language")
    p.add_argument("--repo", required=True, help="path to the repository the agents work on")
    p.add_argument("--plan-only", action="store_true", help="print the spec and stop; nothing is written")
    p.add_argument("--yes", action="store_true", help="skip the confirmation before implementation")
    p.add_argument("--verbose", action="store_true", help="print every tool call")
    return p.parse_args()


def check_spec_paths(spec, repo: Path) -> tuple[list[str], list[str]]:
    """Return (problems, new_files). A problem is a path outside the repo or in a directory that does not exist."""
    problems, new_files = [], []
    for task in spec.tasks:
        for name in task.files:
            path = (repo / name).resolve()                      # an absolute name replaces the repo prefix
            if path != repo and repo not in path.parents:
                problems.append(f"{name}: outside the repository")
            elif not path.exists():
                if path.parent.is_dir():
                    new_files.append(name)
                else:
                    problems.append(f"{name}: directory {path.parent.relative_to(repo)} does not exist")
    return problems, new_files


def list_repo_files(repo: Path) -> str:
    """Relative paths of the repo's files, one per line. Tracked and untracked, minus ignored, when it is a git repo."""
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=repo, capture_output=True, text=True, check=True).stdout
        names = [n for n in out.split() if not n.endswith(".DS_Store")]
    except (subprocess.CalledProcessError, FileNotFoundError):
        skip = {".git", ".venv", "__pycache__", "node_modules"}
        names = [str(p.relative_to(repo)) for p in repo.rglob("*")
                 if p.is_file() and not skip & set(p.relative_to(repo).parts) and p.name != ".DS_Store"]
    return "\n".join(sorted(names))


def run_tests(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run pytest in the repo, preferring the repo's own virtual environment."""
    venv_python = repo / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable
    try:
        return subprocess.run([python, "-m", "pytest", "-q", *args], cwd=repo,
                              capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "pytest timed out after 300 seconds")


def collect_tests(repo: Path) -> set[str]:
    """Test ids such as tests/test_items.py::test_health."""
    out = run_tests(repo, "--collect-only").stdout
    return {line.strip() for line in out.splitlines() if "::" in line}


def change_summary(repo: Path) -> dict[str, tuple[int, int]]:
    """{path: (lines added, lines deleted)} for changes against the last commit, new files included."""
    def git(*a: str) -> list[str]:
        return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True).stdout.splitlines()

    changes = {}
    for line in git("diff", "--numstat", "HEAD"):
        added, deleted, path = line.split("\t", 2)
        changes[path] = (int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0)
    for path in git("ls-files", "--others", "--exclude-standard"):
        if not path.endswith(".DS_Store"):
            try:
                changes[path] = (len((repo / path).read_text(errors="ignore").splitlines()), 0)
            except OSError:
                changes[path] = (0, 0)
    return changes


def verify(repo: Path, spec, tests_before: set[str], changes_before: dict) -> bool:
    """Check the run from the outside, without trusting what the agents report."""
    print("\n== Independent check (not the agents' report) ==")
    in_scope = set()
    for task in spec.tasks:
        for name in task.files:
            path = (repo / name).resolve()
            in_scope.add(str(path.relative_to(repo)) if repo in path.parents else name)

    problems = []
    after = change_summary(repo)
    changed = {p: v for p, v in after.items() if changes_before.get(p) != v}
    print("Changed files:" if changed else "Changed files: none")
    for path, (added, deleted) in sorted(changed.items()):
        print(f"  {path}: +{added} -{deleted}")
        if path not in in_scope:
            problems.append(f"{path} changed but is not in the spec")
        if deleted > added:
            problems.append(f"{path} lost more lines than it gained (+{added} -{deleted})")

    tests_after = collect_tests(repo)
    removed = sorted(tests_before - tests_after)
    if removed:
        problems.append("tests that existed before are gone: " + ", ".join(removed))
    result = run_tests(repo)
    summary = (result.stdout.strip().splitlines() or ["no output"])[-1]
    print(f"Tests: {len(tests_before)} before, {len(tests_after)} after. pytest: {summary}")
    if result.returncode != 0:
        problems.append("pytest fails")
        print("\n".join((result.stdout + result.stderr).splitlines()[-15:]))

    if problems:
        print("\nNEEDS REVIEW:")
        for problem in problems:
            print(f"  - {problem}")
        print("Undo with: git checkout -- . && git clean -fd   (run inside the repo, and only if you want it all gone)")
        return False
    print("No problems found.")
    return True


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"Repository not found: {repo}", file=sys.stderr)
        return 1

    # These imports load settings, so they come after the path setup above.
    from agents.coder import coder
    from agents.orchestrator import orchestrator
    from agents.planner import make_spec, planner
    from agents.reviewer import reviewer
    from hooks import ToolLog

    if args.verbose:
        for agent in (planner, coder, reviewer, orchestrator):
            agent.hooks.add_hook(ToolLog())

    # Relative paths in the spec and the default run_pytest directory now resolve inside the repo.
    os.chdir(repo)

    print(f"Planning in {repo} ...")
    spec = make_spec(
        f"{args.request}\n\n"
        f"The current directory is the repository. Its files, as relative paths:\n{list_repo_files(repo)}\n\n"
        "Read the files the change touches with exactly these relative paths before planning."
    )
    spec_json = spec.model_dump_json(indent=2)
    print(spec_json)

    if not spec.tasks:
        print("\nThe spec has no tasks, so there is nothing to implement. Rephrase the request and try again.",
              file=sys.stderr)
        return 1
    problems, new_files = check_spec_paths(spec, repo)
    if problems:
        print("\nThe spec refers to paths that do not exist in the repo, so the plan is probably invented:",
              file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if new_files:
        print("\nThe plan will create these new files:")
        for name in new_files:
            print(f"  - {name}")
    if args.plan_only:
        return 0
    if not args.yes and input("\nProceed with implementation? [y/N] ").strip().lower() != "y":
        print("Stopped before implementation.")
        return 0

    tests_before = collect_tests(repo)
    changes_before = change_summary(repo)
    print(f"\nBaseline: {len(tests_before)} tests collected.")

    print("\nImplementing ...")
    result = orchestrator(
        f"Repository: {repo}\n\nSpec:\n{spec_json}\n\n"
        "Implement every task in the spec, reviewing each one, and report the outcome."
    )
    print("\n" + str(result))
    return 0 if verify(repo, spec, tests_before, changes_before) else 1


if __name__ == "__main__":
    sys.exit(main())
