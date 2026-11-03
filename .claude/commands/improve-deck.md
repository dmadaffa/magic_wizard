Improve a Standard deck with cards found by Scryfall searches that will not rotate out within 6 months.

## Input
The user provides a path to a deck list file, optionally a format name, and optionally `--card "<card>"`.

Examples:
- `/improve-deck decks/my_deck.txt Standard` (whole deck: proposals, searches, a built deck)
- `/improve-deck decks/my_deck.txt Standard --card "Cinder Dart"` (alternatives for one card)

Split `$ARGUMENTS` into the **file path** (first token), the `--card` value (the quoted text after `--card`) and the **format name** (the remaining tokens).
- Standard is the only supported format for now. For any other format, stop and tell the user. If the format is missing, use the one `lib/deck_parser.py` finds in the file (Step 1); if that is not Standard, stop.
- For an unknown flag, stop and tell the user.

Rules for the whole run:
- Card names come from Scryfall search results (`agents/improve_deck.py`), never from your memory of cards. Never invent a name.
- Judge every card by the text `card_view.py` prints. Reasons from a sub-agent are not trusted.
- Never read `data/card_cache.jsonl` directly.
- Searches run one after another, never in parallel. Create `output/` if it is missing.
- `<stem>` is the deck file's stem and `<date>` today's date (YYYY-MM-DD).

## Common steps

### Step 1 — Parse, fetch and view the deck
Run `uv run python lib/deck_parser.py <path> "<format>"` (stdout JSON; the format argument only if the user gave one). Unique names of every section go to `uv run python agents/card_fetcher.py ...` in one call, then `uv run python agents/card_view.py --format "Standard" ...` and `uv run python agents/deck_stats.py <path>`. Handle fetcher warnings, `Not found`, `Not fetched (Scryfall rate limit)` and `NOT CACHED` as `/analyze-deck` Steps 2 and 3 do. Use the names in the parser's JSON, never from the raw file (Arena exports carry `(SET) 123` suffixes that Scryfall rejects).

The deck's **color identity** is the union of the colors of its cards' `identity` fields in the `card_view.py` output, written as letters (`r`, `wu`, ...).

### Step 2 — Rotation
Run `uv run python agents/rotation_report.py <path>` and `uv run python agents/rotation_report.py --prefix`.
- `ROTATING: <name>` lines are the deck's cards that leave Standard at the next rotation. They are cards to cut.
- Any other line (rotation more than 6 months away, data out of date, report skipped) is shown to the user as it is. If stderr has a `WARNING`, pass it on: it means `data/standard_rotation.json` needs attention (see CLAUDE.md).
- The `--prefix` line is the **survival prefix**. An empty line means rotation is not active: searches use `f:standard` only. Build every query prefix as `f:standard <survival prefix> id<=<colors>` (skip the empty part).

## Deck mode (no `--card`)

### Stage 1 — Propose
From the `card_view.py` and `deck_stats.py` output and the rotating cards, propose 1 to 3 strategies or improvements, as many as the deck needs (for example "lower the curve", "lean into one mechanic", "replace the rotating cards", "fix the mana"). Each has:
- a goal
- its roles, ranked by importance
- the cards it cuts (the rotating cards go to whichever proposal fills their roles)
- optionally a new color, when the deck needs one

Show the proposals to the user in a short list, then continue; do not wait.

### Stage 2 — Search, one card-scout per proposal, one at a time
For proposal `n`, start the `card-scout` agent and wait for it before starting the next. Give it:
- the proposal (goal, ranked roles, cards to cut) and the format
- the color identity and the deck's card names
- the query prefixes written out in full. No `<x>` or other placeholders: for a new color give one concrete prefix per candidate color, for example `f:standard <survival prefix> id<=rg` and `f:standard <survival prefix> id<=rw`, with the real survival prefix text
- the paths `output/<stem>_<date>_proposal_<n>.md` and `output/<stem>_<date>_proposal_<n>.log` (delete an old `.log` of the same name first, so the log holds only this run)

Tell it to run at most 8 or 9 searches and to reply with the cards only.

**Traceability check.** After each scout, compare every returned card name with the lines of `output/<stem>_<date>_proposal_<n>.log` (for example `grep -vxFf <log> <names file>`, or by reading the log). Drop any name that is not in the log and tell the user which names were dropped and that they were not found in the scout's search results. A proposal whose scout returns no valid names is reported as empty.

### Stage 3 — Build
1. Write the pool file `output/<stem>_<date>_pool.txt`, without basic lands and deduplicated across proposals and the deck. The deck's own cards keep their quantity, summed across sections and capped at 4; scout picks get `4`. **Do not put the `ROTATING:` cards of Step 2 in the pool** (they are Stage 0's cards to cut; `/build-deck` has no rotation logic). A scout pick that is also a `ROTATING:` card is left out too. Show the user which cards each proposal added.
2. Run the `/build-deck` flow on `output/<stem>_<date>_pool.txt Standard`: follow `.claude/commands/build-deck.md` Steps 1 to 4 with these arguments. It writes `output/<stem>_<date>_pool_<date>_built.txt`.
3. After its summary, add **Given up to rotation** (only when rotation is active, i.e. Step 2 gave `ROTATING:` lines): every `ROTATING:` card left out of the pool. One line each: card, rotation date (from the "Rotation on <date>" line), what it did for the deck. The user can then choose between "best until rotation" and "rotation-safe". If rotation is not active or no card rotates, say so in one line.

End the chat with the `/build-deck` summary, the **Given up to rotation** list and the paths of the files written (proposal files, logs, pool, built deck).

## `--card` mode (no sub-agents)

Work in the main context for the one card `<card>` of the deck (it must be a card in the deck; if not, tell the user and stop).

1. **Roles**: from `card_view.py`, list the jobs the card does in this deck (mana value slot, colors, body, mana ability, fixing, counter or synergy keywords, removal), ranked by importance to the deck.
2. **Searches**: one search per role plus one combined query for cards that cover several roles, each with the prefix from Step 2 and `agents/improve_deck.py '<prefix> <role query>' --log output/<stem>_<date>_card.log` (single quotes, because queries contain double quotes; a query with an apostrophe needs `o:/.../` or a rewrite). Examples (invented): `mv<=2 t:creature o:"+1/+1 counter"`, `t:land -t:basic id=<colors>`, `-t:creature o:"destroy target creature"`.
3. **Rank** by roles covered, then body or stats against the original, color needs against `deck_stats.py` sources, and legendary or duplicate concerns. If no single card covers every role, say which role each candidate gives up.
4. **Verify**: run `card_fetcher.py` and then `card_view.py --format "Standard"` on the shortlist. Drop any card that is not `standard:legal`, and judge reasons from the printed text.
5. Output: for each role, the top 3 to 5 candidates with a one-line reason each, then the deck's rotating cards (the `ROTATING:` lines of Step 2, with a short hint what could replace each).

## Tone and length
- Be concise. No filler sentences.
- Assume the user knows how to play Magic.
