# Magic Wizard — MTG Deck Assistant

Agentic system for analyzing Magic: The Gathering decks. Uses Scryfall as the card data source and a local CSV cache to avoid redundant API calls.

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

Supported sideboard separators: `//`, `SB:`, or a blank line between main deck and sideboard.

## How It Works

1. `lib/deck_parser.py` — parses the deck list text
2. `agents/card_fetcher.py` — fetches missing cards from Scryfall, stores in `data/card_cache.csv`
3. `.claude/commands/analyze-deck.md` — orchestrator skill: parse → fetch → load cache → analyze

The card fetcher is pure Python with zero LLM cost. Claude is only called once for the analysis step.

## Card Cache

Card data lives in `data/card_cache.csv`. Cards are fetched once and reused indefinitely.

To manually pre-populate the cache:
```bash
python -m uv run python agents/card_fetcher.py "Card Name 1" "Card Name 2"
```

## Upgrading to SQLite

When the CSV cache gets unwieldy:
1. Create `lib/cache_sql.py` implementing the same `CardCache` interface (`get`, `put`, `get_many`)
2. In `agents/card_fetcher.py`, change `from lib.cache import CardCache` to `from lib.cache_sql import CardCache`

No other changes needed.

## Project Structure

```
agents/card_fetcher.py      sub-agent: Scryfall fetch + cache write
lib/cache.py                CardCache class (CSV-backed)
lib/deck_parser.py          deck list parser
lib/scryfall.py             Scryfall API client
data/card_cache.csv         persistent card data
decks/                      your deck list files
.claude/commands/           Claude Code skills
```
