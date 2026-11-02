Build one 60-card deck from a pool of cards.

## Input
The user provides a path to a pool file and a format name.

Examples:
- `/build-deck decks/pool.txt Standard`
- `/build-deck output/my_deck_pool.txt Standard`

The pool file uses the deck-list format (`N Name` lines, parsed by `lib/deck_parser.py`). Each quantity is the most copies available; a bare pool can say `4` for every card. The pool has no basic lands: the skill adds them itself.

Split `$ARGUMENTS` into the **pool path** (first token) and the **format name** (all remaining tokens). Standard is the only supported format for now; for any other format, or a missing one, stop and tell the user. Don't build anything.

Rules for the whole run:
- Use only cards from the pool, plus basic lands (Plains, Island, Swamp, Mountain, Forest) that you add.
- Build from the text `card_view.py` prints, never from memory of a card and never from reasons the pool's author gave for a card.
- Never read `data/card_cache.jsonl` directly.

## Steps — follow in order, do not skip

### Step 1 — Parse, fetch and view the pool
Run:
```
uv run python lib/deck_parser.py <pool-path> "<format>"
```
stdout is the JSON document (stderr is a summary; ignore it). The pool is every card in `main`, `side`, `commander` and `companion`. Sum the quantities of a name across sections and lines (`2 X` in main plus `2 X` in the sideboard is 4 copies available); the 4-copy limit still applies.

Fetch every unique pool name plus the five basic lands (Plains, Island, Swamp, Mountain, Forest) in one call. The basics are needed because `card_view.py` and `deck_stats.py` read only the cache: without them `deck_stats.py` prints `NOT CACHED` and gives wrong Lands and Sources numbers.
```
uv run python agents/card_fetcher.py "<card1>" "<card2>" ...
```
- Cards under `Not found` (misspelled or unknown names): tell the user and drop them from the pool.
- Cards under `Not fetched (Scryfall rate limit)`: tell the user, drop them from the pool and list them in the summary as left out.
- If stderr has a `WARNING: ... older than 3 months` line, show it to the user and suggest `--refresh` for only those cards. Don't refresh on your own.

Then view every remaining pool card in one call:
```
uv run python agents/card_view.py --format "<format>" "<card1>" "<card2>" ...
```
Read the output as in `/analyze-deck` Step 3. Multi-face cards list each face with how it is reached; a back face that is not `cast` is upside of the front face, not a separate spell. A card that is not `<format>:legal` is left out of the build (reason: not legal).

### Step 2 — Choose the plan, colors and cards
- Pick one plan the pool supports best, and one or two colors (three only when the pool clearly needs them). Judge each card by its text from Step 1.
- Choose the nonland cards, at most the pool quantity of each and at most 4 copies of any card.
- Add basic lands for the colors, split by the colored pips of the chosen cards. Use 24 lands by default, fewer for a low curve; say how many and why. Nonbasic lands from the pool count as lands.
- The main deck is exactly 60 cards. No sideboard.

### Step 3 — Write the list and verify
Create `output/` if it is missing. Write `output/<pool file stem>_<YYYY-MM-DD>_built.txt` (today's date) with the Write tool, in the format the parser reads: a first line `// <Format>`, then `N Name` lines. A second build of the same pool on the same day overwrites it. Example:

```text
// Standard
4 Cinder Dart
4 Null Ripple
2 Gravel Warden
12 Mountain
```

All checks are deterministic: no extra LLM call.
1. Run `uv run python lib/deck_parser.py output/<stem>_<date>_built.txt`. The main deck must have exactly 60 cards and no sideboard. Each card except basic lands has at most 4 copies.
2. Every card name must be in the pool (with at most its pool quantity) or be a basic land.
3. Run `uv run python agents/card_view.py --format "<format>"` on every distinct card in the built list in one call. Each must show `<format>:legal`. Basic lands are legal. A card showing anything else is replaced.
4. Run `uv run python agents/deck_stats.py output/<stem>_<date>_built.txt` for the curve, colors and sources. `NOT CACHED: <name>` on stderr means a card is missing: say so.

After any fix, rewrite the file and repeat from check 1. Allow at most 2 correction rounds. If something still fails, keep the file and say exactly what fails in the summary under `Unverified:`.

### Step 4 — Summary
End the chat with this structure, short and with no prose padding:

---
**Built:** `output/<file>_built.txt` (<N> cards, format <Format>)
**Plan**
- 2–3 bullets: the strategy, the colors, and why the land count.

**Curve and colors**
- Copy `Curve:`, `Average CMC:`, `Colors (spells/pips):` and `Sources:` from `deck_stats.py`.

**Left out** (pool cards not in the deck)
- <card>: <one-line reason>

`Unverified: <what failed>` (only if a check still failed after the corrections)
---

## Tone and length
- Be concise. No filler sentences.
- Assume the user knows how to play Magic.
