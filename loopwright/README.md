# loopwright

A blind reviewer that proves each new test fails on the old code before the change is committed.

loopwright is a Claude Code plugin for test-first work on a task queue.

- A developer subagent writes a failing test, fixes the code, and labels every test it adds.
- A code-reviewer subagent judges the change against the task alone, re-runs the new tests on the base revision, and runs the full suite.
- You (the orchestrating session) pick the task, forward findings, commit, and close it.

## Install

```
claude plugin marketplace add dmadaffa/loopwright
claude plugin install loopwright@loopwright
```

Then, in your project, run `/loopwright:init`. It looks at how the project runs tests and checks, asks you to confirm in one question, and writes `.claude/loopwright.md`, a project rules file and the task folders. It never overwrites an existing `.claude/loopwright.md`.

Needs Python 3.10+ and git. The scripts use only the standard library.

## The workflow

1. `/loopwright:task-new <description>` creates a task file (markdown with YAML frontmatter) and updates the generated `INDEX.md`.
2. `/loopwright:task-work [id]` picks a task: the given id, or the lowest-id open one that is ready.
3. The `developer` subagent writes the failing test first, then the smallest fix. It reports every test with a label (below) and the failing output from before the fix. It never commits.
4. The `code-reviewer` subagent gets the task and the diff, never the developer's report. It runs `scripts/run_on_base.py` to see the new tests run on the base revision, runs the full suite and the project's checks, and returns a verdict.
5. Review rounds repeat until no blocking or should-fix finding remains. You then commit (never with `--no-verify`) and close the task.

## Why it works this way

**The blind reviewer.** The reviewer never sees the developer's report or reasoning. A report is a set of claims by the author; a reviewer who reads it starts by agreeing with it. Given only the task and the diff, the reviewer has to check each claim itself or not make it.

**The base-revision check.** In TDD the red step is the proof that a test tests something: it must fail before the fix. A report saying "it failed" is not proof. `run_on_base.py` creates a temporary git worktree at the base revision, copies in the changed files except the fix files, runs the new tests there, prints what happened and removes the worktree. It supplies the evidence and judges nothing: the reviewer reads the per-test lines and verifies red against the developer's labels, and green with the full suite. A uv project builds a fresh environment in the worktree on the first run, so the reviewer allows a long timeout.

**The reproduces / guard / decision labels.** Every added test has one stated purpose. A *reproduces* test fails before the fix and passes after, and every task needs one. A *guard* passes before and after and names the realistic over-fix it would catch. A *decision* pins a choice the task left open. A test that is none of these is noise, and the labels give the reviewer something concrete to check against the base-revision run: a "reproduces" test that passes on the old code is a finding.

## Lessons from real runs

loopwright was dogfooded on one project, and its loop rules in `skills/task-work/SKILL.md` come from things that went wrong.

- **A reviewer's suggested fix caused a regression.** The fix tightened one case and broke a valid one; only the next review caught it. The orchestrator now checks each suggested fix for regressions before forwarding it.
- **A YAML error hid a reviewer.** An unquoted `: ` in the agent's frontmatter description made Claude Code silently skip the agent. If an agent type is missing, check its frontmatter first.
- **A shell edit that matched nothing.** A mutation check (reintroduce the over-fix, watch the guard test fail) passed for the wrong reason, because the edit had not applied. Check the edit applied.
- **A fresh reviewer found what three approving rounds missed.** After `/reload-plugins`, a newly started reviewer found that a files command without `{files}` silently ran the whole suite. When a change touches the reviewer's own instructions or anything it runs, a fresh reviewer now reviews it.
- **Non-ASCII output crashed `run_on_base.py` on Windows only.** It happened with piped stdout, which is how an agent runs it, so it never showed in a terminal.
- **The option that fails silently looked best.** Copying the tests into the base revision looks right, but a missing helper's ImportError then looks like a correct red. Asking for alternatives found the inverse, copying everything except the fix files, which fails loudly.
- **Edited skills were read at session start.** The session kept following the old text until `/reload-plugins`. After editing a skill or an agent definition, reload before relying on it.

## Configuration

The only contract between a project and the plugin is `.claude/loopwright.md`: tasks dir, project rules file, test command, test files command, check commands, commit trailer and notes. `/loopwright:init` writes it from [`templates/loopwright.md`](templates/loopwright.md), which documents each section.

## How it compares

This is not an exhaustive list. It compares loopwright with a few of the best-known tools available as of 2026-10-05, based on each project's README and docs.

- **Superpowers** is a complete development methodology built from composable skills that trigger automatically. It covers brainstorming, plans, worktrees, TDD, code review and finishing the branch. It runs on many agent harnesses and is in Anthropic's official marketplace. loopwright covers a much smaller part of that.
  - Its code-review skill dispatches a reviewer with crafted context instead of the session history. That context includes a summary of what was built.
  - Its TDD skill enforces red by instruction ("watch it fail"). Its README describes no script that re-runs the new tests on the base revision.
  - loopwright's reviewer gets only the task, and a script supplies the red evidence.
- **TDD Guard** blocks the agent's edits in real time, through hooks, when it writes implementation without a failing test. It supports many test frameworks. Its README says it has grown into Probity, and that new projects should start there. loopwright checks after the work, not during it, and has no live enforcement.
- **taskmd** (driangle/taskmd) is a much more complete task manager. It has a CLI, a web dashboard, an MCP server and skills that run tasks. Its `verify` step runs a task's shell commands. loopwright's task files and index are deliberately plain. loopwright adds the blind reviewer and the base-revision check, which taskmd doesn't describe.

## Version and known limits

Version 0.2.0. Built and dogfooded on one project, so expect rough edges on others.

Authorship: Designed by Daniele Madaffari. The code was written by Claude Code agents under this workflow and reviewed by the author.

Known limits:

- Subagents can't invoke skills, so a project's user-facing commands must be run and checked by the orchestrating session.
- `run_on_base.py` copies whole changed files; a file that mixes test and fix code can't be split.
- Dogfooded on one project (a Python project run with uv), so other stacks are untested.

To work on the plugin itself, run from the repo root:

```
uv run pytest -q
uv run ruff check .
claude plugin validate --strict .
```

CI runs the tests and `ruff check` on Ubuntu, Windows and macOS with Python 3.10 and the latest stable, and the validate step on Ubuntu.

MIT licensed. See [LICENSE](LICENSE).
