"""
Heuristic token-count estimator.

Approximates how a WordPiece/BPE tokenizer (e.g. the one
sentence-transformers/all-MiniLM-L6-v2 uses for the memory layer's
eventual embedding step) would count tokens, WITHOUT requiring
transformers/torch to be installed just to enforce a 256-token budget
here. Those packages are heavy (~1.5-2.5GB, per memory/SETUP_PLAN.md)
and are reserved for when the actual embedding step is built.

This mirrors the precedent already set in memory/SCHEMA_DESIGN.md's own
token-budget measurement (B10), which explicitly used a heuristic count
"not a tokenizer run" for the same reason, and carried the same caveat
this file repeats: the estimate is approximate, not exact. Re-verify
with the real tokenizer once sentence-transformers is installed for the
embedding step.

Rule: split on whitespace. A short, purely alphabetic word counts as
one token (WordPiece rarely splits common English/category words like
"Critical" or "Exploits"). Anything containing digits, punctuation,
underscores, or longer than 6 characters is charged roughly len/4
tokens, approximating how WordPiece shreds numbers, decimals, and
uncommon identifiers (NetFlow feature names) into multiple sub-word
pieces.
"""

import math


def estimate_tokens(text: str) -> int:

    total = 0

    for word in text.split():

        if word.isalpha() and len(word) <= 6:
            total += 1
        else:
            total += max(1, math.ceil(len(word) / 4))

    return total
