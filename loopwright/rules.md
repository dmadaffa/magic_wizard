# Loopwright rules

Generic rules for the `developer` and `code-reviewer` subagents. Both read this file at the start of every task, then the project rules file named in `.claude/loopwright.md`: the developer follows these rules, the reviewer checks them. Project rules add to these and win on conflict.

To add a generic rule, append a section here. Keep each rule short and say why it exists, so an agent can judge edge cases.

## Tests

- Test first: write a test that reproduces the bug or specifies the feature, run it, and confirm it fails for the expected reason before changing the code.
- Every added test (or parametrized case group) has one purpose, and the report labels it:
  - **reproduces**: fails before the fix, passes after. Every task needs at least one.
  - **guard**: passes before and after. It protects existing behaviour against a realistic over-fix (e.g. a looser regex that would also strip parts of valid input). Name the over-fix it catches.
  - **decision**: pins a choice the task left open (and may pass before). Name the choice.
  A test that passes before the fix and is none of these doesn't belong in the change.
- Test behaviour through public functions and CLI output, not private helpers or internal state.
- Mock only at the system boundary (network calls, the clock). Never mock the code under test.
- Cases that differ only in their data go in one parametrized test, not a loop or several copy-pasted tests. A loop stops at the first failure and hides the rest; parametrized cases each pass or fail on their own.

## Git

- Don't run `git stash`, `git reset`, `git checkout -- <file>`, `git restore` or `git clean`. These can silently lose uncommitted work. To look at an older version, use `git show <rev>:<path>` or a temporary `git worktree` in the scratchpad directory.
- Don't commit or push. The orchestrating session commits after review.

## Code

- Match the surrounding style: naming, comment density, idioms.
- Only change what the task needs. If you notice other problems, list them in your report; don't fix them.
- Keep the project docs and docstrings in sync when behaviour or output shape changes.
- Edit files with the Edit/Write tools, not `sed`, heredocs or inline scripts, whenever the text contains `\n`, quotes, `*` or other non-ASCII characters. Shell escaping has turned a `\n` inside a test string into a real line break and corrupted test files more than once. Shell edits are fine for simple ASCII substitutions; check the result with `git diff` either way.
