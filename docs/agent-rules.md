# Agent rules

Project rules for the `developer` and `code-reviewer` subagents (`.claude/agents/`). Both read this file at the start of every task: the developer follows these rules, the reviewer checks them.

To add a rule, append a section here. Keep each rule short and say why it exists, so an agent can judge edge cases.

## Environment

- Windows, Git Bash. Run Python through uv: `python -m uv run pytest -q`, `python -m uv run python <script>`.
- `LF will be replaced by CRLF` warnings from git are harmless.

## Card content is IP

- No real Magic card names, rules text or Scryfall ids in any tracked file except `CLAUDE.md`. Use invented cards in tests, fixtures, docstrings, comments and examples.
- The pre-commit hook (`scripts/check_ip.py --staged`) scans **every staged file in full**, not only the changed lines. A file you touch must be completely clean, even lines you did not write. If a file you need to edit already contains real names, report it rather than working around the hook.
- Invented names can collide with real cards, even single words. Check new names before you use them: `python -m uv run python scripts/check_ip.py` (whole repo) must not report them.
- Words that are both card names and plain words go in `lib/ip_allowlist.txt`. Only add ordinary words, never a distinctive name.
- `data/`, `decks/` and `BUGS.md` are git-ignored. You may read them locally; never quote their card content into tracked files.

## Tests

- Test first: write a test that reproduces the bug or specifies the feature, run it, and confirm it fails for the expected reason before changing the code.
- Every added test (or parametrized case group) has one purpose, and the report labels it:
  - **reproduces**: fails before the fix, passes after. Every task needs at least one.
  - **guard**: passes before and after. It protects existing behaviour against a realistic over-fix (e.g. a looser regex that would also strip parts of real names). Name the over-fix it catches.
  - **decision**: pins a choice the task left open (and may pass before). Name the choice.
  A test that passes before the fix and is none of these doesn't belong in the change.
- Scryfall fixtures go in `tests/fixtures/scryfall/`: Scryfall's real JSON shape, invented content. Don't hand-write the structure; base it on a real API response, then anonymise.
- Test behaviour through public functions (`parse`, `Card.from_scryfall`, CLI output), not private helpers or internal state.
- Mock only at the system boundary (HTTP calls to Scryfall, the clock). Never mock the code under test.
- Cases that differ only in their data go in one `@pytest.mark.parametrize` test, not a loop or several copy-pasted tests. A loop stops at the first failure and hides the rest; parametrized cases each pass or fail on their own.

## Git

- Don't run `git stash`, `git reset`, `git checkout -- <file>`, `git restore` or `git clean`. These can silently discard uncommitted work. To look at an older version, use `git show <rev>:<path>` or a temporary `git worktree` in the scratchpad directory.
- Don't commit or push. The orchestrating session commits after review.

## Code

- Match the surrounding style: naming, comment density, idioms.
- Only change what the task needs. If you notice other problems, list them in your report; don't fix them.
- Keep `CLAUDE.md`, `.claude/commands/*.md` and docstrings in sync when behaviour or output shape changes.
