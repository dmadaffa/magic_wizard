"""Tests for loopwright/scripts/run_on_base.py.

Each test builds a throwaway git repo with an invented module and tests, calls
the script's `main()` in that repo and checks the printed report, the exit code
and the leftover worktrees. The runner in the repos is pytest itself.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_on_base.py"
PY = Path(sys.executable).as_posix()
RUNNER = f"{PY} -m pytest -v -p no:cacheprovider"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}

# Enough shared lines for git to detect a rename.
PADDING = "".join(f"CONSTANT_{i} = {i}\n" for i in range(10))
TEST_CALC = "from calc import double\n\n\ndef test_double():\n    assert double(2) == 4\n"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("run_on_base", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **GIT_ENV},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def config(test_command=RUNNER, files_command=None):
    text = f"# Loopwright project settings\n\n## Test command\n\n`{test_command}`\n"
    if files_command is not None:
        text += f"\n## Test files command\n\n<!-- comment -->\n\n{files_command}\n"
    return text


def make_repo(tmp_path, cfg=None, files=()):
    """A git repo with one commit holding the config and `files`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo, ".claude/loopwright.md", cfg or config())
    for rel, text in files:
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return repo


def run(script, repo, monkeypatch, capsys, *args):
    monkeypatch.chdir(repo)
    code = script.main(list(args))
    return code, capsys.readouterr().out


