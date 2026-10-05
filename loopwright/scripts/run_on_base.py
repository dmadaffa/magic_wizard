"""Run tests on the base revision of a change and print what happened.

    python run_on_base.py <test files> [--fix <paths>] [--base <rev>]

Run it from the root of the repo under review. It creates a temporary git
worktree at the base revision (default HEAD) outside the repo, copies in every
file the change touched (`git diff --name-only <base>` plus untracked files)
except the --fix files, which stay at their base version, and deletes the files
the change deleted (again except --fix files). It then runs the test files
there and prints the base revision, the files copied, the files deleted, the fix
files kept at the base, the command, the runner's output as it came and the runner's exit code.
The worktree is always removed. The repo's working tree, index and refs are
not touched.

The script judges nothing: the reviewer reads the runner's per-test lines and
compares them with the developer's labels (reproduces tests must fail on the
base). Pass the test files and the fix files as paths relative to the repo
root. A file can't be both a fix file and a test to run.

The command comes from `.claude/loopwright.md`: the `## Test files command`
section with a `{files}` placeholder, else the `## Test command` section with
the test files appended. A uv project builds a fresh environment in the
worktree. Needs Python 3.10+ and git.

Exit codes: 0 whenever the tests ran, whatever their result (the runner's own
exit code is printed); non-zero only when the script couldn't run them (2 bad
usage, config or base revision, 3 worktree or command failure, 130 interrupted).
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG = Path(".claude") / "loopwright.md"


class UsageError(Exception):
    pass


class RunError(Exception):
    pass


def _git(repo, *args, check=True):
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RunError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _config_value(text, label):
    """The first non-empty, non-comment line under `## <label>`, without backticks."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    match = re.search(rf"^##\s+{re.escape(label)}\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    for line in text[match.end() :].splitlines():
        line = line.strip()
        if line.startswith("## "):
            return None
        if line:
            line = line.strip("`").strip()
            return None if line.lower() == "none" else line
    return None


def build_command(config_text, files):
    """The runner command as an argv list, with the test files in it."""
    files_command = _config_value(config_text, "Test files command")
    if files_command:
        tokens = shlex.split(files_command)
        if "{files}" not in tokens:
            raise UsageError(
                f"'Test files command' in {CONFIG} must contain {{files}} as its "
                "own argument (not inside another one), or the test files are dropped"
            )
        argv = []
        for token in tokens:
            argv += files if token == "{files}" else [token]
        return argv
    test_command = _config_value(config_text, "Test command")
    if not test_command:
        raise UsageError(f"no test command: set 'Test command' in {CONFIG}")
    return shlex.split(test_command) + files


def _repo_path(top, value):
    try:
        return Path(value).resolve().relative_to(top).as_posix()
    except ValueError:
        raise UsageError(f"not inside the repo: {value}") from None


def changed_files(repo, base):
    """(paths that exist now, paths the change deleted, {new path: old path} of
    renames), relative to the repo. A rename counts in both lists."""
    out = _git(repo, "diff", "--name-status", "--find-renames", "-z", base).stdout
    parts = [p for p in out.split("\0") if p]
    present, deleted, renames = [], [], {}
    i = 0
    while i < len(parts):
        status = parts[i][0]
        if status in "RC":
            old, new = parts[i + 1], parts[i + 2]
            i += 3
            present.append(new)
            if status == "R":
                deleted.append(old)
                renames[new] = old
            continue
        path = parts[i + 1]
        i += 2
        (deleted if status == "D" else present).append(path)
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z").stdout
    present += [p for p in untracked.split("\0") if p]
    return present, deleted, renames


def run_command(argv, cwd):
    """Run the test command; return (combined output, exit code)."""
    # On Windows a runner like npm is a .cmd file that only a full path finds.
    argv = [shutil.which(argv[0]) or argv[0], *argv[1:]]
    result = subprocess.run(
        argv,
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout, result.returncode


def _remove_worktree(repo, scratch):
    _git(repo, "worktree", "remove", "--force", str(scratch / "base"), check=False)
    shutil.rmtree(scratch, ignore_errors=True)
    _git(repo, "worktree", "prune", check=False)
    if scratch.exists():
        print(
            f"warning: couldn't remove {scratch} (a file may still be open); "
            "delete the directory, then run: git worktree prune",
            file=sys.stderr,
        )


def run(args):
    top = Path(
        _git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.strip()
    ).resolve()
    config_path = top / CONFIG
    if not config_path.is_file():
        raise UsageError(f"{CONFIG} not found in {top}")

    tests = [_repo_path(top, t) for t in args.tests]
    fix = {_repo_path(top, f) for f in args.fix}
    both = sorted(fix & set(tests))
    if both:
        raise UsageError(f"both a fix file and a test to run: {', '.join(both)}")
    argv = build_command(config_path.read_text(encoding="utf-8"), tests)

    sha = _git(top, "rev-parse", "--verify", f"{args.base}^{{commit}}", check=False)
    if sha.returncode != 0:
        raise UsageError(f"bad base revision: {args.base}")
    sha = sha.stdout.strip()

    present, deleted, renames = changed_files(top, sha)
    known = set(present) | set(deleted)
    unknown = sorted(fix - known)
    if unknown:
        raise UsageError(f"--fix path is not a changed file: {', '.join(unknown)}")
    # A convenience for renames git detected: naming either half keeps the pair
    # at the base (the old path alone would break imports, the new path alone
    # would apply the fix under its new name). A rename git doesn't detect (an
    # unstaged `mv`, a heavily edited file) shows as delete plus add: list both.
    fix |= {old for new, old in renames.items() if new in fix}
    fix |= {new for new, old in renames.items() if old in fix}
    copy = [p for p in present if p not in fix]
    remove = [p for p in deleted if p not in fix]
    kept = sorted(fix)

    _git(top, "worktree", "prune")
    scratch = Path(tempfile.mkdtemp(prefix="run_on_base_")).resolve()
    worktree = scratch / "base"
    try:
        _git(top, "worktree", "add", "--detach", str(worktree), sha)
        print(f"worktree: {worktree}")
        try:
            for rel in remove:
                (worktree / rel).unlink(missing_ok=True)
            for rel in copy:
                target = worktree / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(top / rel, target)
        except OSError as exc:
            raise RunError(f"couldn't copy the change into the worktree: {exc}") from exc
        print(f"base: {args.base} ({sha})")
        print(f"copied: {', '.join(copy) or '-'}")
        print(f"deleted: {', '.join(remove) or '-'}")
        print(f"kept at base: {', '.join(kept) or '-'}")
        print(f"command: {shlex.join(argv)}", flush=True)
        try:
            output, code = run_command(argv, worktree)
        except OSError as exc:
            raise RunError(f"couldn't run the command: {exc}") from exc
        print("--- runner output ---")
        print(output.rstrip("\n"))
        print("---")
        print(f"runner exit code: {code}")
    finally:
        _remove_worktree(top, scratch)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tests", nargs="+", help="test files to run, from the repo root")
    parser.add_argument(
        "--fix",
        nargs="+",
        default=[],
        metavar="PATH",
        help="files of the fix: they stay at their base version",
    )
    parser.add_argument("--base", default="HEAD", help="base revision (default HEAD)")
    args = parser.parse_args(argv)
    # Runner output can hold any text; a piped stdout may use a narrow encoding.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        run(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
