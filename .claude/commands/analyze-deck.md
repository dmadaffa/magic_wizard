Analyze a Magic: The Gathering deck list and provide concise, actionable feedback.

## Input
The user provides a path to a deck list file, and optionally a format name.

Examples:
- `/analyze-deck decks/my_deck.txt`
- `/analyze-deck decks/my_deck.txt Modern`
- `/analyze-deck inputs/draft.txt Standard`

Split `$ARGUMENTS` into the **file path** (first token) and an optional **format name** (remaining tokens, e.g. "Modern", "Standard", "Commander").

## Steps — follow in order, do not skip

### Step 1 — Parse the deck list and determine format
Run:
```
uv run python lib/deck_parser.py <file-path>
```
(Pass only the file path, not the format, to the script.)

Read the JSON output. It contains:
- `main` — list of `{qty, name}` for main deck cards
- `side` — list of `{qty, name}` for sideboard cards
- `format` — format name extracted from the deck's title comment, or `null`

**Active format**: use the explicit format argument if one was provided; otherwise fall back to the `format` field from the JSON; otherwise treat as unknown.

### Step 2 — Populate the card cache
Extract all unique card names from both `main` and `side`.
Run the card fetcher sub-agent to fetch any cards not already in the cache:
```
uv run python agents/card_fetcher.py "<card1>" "<card2>" ...
```
Pass ALL unique card names (main + sideboard) in a single call. The fetcher handles cache hits itself.

### Step 3 — Load card data
Read `data/card_cache.csv`. For each card in the deck, find its row.
Build two compact card lists using the format:
```
4x Cinder Dart | {R} | CMC 1 | Instant | modern:legal, legacy:legal
```
Include oracle text only for non-obvious cards (skip basic lands).

**Main deck** — list all main deck cards.
**Sideboard** — list all sideboard cards (omit this section if `side` is empty).

### Step 4 — Analyze and respond

Produce output in this exact structure — bullet points, no prose padding:

---
**Format Legality** (active format: _<format or "unknown">_)
- If format is known: state whether the deck is fully legal in that format, noting any illegal cards by name.
- If format is unknown: list legality across Standard / Modern / Pioneer / Legacy / Commander and highlight the most permissive format where the deck is fully legal.

**Mana Curve** (main deck only)
- CMC distribution: how many spells at each cost (0, 1, 2, 3, 4, 5+)
- Average CMC of non-land spells
- One sentence on whether the curve fits the apparent strategy

**Color Balance**
- Mana sources per color vs. spells requiring that color
- Flag any significant imbalances

**Synergy Notes**
- 3–5 bullet points on notable synergies or synergy gaps

**Sideboard** (omit entirely if sideboard is empty)
- Total sideboard cards and the matchups / threats each card addresses
- Coverage gaps: matchups or archetypes the sideboard does not address
- Off-plan cards: any sideboard cards that seem mismatched for the main deck's strategy

**Suggestions** (top 3–5 only, be specific)
- Cut: [card name] (N copies) → Add: [replacement] — [one-sentence reason]

---

## Tone and length
- Be concise. No filler sentences.
- Assume the user knows how to play Magic.
- Flag power-level concerns only if significant.
