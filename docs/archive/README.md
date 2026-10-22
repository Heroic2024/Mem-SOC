# Archive

Superseded documents, kept for history. **Nothing here is current** — every
file carries a banner saying what replaced it.

| File | Superseded by | Why |
|---|---|---|
| `docker-single-image-stack.md` | [`../deployment/operations.md`](../deployment/operations.md) | Documented the root `Dockerfile` / `docker-compose.yml` single-image stack, deleted in the 2026-09-20 restructure. |
| `operations-legacy.md` | [`../deployment/operations.md`](../deployment/operations.md) | Earlier, shorter ops guide that duplicated the current one. Reconciliation tracked as **BL-062**. |
| `testing-protocol-v1.md` | [`testing-protocol-v2.md`](./testing-protocol-v2.md), itself superseded by [`../status/testing-protocol-v3.md`](../status/testing-protocol-v3.md) | One parser fix (a verdict wrapped in a JSON array), so the protocol version and tag moved to `p2` / `memsoc-protocol-v2`. **BL-125.** |
| `testing-protocol-v2.md` | [`../status/testing-protocol-v3.md`](../status/testing-protocol-v3.md) | A per-model output cap (Gemma 16,384) and a retry for transient API errors, so the protocol version and tag moved to `p3` / `memsoc-protocol-v3`. **BL-126.** |

If you are looking for how to run MemSOC today, start at
[`../README.md`](../README.md).
