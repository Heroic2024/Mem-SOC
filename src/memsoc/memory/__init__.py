"""
Layer 3 -- the memory layer. The single experimental variable.

    from memsoc.memory import open_memory

    mem = open_memory(run_id, condition)        # "off" | "self" | "oracle"
    cases = mem.retrieve(record, flow)
    mem.write(record, flow, verdict, seq, precedent_used)

See store.py for the three conditions and docs/memory-layer/ for the
design. Importing this package does not load torch or chromadb; only an
"on" condition does.
"""

from memsoc.memory.case_text import SCHEMA_VERSION
from memsoc.memory.store import CONDITIONS, Case, SchemaMismatch, open_memory
