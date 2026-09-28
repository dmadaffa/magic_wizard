# Magic Wizard — MTG Deck Assistant

> **Open bug backlog:** see `BUGS.md` before starting new work. For each bug: write a failing test first (fixtures: Scryfall's real JSON shape, invented card content), then fix, then tick the box. Don't mark a bug done unless its test fails without the fix.

> **Card content is IP.** No real card names, rules text or Scryfall ids in any tracked file except this one: use invented cards in tests, fixtures, docstrings and examples. `scripts/check_ip.py` enforces it via a pre-commit hook; enable it once per clone with `git config core.hooksPath .githooks`. Names that are also plain words go in `lib/ip_allowlist.txt`. Cost and accuracy numbers: `docs/benchmarks.md`.

> **Agent workflow:** for a bug or small feature, spawn the `developer` subagent (Sonnet) with the task definition, then the `code-reviewer` subagent with the same task definition and not the developer's reasoning. Commit only after the review passes. Shared rules for both live in `docs/agent-rules.md`: add new project rules there.

Agentic system for analyzing Magic: The Gathering decks. Uses Scryfall as the card data source and a local JSON Lines cache to avoid redundant API calls.

## Quick Start

```bash
# Install dependencies (first time only)
python -m uv sync

# Analyze a deck
/analyze-deck decks/example_deck.txt
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

## How It Works

1. `lib/deck_parser.py` — parses the deck list text
2. `agents/card_fetcher.py` — fetches missing cards from Scryfall, stores in `data/card_cache.jsonl`
3. `agents/card_view.py` — prints compact per-card (and per-face) lines from the cache
4. `.claude/commands/analyze-deck.md` — orchestrator skill: parse → fetch → view cards → analyze

The card fetcher and card view are pure Python with zero LLM cost. Claude is only called once for the analysis step.

## Card Cache

Card data lives in `data/card_cache.jsonl`: one line per card with the Scryfall card object (images, prices and links stripped). Cards are fetched once and reused indefinitely.

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
```

## Upgrading to SQLite

When the JSON Lines cache gets unwieldy:
1. Create `lib/cache_sql.py` implementing the same `CardCache` interface (`get`, `put`, `get_many`)
2. In `agents/card_fetcher.py` and `agents/card_view.py`, change `from lib.cache import CardCache` to `from lib.cache_sql import CardCache`

No other changes needed.

## Project Structure

```
agents/card_fetcher.py      sub-agent: Scryfall fetch + cache write
agents/card_view.py         sub-agent: compact card lines for the analysis
lib/cache.py                CardCache class (JSON Lines)
lib/card_model.py           Card/Face model, layout + keyword access rules
lib/deck_parser.py          deck list parser
lib/scryfall.py             Scryfall API client
lib/ip_check.py             real-card-name detection (+ ip_allowlist.txt)
scripts/check_ip.py         IP check CLI, run by .githooks/pre-commit
docs/benchmarks.md          measured cost of features, with revisit thresholds
data/card_cache.jsonl       persistent card data
data/card_names.json        Scryfall name catalog for the IP check (30-day refresh)
tests/fixtures/scryfall/    invented cards in Scryfall's JSON shape
decks/                      your deck list files
.claude/commands/           Claude Code skills
.claude/agents/             developer + code-reviewer subagents
docs/agent-rules.md         rules both subagents follow / check
```
