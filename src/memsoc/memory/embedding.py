"""
The one embedding function. Both the write path and the read path call
embed() in this module, and nothing else in the repository loads an
embedding model.

That is the whole point of the file. A query embedded by one model and
documents embedded by another do not raise -- retrieval just returns
plausible nonsense for the rest of the run (docs/work-split.md, Person 1,
"the single most dangerous line in the layer"; risk R4 in
docs/memory-layer/06-risks-and-limitations.md). Keeping a single cached
instance here makes the invariant a property of the code rather than a
convention.

The model is a protected component (CLAUDE.md). It is pinned three ways:
by name, by the exact Hugging Face commit, and to CPU -- CPU and GPU
produce slightly different floats, which would move borderline cases
between runs.

Silent truncation
-----------------
MiniLM truncates at 256 tokens WITHOUT raising. Two different over-long
texts were measured embedding to bit-identical vectors (BL-013). So every
text is length-checked with the model's own tokenizer before it is
embedded, and an over-long text raises CaseTextTooLong. The heuristic in
case_ranker/token_estimator.py is deliberately not used here.

This module imports torch. Arm A must never reach it -- see
NullMemoryLayer in store.py.
"""

import numpy as np


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# The Hugging Face commit the project's environment checks were run
# against. Pinning it means an upstream re-upload cannot change the
# vectors underneath a run.
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

DEVICE = "cpu"

EMBEDDING_DIM = 384


class CaseTextTooLong(ValueError):
    """Raised instead of letting the model silently truncate a text."""


_model = None


def get_model():
    """
    The single shared model instance, loaded on first use.

    Loaded lazily so that importing the memory package costs nothing
    when memory is off.
    """

    global _model

    if _model is None:

        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(
            MODEL_NAME, revision=MODEL_REVISION, device=DEVICE
        )

    return _model


def token_count(text: str) -> int:
    """
    Tokens the model will actually see, special tokens included.

    Counted with the model's own tokenizer -- the only count that agrees
    with where the model truncates.
    """

    return len(get_model().tokenizer.encode(text))


def max_tokens() -> int:

    return get_model().max_seq_length


def check_length(text: str) -> int:
    """Return the token count, or raise if the model would truncate."""

    count = token_count(text)
    limit = max_tokens()

    if count > limit:
        raise CaseTextTooLong(
            f"case text is {count} tokens; the embedding model truncates "
            f"silently at {limit}. Shorten the template (BL-013)."
        )

    return count


def embed(text: str) -> list:
    """
    Length-check, then embed one text as an L2-normalised vector.

    Normalised so that cosine distance in the store is exactly
    1 - dot product.
    """

    check_length(text)

    vector = get_model().encode(
        text,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    return np.asarray(vector, dtype=np.float32).tolist()