def worktrees(repo):
    return [
        line
        for line in git(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]


def test_new_support_file_reaches_worktree_but_new_fix_file_does_not(
    script, tmp_path, monkeypatch, capsys
):
    # reproduces. Done when: new untracked support file (in a new subdirectory)
    # copied unlisted; new fix file absent.
    repo = make_repo(tmp_path)
    write(repo, "calc.py", "def double(x):\n    return x * 2\n")
    write(repo, "support/helpers.py", "VALUE = 1\n")
    write(repo, "test_calc.py", "from support import helpers\n" + TEST_CALC)
    code, out = run(
        script, repo, monkeypatch, capsys, "test_calc.py", "--fix", "calc.py"
    )
    assert code == 0
    assert "No module named 'calc'" in out
    assert "No module named 'support'" not in out
    assert "support/helpers.py" in out and "test_calc.py" in out
    assert "calc.py" in out.split("kept at base:")[1].split("command:")[0]


@pytest.mark.parametrize(
    "fix_args, expected",
    [
        (["--fix", "calc.py"], "1 failed"),
        ([], "1 passed"),
    ],
    ids=["fix kept at base, test fails", "forgotten fix file, test passes"],
)
def test_modified_fix_file_stays_at_base_version(
    script, tmp_path, monkeypatch, capsys, fix_args, expected
):
    # reproduces. Done when: fix file stays at base; forgotten fix file lets the
    # test pass on the base.
    repo = make_repo(tmp_path, files=[("calc.py", "def double(x):\n    return x\n")])
    write(repo, "calc.py", "def double(x):\n    return x * 2\n")
    write(repo, "test_calc.py", TEST_CALC)
    code, out = run(script, repo, monkeypatch, capsys, "test_calc.py", *fix_args)
    assert code == 0
    assert expected in out


@pytest.mark.parametrize(
    "fix_args, expected",
    [
        ([], "1 passed"),
        (["--fix", "old_helper.py"], "1 failed"),
    ],
    ids=["deleted non-fix file is deleted", "deleted fix file is kept"],
)
def test_deleted_files(script, tmp_path, monkeypatch, capsys, fix_args, expected):
    # reproduces. Done when: a deleted non-fix file is deleted in the worktree.
    repo = make_repo(tmp_path, files=[("old_helper.py", "X = 1\n")])
    (repo / "old_helper.py").unlink()
    write(
        repo,
        "test_gone.py",
        "from pathlib import Path\n\n\n"
        "def test_gone():\n    assert not Path('old_helper.py').exists()\n",
    )
    code, out = run(script, repo, monkeypatch, capsys, "test_gone.py", *fix_args)
    assert code == 0
    assert expected in out


def make_rename_repo(tmp_path):
    """pkg/calc.py is renamed (staged, so git detects it) to pkg/mathops.py
    with a fix; pkg/api.py follows; test_api.py is new."""
    repo = make_repo(
        tmp_path,
        files=[
            ("pkg/__init__.py", ""),
            ("pkg/calc.py", PADDING + "def double(x):\n    return x\n"),
            ("pkg/api.py", "from pkg.calc import double\n"),
        ],
    )
    git(repo, "mv", "pkg/calc.py", "pkg/mathops.py")
    write(repo, "pkg/mathops.py", PADDING + "def double(x):\n    return x * 2\n")
    write(repo, "pkg/api.py", "from pkg.mathops import double\n")
    write(
        repo,
        "test_api.py",
        "from pkg.api import double\n\n\ndef test_double():\n    assert double(2) == 4\n",
    )
    return repo


@pytest.mark.parametrize(
    "named",
    ["pkg/mathops.py", "pkg/calc.py"],
    ids=["new path named", "old path named"],
)
def test_renamed_fix_file_keeps_both_paths_at_base(
    script, tmp_path, monkeypatch, capsys, named
):
    # reproduces. Done when: file selection pairs a detected rename, whichever
    # half is named: the old path stays, the new path stays absent.
    repo = make_rename_repo(tmp_path)
    code, out = run(
        script, repo, monkeypatch, capsys, "test_api.py", "--fix", named, "pkg/api.py"
    )
    assert code == 0
    assert "1 failed" in out and "No module named" not in out
    kept = out.split("kept at base:")[1].split("command:")[0]
    assert "pkg/calc.py" in kept and "pkg/mathops.py" in kept


def test_renamed_non_fix_file_moves(script, tmp_path, monkeypatch, capsys):
    # reproduces. Done when: a renamed non-fix file is copied under its new path
    # and deleted under the old one.
    repo = make_rename_repo(tmp_path)
    code, out = run(script, repo, monkeypatch, capsys, "test_api.py")
    assert code == 0
    assert "1 passed" in out
    assert "\ndeleted: pkg/calc.py\n" in out


@pytest.mark.parametrize(
    "test_body, runner_code, test_line",
    [
        ("assert True", 0, "test_x.py::test_x PASSED"),
        ("assert False", 1, "test_x.py::test_x FAILED"),
    ],
    ids=["passing", "failing"],
)
def test_completed_run_reports_and_exits_zero_and_removes_worktree(
    script, tmp_path, monkeypatch, capsys, test_body, runner_code, test_line
):
    # reproduces. Done when: exit 0 whenever the tests ran, whatever their
    # result; the output is a report without a verdict; the worktree is gone
    # after a normal and a failing run.
    repo = make_repo(tmp_path)
    write(repo, "test_x.py", f"def test_x():\n    {test_body}\n")
    code, out = run(script, repo, monkeypatch, capsys, "test_x.py")
    head = git(repo, "rev-parse", "HEAD").strip()
    assert code == 0
    assert f"base: HEAD ({head})" in out
    assert "copied: test_x.py" in out and "kept at base: -" in out
    assert f"command: {RUNNER} test_x.py" in out
    assert test_line in out
    assert f"runner exit code: {runner_code}" in out
    wt = out.split("worktree: ")[1].splitlines()[0]
    assert not Path(wt).exists()
    assert len(worktrees(repo)) == 1


def test_worktree_is_removed_after_interrupt(script, tmp_path, monkeypatch, capsys):
    # reproduces. Done when: worktree gone after an interrupted run.
    repo = make_repo(tmp_path)
    write(repo, "test_x.py", "def test_x():\n    pass\n")

    def interrupted(argv, cwd):
        raise KeyboardInterrupt

    monkeypatch.setattr(script, "run_command", interrupted)
    code, out = run(script, repo, monkeypatch, capsys, "test_x.py")
    wt = out.split("worktree: ")[1].splitlines()[0]
    assert code != 0
    assert not Path(wt).exists()
    assert len(worktrees(repo)) == 1


def test_stale_worktree_entries_are_pruned_at_start(
    script, tmp_path, monkeypatch, capsys
):
    # reproduces. Done when: a hard-killed earlier run leaves an entry; the next
    # run prunes it.
    repo = make_repo(tmp_path)
    stale = tmp_path / "stale"
    git(repo, "worktree", "add", "--detach", str(stale), "HEAD")
    shutil.rmtree(stale)
    assert len(worktrees(repo)) == 2
    write(repo, "test_x.py", "def test_x():\n    pass\n")
    run(script, repo, monkeypatch, capsys, "test_x.py")
    assert len(worktrees(repo)) == 1


def test_repo_under_review_is_left_untouched(script, tmp_path, monkeypatch, capsys):
    # reproduces. Done when: the repo's working tree, index and refs are not
    # touched.
    repo = make_repo(tmp_path, files=[("calc.py", "def double(x):\n    return x\n")])
    write(repo, "calc.py", "def double(x):\n    return x * 2\n")
    write(repo, "test_calc.py", TEST_CALC)
    before = git(repo, "status", "--porcelain"), (repo / "calc.py").read_text()
    head = git(repo, "rev-parse", "HEAD")
    refs = git(repo, "for-each-ref")
    run(script, repo, monkeypatch, capsys, "test_calc.py", "--fix", "calc.py")
    assert (git(repo, "status", "--porcelain"), (repo / "calc.py").read_text()) == before
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "for-each-ref") == refs


def test_base_option_reviews_a_commit_range(script, tmp_path, monkeypatch, capsys):
    # reproduces. Done when: --base <rev> replaces HEAD as the base.
    repo = make_repo(tmp_path)
    first = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "calc.py", "def double(x):\n    return x * 2\n")
    write(repo, "test_calc.py", TEST_CALC)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    code, out = run(
        script,
        repo,
        monkeypatch,
        capsys,
        "test_calc.py",
        "--fix",
        "calc.py",
        "--base",
        first,
    )
    assert code == 0
    assert "No module named 'calc'" in out


