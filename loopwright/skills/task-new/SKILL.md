---
name: task-new
description: "Create a task file from a free-text description and regenerate the task index."
argument-hint: "<description>"
---

Create a task from this description: `$ARGUMENTS`

## 1. Read the settings

Read `.claude/loopwright.md` for the tasks dir. Never assume it.

## 2. Work out the shape

From the description, infer:

- `type`: `bug`, `task` or `story`.
- `mode`: `auto` when an agent can do it with no further input, `human` when a decision or a step only the user can do is open.
- Open decisions: anything the description leaves to choose, each with a recommendation.

Record open decisions with a recommendation; ask the user only if the type or the goal itself is unclear.

## 3. Write the file

`<python>` below means the first of `python`, `python3` whose `--version` exits 0 (some machines only have `python3`; on Windows `python3` can be a Store placeholder that fails). The script needs Python 3.10 or newer and nothing else.

Get the id:

```
<python> "${CLAUDE_PLUGIN_ROOT}/scripts/index.py" "<tasks dir>" --next-id
```

If this exits 1, an existing task file is invalid: show the error and fix that file first.

Folder:

- `unrefined/`, with `mode: human`, if any decision is open.
- Otherwise `bugs/` for `type: bug`, and `features/` for a task or a story.

File name: `NNN-slug.md`, with the id zero-padded to three digits and a short kebab-case slug.

Front matter needs `type`, `mode` and `status: open`. Add `priority` (high, medium, low or backlog), `depends` and `parent` only when they apply. Write them as `depends: [12, 14]` and `parent: 12`: flow lists only, since a YAML block list fails `index.py`.

Body, in this order:

- `# N. Title`: the index reads the title from this heading.
- `## Goal`, or `## Problem` for a bug.
- `## Decisions`: the settled ones.
- `## Open decisions`: only if any are open, each with a recommendation. A task with any open decision goes to `unrefined/` with `mode: human`.
- `## Changes`: what to change, concretely enough for a developer to start.
- `## Done when`: checkable conditions, including any check only the orchestrator can run.

## 4. Update the index

```
<python> "${CLAUDE_PLUGIN_ROOT}/scripts/index.py" "<tasks dir>"
```

If it fails, fix the file it names and run it again. Then tell the user the id, the path, and the open decisions if any.
