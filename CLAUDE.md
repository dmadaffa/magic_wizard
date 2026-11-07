# Magic Wizard — MTG Deck Assistant

> **Tasks:** read `tasks/INDEX.md`, then only the task file you need. For each bug: write a failing test first (fixtures: Scryfall's real JSON shape, invented card content), then fix. Don't mark a bug done unless its test fails without the fix. Mark it done by setting `status: done`, moving the file to `tasks/done/` and regenerating the index. `/loopwright:task-work` and `/loopwright:task-new` regenerate it; by hand, run `python <plugin>/scripts/index.py tasks/`, where `<plugin>` is the installed copy, `~/.claude/plugins/cache/loopwright/loopwright/<version>` (`--next-id` prints the next free id). `tasks/` is git-ignored. `/loopwright:task-work [id]` runs a task end to end (pick, developer, reviewer, commit, close); `/loopwright:task-new <description>` creates a task file and updates the index.

> **Card content is IP.** No real card names, rules text or Scryfall ids in any tracked file, this one included (only `uv.lock` and the allowlist are exempt): use invented cards in tests, fixtures, docstrings and examples. `scripts/check_ip.py` enforces it via a pre-commit hook; `check_ip.py --history` scans every blob and commit message in all refs. Enable the hook once per clone with `git config core.hooksPath .githooks`. The same hook runs `ruff check` on staged `.py` files (version and rules pinned in `pyproject.toml`; run `python -m uv run ruff check .`). Names that are also plain words go in `lib/ip_allowlist.txt`. Cost and accuracy numbers: `docs/benchmarks.md`.

> **Agent workflow:** for a bug or small feature, spawn the `loopwright:developer` subagent (Sonnet) with the task definition, then the `loopwright:code-reviewer` subagent with the same task definition and not the developer's reasoning. Commit only after the review passes. The agents come from the `loopwright` plugin (https://github.com/dmadaffa/loopwright, installed via `.claude/settings.json`). Generic rules for both live in the plugin's `rules.md`; project rules live in `docs/agent-rules.md` (add new project rules there); `.claude/loopwright.md` tells the agents where those are and which test and check commands to run.

LLM-assisted analyzer for Magic: The Gathering decks: a deterministic Python pipeline (parse the deck list, fetch and cache cards from Scryfall, print a compact card view) plus one Claude analysis step (`/analyze-deck`; `/improve-deck` in deck mode runs 1 to 3 sub-agents plus a build step). Uses Scryfall as the card data source and a local JSON Lines cache to avoid redundant API calls.

## Quick Start

```bash
# Install dependencies (first time only)
python -m uv sync

# Analyze a deck (create decks/my_deck.txt first, see "Adding a Deck"; decks/ is git-ignored)
/analyze-deck decks/my_deck.txt

# Also write the analysis to output/<deck>_<date>.md, plus replacements, alternative
# strategies and a suggested list (also output/<deck>_<date>_suggested.txt)
/analyze-deck decks/my_deck.txt Modern --save

# Rotation-safe improvements from Scryfall searches, then a built deck (Standard)
/improve-deck decks/my_deck.txt Standard

# Build one 60-card Standard deck from a pool file (writes output/<pool>_<date>_built.txt)
/build-deck decks/pool.txt Standard
```

## Adding a Deck

Create a `.txt` file in `decks/` using standard MTGO/Arena format:

```
4 Cinder Dart
4 Null Ripple
// Sideboard
2 Gravel Warden
```

Supported sideboard separators: `// Sideboard`, a `Sideboard` line, or an `SB:` prefix. Arena section headers (`Commander`, `Companion`, `Deck`, `Sideboard`) are recognized. A blank line starts the sideboard only when the file has none of these markers; otherwise blank lines just group cards.

The format is read from the header lines before the first card: a comment like `// Modern Zorbling Tempo` or a plain line like `Standard Deck`. Matching is case-insensitive and whole-word (`Premodern` and `Pre-Modern` are not `Modern`; `Pauper-legal` is `Pauper`), and the first format mentioned wins. Bare Arena section headers (`Commander`, `Deck`, ...) don't set a format; for those exports pass the format to `/analyze-deck` (e.g. `/analyze-deck decks/my_deck.txt Pioneer`). The skill forwards it to `lib/deck_parser.py`, which overrides the header format; the JSON `format` field is the single source of truth. The script prints only JSON on stdout and a human-readable summary on stderr.

## How It Works

1. `lib/deck_parser.py` — parses the deck list text
2. `agents/card_fetcher.py` — fetches missing cards from Scryfall, stores in `data/card_cache.jsonl`
3. `agents/card_view.py` — prints compact per-card (and per-face) lines from the cache
4. `agents/deck_stats.py` — mana curve, color pips and mana sources of the main deck (rules in `lib/stats.py`)
5. `.claude/commands/analyze-deck.md` — orchestrator skill: parse → fetch → view cards → deck stats → analyze

The card fetcher, card view and deck stats are pure Python with zero LLM cost. Claude is only called once for the analysis step.

## Improving and building decks (Standard)

- `/improve-deck <deck> Standard` proposes 1 to 3 strategies, runs one `card-scout` sub-agent per proposal (`.claude/agents/card-scout.md`, Bash + Read/Write only, Sonnet), then builds a deck from the deck's cards plus the scouts' picks with `/build-deck`. `--card "<card>"` finds alternatives to one card instead, with no sub-agents. Card names come only from Scryfall searches (`agents/improve_deck.py`, which logs every result name per proposal; the skill drops returned names missing from the log).
- `/build-deck <pool file> Standard` builds one 60-card deck from a pool of cards plus basic lands.
- `data/standard_rotation.json` (tracked) holds `next_rotation`, the `rotating` set codes and the `evergreen` set codes. Edit it by hand when Wizards announces a rotation (about once a year): set the new date and the codes that leave. Surviving sets are derived from Scryfall's `/sets`. Cards are flagged only when the rotation is within 6 months; once the date has passed, `agents/rotation_report.py` warns that the file is out of date.

## Card Cache

Card data lives in `data/card_cache.jsonl`: one line per card with the Scryfall card object (images, prices and links stripped). Cards are fetched once and reused; the fetcher warns on stderr when a cached card is older than 3 months (legality changes with rotations and bans) but does not re-fetch it. Re-fetch named cards with `--refresh`; a failed refresh keeps the old entry and warns. Uncached cards are fetched in batches of 75 (`/cards/collection`, matched by name or face name, case-insensitive), one cache write per batch; names a batch doesn't return are retried one by one with `/cards/named`, and names differing only in whitespace are requested once.

Card names are whitespace-normalized as cache keys (ends trimmed, inner runs collapsed to one space, case kept); `CardCache` does this, so callers can pass names as they have them.

Don't flatten Scryfall data when storing it. `lib/card_model.py` turns the stored object into a `Card` with `Face`s, so new mechanics are handled there without re-fetching.

## Multi-face cards and new mechanics

Each face has *access modes* describing how it gets into play (`cast`, `transform`, `prepared`, `flip`, `meld`, ...). In `lib/card_model.py`:
- `LAYOUT_ACCESS` maps a Scryfall `layout` to per-face modes. A new layout (like `prepare`) is one entry.
- `KEYWORD_ACCESS` adds modes from keywords, for cards that mix mechanics (e.g. a `modal_dfc` whose front face can also transform).
- Unknown layouts fall back to "front face castable" and emit a warning.

Add a fixture to `tests/fixtures/scryfall/` (an invented card in Scryfall's real JSON shape, never real card text) and a case to `tests/test_card_model.py` for every new mechanic.

To manually pre-populate the cache:
```bash
python -m uv run python agents/card_fetcher.py "Card Name 1" "Card Name 2"
# Re-fetch cards whose legality may be stale
python -m uv run python agents/card_fetcher.py --refresh "Card Name 1" "Card Name 2"
```

`agents/card_view.py [--format "Pauper Commander"]` prints only that format's legality: the name is lowercased with spaces and hyphens removed and looked up in Scryfall's legalities (`unknown` if there is no such key, e.g. Explorer or Draft). Without `--format` it prints standard, modern, pioneer, legacy and commander.

## Upgrading to SQLite

When the JSON Lines cache gets unwieldy:
1. Create `lib/cache_sql.py` implementing the same `CardCache` interface (`get`, `put`, `put_many`, `get_many`), keying every entry by `lib.cache.normalize_name`
2. In `agents/card_fetcher.py`, `agents/card_view.py` and `agents/deck_stats.py`, change `from lib.cache import CardCache` to `from lib.cache_sql import CardCache`

No other changes needed.

## Releasing

Tags are `vX.Y.Z` and match `version` in `pyproject.toml`.
1. Bump `version` in `pyproject.toml` (it also sets the Scryfall User-Agent), commit and push `main`.
2. Tag it: `git tag -a vX.Y.Z -m "Magic Wizard X.Y.Z"`.
3. Publish the tag: `git push origin vX.Y.Z`.
4. Create a GitHub release from the tag, titled "Magic Wizard X.Y.Z".

## Project Structure

```
agents/card_fetcher.py      script: Scryfall fetch + cache write
agents/card_view.py         script: compact card lines for the analysis
agents/deck_stats.py        script: curve, colors and mana sources of the main deck
agents/improve_deck.py      script: Scryfall search with compact lines and a result-name log
agents/rotation_report.py   script: deck cards rotating out of Standard (--prefix: survival search filter)
lib/stats.py                deck statistics (pure functions over Cards)
lib/rotation.py             Standard rotation: data/standard_rotation.json -> search filters, status
lib/cache.py                CardCache class (JSON Lines)
lib/card_model.py           Card/Face model, layout + keyword access rules
lib/deck_parser.py          deck list parser
lib/scryfall.py             Scryfall API client
lib/ip_check.py             real-card-name detection (+ ip_allowlist.txt)
scripts/check_ip.py         IP check CLI, run by .githooks/pre-commit
.githooks/pre-commit        pre-commit hook: IP check on staged files + ruff on staged .py files
.github/workflows/ci.yml    CI: tests, ruff and the IP check on the tree
docs/benchmarks.md          measured cost of features, with revisit thresholds
data/card_cache.jsonl       persistent card data
data/standard_rotation.json hand-edited next rotation date + rotating/evergreen set codes (tracked)
data/scryfall_sets.json     /sets cache, refreshed after 1 day
data/card_names.json        Scryfall name catalog for the IP check (30-day refresh)
tests/                      pytest suite
tests/fixtures/scryfall/    invented cards in Scryfall's JSON shape
decks/                      your deck list files
output/                     saved analyses and built decks, git-ignored
.claude/commands/           Claude Code skills (analyze-deck, build-deck, improve-deck)
.claude/agents/             card-scout sub-agent
.claude/loopwright.md       project-to-plugin contract: tasks dir, rules file, test/check commands, commit trailer
.claude/settings.json       enables the loopwright plugin from its GitHub marketplace
docs/agent-rules.md         project rules the subagents follow / check
tasks/                      task files by folder (bugs, features, unrefined, done) + generated INDEX.md; git-ignored
```
