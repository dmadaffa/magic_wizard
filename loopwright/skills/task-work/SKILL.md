---
name: task-work
description: "Work one task from the task queue end to end: pick it, spawn the developer and code-reviewer agents, run review rounds, commit, and close the task."
argument-hint: "[id]"
---

Work one task from the queue: `$ARGUMENTS` (a task id, or empty to take the next one).

You are the orchestrator. The developer and reviewer agents do the work; you pick, judge, ask the user, commit and close. The process matters as much as the fix, so follow these steps in order.

## 1. Read the settings

Read `.claude/loopwright.md`. It gives the tasks dir, the project rules file, the test command, the check commands, the commit trailer and project notes. Use those values everywhere below; never assume them. Then read `INDEX.md` in the tasks dir.

## 2. Pick the task

- Given an id:
  - Done or nonexistent (not in the index, no file): say so and stop.
  - In `unrefined/`: say it needs triage first, and stop.
  - Any of its `depends` still open: say which ones, and stop. That is not a triage case.
  - Otherwise use it.
- No id: take the lowest-id task in the open table that is `mode: auto`, is not in `unrefined/`, and has no `depends` that are still open. The open table includes `in-progress` rows. The `depends` column of the index is enough to tell; an id missing from the open table is done. If nothing qualifies, say so and stop.

Read only that task file. Its body is the spec.

If it is `status: in-progress`, a previous run may have stopped midway: ask the user whether that run left changes in the working tree, and resume from there instead of starting over.

## 3. If the task is `mode: human`

Open decisions live in a section whose heading starts with `## Open decisions` (it may carry a suffix); settled ones live under `## Decisions`.

Ask the user each question in the open section, with a recommendation each. Use the AskUserQuestion tool when there are a few discrete options. Move each answer, verbatim, into `## Decisions`. Remove the open section once it is empty. Then set `mode: auto`, unless a step only the user can do remains (below), and regenerate the index (see step 7 for the command), which also validates the edit.

If the task needs a step only the user can do (an install, a restart), say so, keep `mode: human`, and ask the user to do that step at the point it is needed.

## 4. Mark it in progress

Set `status: in-progress` in the task file and regenerate the index.

## 5. Develop and review

Reproduce first: a bug or feature starts with a test that fails for the expected reason. Then the fix. Then your own review of the diff.

1. Spawn `loopwright:developer`. Give it the task file's path and its full content, plus any decisions taken in this run.
2. When it reports `done`, spawn `loopwright:code-reviewer` with the same path, content and decisions. Never give the reviewer the developer's report or reasoning: it must judge the diff against the task alone. If the developer reports `blocked` or `partial`, stop and ask the user instead.
3. Run review rounds. Resume the same developer and the same reviewer with SendMessage so they keep context. Use fresh agents for each new task. Expect 2 to 3 rounds; findings are mostly about test labels and grouping, rarely about the code.
4. Check the developer's report shows the reproducing test failing before the fix (when the task has one), and read the diff yourself before committing.

Rules for the loop:

- Put the user's decisions into the task definition verbatim.
- When a fix raises a new behaviour question, stop and ask the user. Do not let the agents choose.
- Judge each reviewer finding before forwarding it, and check its suggested fix for regressions: a fix that tightens one case can break a valid one, and only the next review would catch it.
- To reject a finding, resume the reviewer with the reason, or tell the user if it is a judgement call.
- When you apply small review fixes yourself, check each new guard test by reintroducing the over-fix in a scratchpad copy and watching the test fail. Also check the edit actually applied: a silent no-op edit can make that check pass for the wrong reason.
- If an agent type is missing or skipped, check its frontmatter first; a YAML error (for example `: ` inside an unquoted description) hides it.
- Related-case coverage is a question for you as well as the reviewer: does the test fail without the fix, and does the fix cover the cases next to it?
- After a change edits a skill or an agent definition, ask the user to run `/reload-plugins` (or start a new session) before you rely on the new text. Skills and agent definitions are read at session start, so the session keeps following the old text until a reload. Only the user can run it; agents cannot.
- When the change edits the reviewer's own instructions or anything the reviewer runs, step 6 always includes a review by a fresh `code-reviewer`, added if the Done when doesn't ask for one. It runs after the reload, if the rule above applied, and gets only the standard brief of step 5 (task path, content and decisions; nothing about what changed). If it finds something, later rounds resume that fresh reviewer, not the step-5 one. An approving round can miss what a reviewer reading only the updated instructions finds, and a fresh run also shows that the updated instructions work on their own.

## 6. Run the orchestrator checks

Run the checks the task's Done when assigns to the orchestrator (for example commands only the session can run, since subagents cannot invoke skills). Look at the result. On failure, resume the developer, then run another review round on the new change (step 5) and repeat this step.

## 7. Create the commit and close

Gate: no blocking or should-fix finding remains, each one was either fixed or rejected with a reason; the orchestrator checks of step 6 pass; and the test and check commands from the settings pass by the criterion the settings give (a check can be scoped to touched files, for example).

- Record each optional finding you did not apply as a note in the task file, or as a new task with `/loopwright:task-new`.
- Stage only the files this change touched, by name. Never `git add -A`.
- Message: first line `<title> (#id)`, then a short body, then a blank line, then the configured trailer.
- Never use `--no-verify`. If a pre-commit hook fails, fix the cause and commit again. One task, one commit.

Then set `status: done` in the task file, move it to `done/` in the tasks dir, and regenerate the index. `<python>` below means the first of `python`, `python3` whose `--version` exits 0 (some machines only have `python3`; on Windows `python3` can be a Store placeholder that fails).

```
<python> "${CLAUDE_PLUGIN_ROOT}/scripts/index.py" "<tasks dir>"
```

The script needs Python 3.10 or newer and uses only the standard library, so it needs no project runner. The tasks dir may be git-ignored; if so, do not try to commit it.

Report to the user: the task, the commit, any optional findings left open, and anything you noticed.
