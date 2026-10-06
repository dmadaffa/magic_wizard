# Magic Wizard

An LLM-assisted deck analyzer for Magic: The Gathering. Give it a deck list; it returns concise, actionable feedback.

It is a deterministic Python pipeline plus one Claude call:

1. `lib/deck_parser.py` parses an MTGO/Arena deck list (main deck, sideboard, commander, format).
2. `agents/card_fetcher.py` fetches cards missing from the local cache from the [Scryfall](https://scryfall.com) API and stores them in `data/card_cache.jsonl`.
3. `agents/card_view.py` prints a compact line per card (and per face) from the cache.
4. The `/analyze-deck` skill ([Claude Code](https://claude.com/claude-code)) runs those steps and asks Claude to analyze the deck. This is the only LLM step; steps 1-3 make no LLM calls.

## Quick start

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/) and Claude Code.

```bash
python -m uv sync
```

Put a deck list in `decks/` (that folder is git-ignored):

```
// Modern Example Tempo
4 Cinder Dart
4 Null Ripple
// Sideboard
2 Gravel Warden
```

Then, in Claude Code:

```
/analyze-deck decks/my_deck.txt
/analyze-deck decks/my_deck.txt Modern --save
```

`--save` also writes the analysis to `output/<deck>_<date>.md`.

The format comes from a header line in the file, or from the second argument (which wins). See `CLAUDE.md` for the full deck format and the card cache details.

## Card content is not in this repo

Card names, rules text and images belong to Wizards of the Coast, so this repo contains none. Tests and fixtures use invented cards in Scryfall's JSON shape. `scripts/check_ip.py` scans the repo for real card names (using Scryfall's name catalog), a pre-commit hook in `.githooks/` runs it on staged files (`git config core.hooksPath .githooks`), and CI runs it on the tree. `check_ip.py --history` scans every blob and commit message in all refs. The card cache in `data/` is git-ignored and built on your machine.

## How it is built

The product is not agentic; the way it is built is. Features and fixes are developed by Claude Code subagents (a developer and a code reviewer) using [loopwright](https://github.com/dmadaffa/loopwright). Project rules for them are in `docs/agent-rules.md`.

## License

[MIT](LICENSE).

## Notices

Magic Wizard is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data comes from the [Scryfall](https://scryfall.com) API. Each user fetches it on their own machine and caches it locally (`data/` is git-ignored and never redistributed). Magic Wizard is not produced by or endorsed by Scryfall.

Notices checked against the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy) and Scryfall's [API documentation](https://scryfall.com/docs/api) on 2026-10-06.
