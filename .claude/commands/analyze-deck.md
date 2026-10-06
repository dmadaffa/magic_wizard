Analyze a Magic: The Gathering deck list and provide concise, actionable feedback.

## Input
The user provides a path to a deck list file, and optionally a format name and flags.

Examples:
- `/analyze-deck decks/my_deck.txt`
- `/analyze-deck decks/my_deck.txt Modern`
- `/analyze-deck decks/draft.txt Standard`
- `/analyze-deck decks/my_deck.txt Modern --save` (also writes the analysis to `output/`)

Split `$ARGUMENTS` into the **file path** (first token), **flags** and an optional **format name**:
- Tokens starting with `--` are flags. They can appear anywhere after the path (`decks/x.txt Modern --save` and `decks/x.txt --save Modern` mean the same).
- `--save` is the only known flag. For an unknown flag, stop and tell the user; don't pass it on.
- The remaining non-flag tokens are the format name (e.g. "Modern", "Standard", "Commander"), passed to Step 1 as before. Never pass a flag to the parser.

## Steps — follow in order, do not skip

### Step 1 — Parse the deck list and determine format
Run:
```
uv run python lib/deck_parser.py <file-path> ["<format>"]
```
Pass the format only if the user provided one, with all remaining tokens as one quoted argument (e.g. `"Pauper Commander"`). It overrides the format found in the file header. Without it, omit the argument.

stdout is the JSON document (the script prints a human-readable summary to stderr; ignore it). Read the JSON. It contains:
- `main` — list of `{qty, name}` for main deck cards
- `side` — list of `{qty, name}` for sideboard cards
- `commander` — list of `{qty, name}` for the commander(s), empty if none
- `companion` — list of `{qty, name}` for the companion, empty if none (Arena also lists it in `side`)
- `format` — the active format: the format argument if one was passed, otherwise the format from the header lines before the first card (comment or plain line, whole word, first mention wins), or `null` (unknown)

**Active format**: the `format` field of the JSON, nothing else. `null` means unknown.

### Step 2 — Populate the card cache
Extract all unique card names from `commander`, `companion`, `main` and `side`.
Run the card fetcher script to fetch any cards not already in the cache:
```
uv run python agents/card_fetcher.py "<card1>" "<card2>" ...
```
Pass ALL unique card names (every section) in a single call. The fetcher handles cache hits itself.

### Step 3 — Load card data
Run the card view for all unique card names (every section) in a single call:
```
uv run python agents/card_view.py "<card1>" "<card2>" ...
```
Do not read `data/card_cache.jsonl` directly. The output has one block per card:
```
Cinderquill Volley | {R} | CMC 1 | identity R | Instant | standard:not_legal, modern:legal, ...
    Cinderquill Volley deals 2 damage to any target.
Tidewatch Apprentice // Tidewatch Horror | transform | CMC 1 | identity U | standard:not_legal, ...
  [face 1: cast] Tidewatch Apprentice | {U} | Creature — Human Apprentice | 1/2
    At the beginning of your upkeep, ...
  [face 2: transform] Tidewatch Horror | Creature — Horror | 3/3
    Flying
```
Multi-face cards list each face with how it is reached:
- `cast` — can be cast from hand for that face's cost (MDFC faces, adventure and split halves)
- `transform`, `disturb`, `daybound`, `craft`, `more_than_meets_the_eye` — reached by transforming, not cast from hand for its cost
- `prepared` — the spell copy cast while the creature is prepared
- `flip`, `meld` — reached by flipping / melding

For the **mana curve**, count each card at its `CMC` (for split cards this is the combined cost), and note cheaper `cast` faces (e.g. an adventure half or an MDFC land face) as flexibility. Treat back faces that are not `cast` as upside of the front face, not as separate spells.

Build two compact card lists prefixed with quantity (`4x ...`), keeping face lines for multi-face cards.
Include oracle text only for non-obvious cards.

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

### Step 5 — Save (only with `--save`)
Skip this step without `--save`; nothing is written.

With `--save`: create `output/` if it is missing, then write `output/<deck file stem>_<YYYY-MM-DD>.md` (today's date) with the Write tool. A second save of the same deck on the same day overwrites that file. The file holds:
- a short header: deck name (the file stem), date, active format (`unknown` if `null`) and the source path
- the Step 4 sections, word for word as shown in chat

Then end the chat with one line: `Saved: output/<file>.md`.

## Tone and length
- Be concise. No filler sentences.
- Assume the user knows how to play Magic.
- Flag power-level concerns only if significant.
