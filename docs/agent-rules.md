# Agent rules

The project rules file named in `.claude/loopwright.md`. The `loopwright:developer` and `loopwright:code-reviewer` subagents read it after `loopwright/rules.md` (the generic rules), at the start of every task: the developer follows these rules, the reviewer checks them.

To add a project rule, append a section here. Keep each rule short and say why it exists, so an agent can judge edge cases.

## Environment

- Windows, Git Bash. Run Python through uv: `python -m uv run pytest -q`, `python -m uv run python <script>`.
- `LF will be replaced by CRLF` warnings from git are harmless.

## Card content is IP

- No real Magic card names, rules text or Scryfall ids in any tracked file except `CLAUDE.md`. Use invented cards in tests, fixtures, docstrings, comments and examples.
- The pre-commit hook (`scripts/check_ip.py --staged`) scans **every staged file in full**, not only the changed lines. A file you touch must be completely clean, even lines you did not write. If a file you need to edit already contains real names, report it rather than working around the hook.
- Invented names can collide with real cards, even single words. Check new names before you use them: `python -m uv run python scripts/check_ip.py` (whole repo) must not report them.
- That whole-repo check only scans files git knows about, so a new untracked file reports 0 hits without being read. Run `git add -N <new files>` first (intent-to-add; it stages no content), then the check.
- Words that are both card names and plain words go in `lib/ip_allowlist.txt`. Only add ordinary words, never a distinctive name.
- `data/`, `decks/` and `tasks/` are git-ignored. You may read them locally; never quote their card content into tracked files.

## Scryfall fixtures

- Scryfall fixtures go in `tests/fixtures/scryfall/`: Scryfall's real JSON shape, invented content. Don't hand-write the structure; base it on a real API response (`curl "https://api.scryfall.com/cards/named?exact=<name>"`), then replace names, rules text, costs and ids with invented ones before committing. A hand-written double-faced-card fixture once hid a bug (`cmc` missing on faces) because the structure was wrong.

## How the generic rules apply here

- System boundary for mocks: HTTP calls to Scryfall (`lib/scryfall.py`) and the clock, including `time.sleep` in its retry path.
- Public entry points to test through: `parse`, `Card.from_scryfall`, the CLI output.
- Docs to keep in sync: `CLAUDE.md`, `.claude/commands/*.md`, docstrings.