@pytest.mark.parametrize(
    "cfg, expected_command",
    [
        (config(), f"{RUNNER} test_x.py"),
        (config(files_command="none"), f"{RUNNER} test_x.py"),
        (
            config(files_command=f"{PY} -m pytest -v -p no:cacheprovider {{files}}"),
            f"{PY} -m pytest -v -p no:cacheprovider test_x.py",
        ),
        (
            config(
                test_command=f"{PY} -m pytest -q",
                files_command=f"{PY} -m pytest -v -p no:cacheprovider {{files}}",
            ),
            f"{PY} -m pytest -v -p no:cacheprovider test_x.py",
        ),
    ],
    ids=["no section", "none", "placeholder", "placeholder wins over test command"],
)
def test_command_comes_from_config(
    script, tmp_path, monkeypatch, capsys, cfg, expected_command
):
    # reproduces. Done when: Test files command with {files}, else Test command
    # plus the files.
    repo = make_repo(tmp_path, cfg=cfg)
    write(repo, "test_x.py", "def test_x():\n    pass\n")
    code, out = run(script, repo, monkeypatch, capsys, "test_x.py")
    assert code == 0
    assert f"command: {expected_command}\n" in out
    assert "1 passed" in out


def test_files_placeholder_may_sit_before_other_arguments(
    script, tmp_path, monkeypatch, capsys
):
    # decision: {files} is replaced where it stands, not only at the end.
    cfg = config(files_command=f"{PY} -m pytest {{files}} -v -p no:cacheprovider")
    repo = make_repo(tmp_path, cfg=cfg)
    write(repo, "test_x.py", "def test_x():\n    pass\n")
    code, out = run(script, repo, monkeypatch, capsys, "test_x.py")
    assert code == 0
    assert "test_x.py::test_x PASSED" in out


@pytest.mark.parametrize(
    "cfg, args",
    [
        (None, ["test_x.py", "--base", "nope"]),
        (config(test_command="no-such-runner-xyz -v"), ["test_x.py"]),
        (None, ["test_x.py", "--fix", "test_x.py"]),
        (None, ["test_x.py", "--fix", "pkg"]),
        (None, ["test_x.py", "--fix", "pkg/nope.py"]),
        (config(files_command=f"{PY} -m pytest -v"), ["test_x.py"]),
        (config(files_command=f"{PY} -m pytest --tests={{files}}"), ["test_x.py"]),
        # decision: "none" for the test command means there is nothing to run.
        (config(test_command="none"), ["test_x.py"]),
    ],
    ids=[
        "bad base revision",
        "missing command",
        "file is both fix and test",
        "fix path is a directory",
        "fix path is not a changed file",
        "files command without a placeholder",
        "placeholder inside another argument",
        "no test command",
    ],
)
def test_runs_that_cant_start_exit_nonzero(
    script, tmp_path, monkeypatch, capsys, cfg, args
):
    # reproduces. Done when: bad base, missing command, and a file that is both
    # fix and test exit non-zero; the unknown --fix paths and the "none" test
    # command (the last case pins that choice) too.
    repo = make_repo(tmp_path, cfg=cfg, files=[("pkg/__init__.py", "")])
    write(repo, "test_x.py", "def test_x():\n    pass\n")
    code, out = run(script, repo, monkeypatch, capsys, *args)
    assert code != 0
    assert "runner exit code" not in out
    assert len(worktrees(repo)) == 1


def test_command_found_through_path_shim(script, tmp_path, monkeypatch, capsys):
    # reproduces. On Windows a runner such as npm is a .cmd file that
    # subprocess can't start by bare name; the script resolves it through PATH.
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    if os.name == "nt":
        (shim_dir / "myrunner.cmd").write_text(f'@"{PY}" -m pytest %*\n')
    else:
        shim = shim_dir / "myrunner"
        shim.write_text(f'#!/bin/sh\nexec "{PY}" -m pytest "$@"\n')
        shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    repo = make_repo(tmp_path, cfg=config(test_command="myrunner -v"))
    write(repo, "test_x.py", "def test_x():\n    pass\n")
    code, out = run(script, repo, monkeypatch, capsys, "test_x.py")
    assert code == 0
    assert "1 passed" in out


def test_cli_with_non_ascii_runner_output(tmp_path):
    # reproduces. Piped stdout on Windows uses the locale encoding; the runner
    # output must still come through and the exit code stay 0.
    repo = make_repo(tmp_path)
    write(
        repo,
        "test_x.py",
        "def test_x():\n    print('日本')\n    assert False\n",
    )
    env = {
        k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "test_x.py"],
        cwd=repo,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    out = result.stdout.decode("utf-8")
    assert "日本" in out
    assert "1 failed" in out
