---
name: init
description: "Set up loopwright in the current project: write .claude/loopwright.md, the rules file and the tasks folders."
---

Set up loopwright in the current project.

`<python>` below means the first of `python`, `python3` whose `--version` exits 0 (some machines only have `python3`; on Windows `python3` can be a Store placeholder that fails). The script needs Python 3.10 or newer and nothing else. If no working `<python>` is found, tell the user loopwright needs Python 3.10+ and stop before writing anything.

## 1. Stop if already set up

If `.claude/loopwright.md` exists, say so and stop. Never overwrite it, and change nothing else.

## 2. Infer the settings

Look at the project root for how tests and checks are run: `pyproject.toml`, `package.json`, `Makefile`, an existing CI workflow, or similar. Propose:

- the test command;
- the test files command: the test command with a `{files}` placeholder and the runner's verbose flag (e.g. `python -m uv run pytest -v {files}`), used by the reviewer to run some test files on the base revision. If you can't tell how the runner takes files and a verbose flag, propose `none` (the test command plus the file paths is used);
- the check commands (linter, type checker, ...), each as a bullet ``- <label>: `<command>`. <criterion>``, with a pass criterion per check: "every file you touched must have zero hits" for linters and formatters that can be scoped to changed files, otherwise "exits 0".

Only propose what the project already has. Never invent a test command or a check. If nothing is found, propose none, say so, and write `none` (without backticks) for that value.

Defaults: tasks dir `tasks/`; project rules file `docs/agent-rules.md`; no commit trailer.

If the tasks dir already exists and holds other files but none of `bugs/`, `features/`, `unrefined/`, `done/` and no `INDEX.md`, it is used for something else: flag it in step 3 and suggest a different dir.

## 3. Confirm in one question

Ask the user once, showing the proposed test command, test files command, check commands with their pass criteria, tasks dir, rules file and trailer, and asking them to confirm or correct any of them. In the same question ask whether the tasks dir should be git-ignored. Recommend tracked, unless the task notes will hold data that must not be published.

## 4. Write the files

Every step only creates what is missing, so an interrupted init can be rerun. `.claude/loopwright.md` goes last: its existence is what marks the project as set up.

- If the project rules file is missing, create it (and its folder) with one header line: `# Project rules`. If it exists, leave it alone.
- Create the missing ones of `bugs/`, `features/`, `unrefined/`, `done/` under the tasks dir. Don't touch existing folders and files.
- If the user chose git-ignored, add `/<tasks dir>` (anchored to the root, e.g. `/tasks/`) to `.gitignore` (create it if needed; skip if already listed).
- Write the empty index:

  ```
  <python> "${CLAUDE_PLUGIN_ROOT}/scripts/index.py" "<tasks dir>"
  ```

  If an `INDEX.md` already exists and doesn't start with `# Task index`, don't run it: say so and leave the file. If the script exits 1, an existing task file is invalid: show the error, leave the file for the user, and stop; rerun init once it is fixed.
- Last, read `${CLAUDE_PLUGIN_ROOT}/templates/loopwright.md` and write it to `.claude/loopwright.md` (create `.claude/` if needed), replacing each `{{placeholder}}` with the confirmed value: `{{test_command}}` with the command in backticks (or `none`), `{{test_files_command}}` likewise, `{{check_commands}}` with the bullets (or `none`), `{{trailer}}` with the trailer in backticks (or `none`), `{{notes}}` with `none`, and the path placeholders with the plain paths (the template already has the backticks). Keep the section labels and the comments.

## 5. Tell the user

List what was created and what was left alone. End with the next step: `/loopwright:task-new <description>`.
