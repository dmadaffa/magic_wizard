Analyze a Magic: The Gathering deck list and provide concise, actionable feedback.

## Input
The user provides a path to a deck list file (e.g. `decks/my_deck.txt`).

## Steps — follow in order, do not skip

### Step 1 — Parse the deck list
Run:
```
uv run python lib/deck_parser.py $ARGUMENTS
```
Read the JSON output to get the list of cards (main deck + sideboard).

### Step 2 — Populate the card cache
Extract all unique card names from the parsed deck.
Run the card fetcher sub-agent to fetch any cards not already in the cache:
```
uv run python agents/card_fetcher.py "<card1>" "<card2>" ...
```
Pass ALL unique card names in a single call. The fetcher handles cache hits itself.

### Step 3 — Load card data
Read `data/card_cache.csv`. For each card in the deck, find its row.
Build a compact card summary like:
```
4x Cinder Dart | {R} | CMC 1 | Instant | modern:legal, legacy:legal
```
Include oracle text only for non-obvious cards (i.e. skip basic lands).

### Step 4 — Analyze and respond

Produce output in this exact structure — bullet points, no prose padding:

---
**Format Legality**
- List each format (Standard / Modern / Pioneer / Legacy / Commander) and whether the deck is fully legal, noting any illegal cards by name.

**Mana Curve**
- CMC distribution: how many spells at each cost (0, 1, 2, 3, 4, 5+)
- Average CMC of non-land spells
- One sentence on whether the curve fits the apparent strategy

**Color Balance**
- Mana sources per color vs. spells requiring that color
- Flag any significant imbalances

**Synergy Notes**
- 3–5 bullet points on notable synergies or synergy gaps

**Suggestions** (top 3–5 only, be specific)
- Cut: [card name] (N copies) → Add: [replacement] — [one-sentence reason]

---

## Tone and length
- Be concise. No filler sentences.
- Assume the user knows how to play Magic.
- Flag power-level concerns only if significant.
