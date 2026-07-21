# QA-only reconstructed baseline adapter

The adapter provides `run_qa_only_baseline_query(question, resources)` for one
isolated QA-only turn.  It lazily verifies the frozen vendor snapshot (65,949
bytes; SHA-256 `2a1585575162de62de30df3fca809048f5a81878b491050e57565e548936fcdc`)
before loading it without relying on Git.

The reconstructed call chain is: initial intent/invalid guards, retrieval with
Top-K 5, vendor reranking, routing, vendor prompt/generation, and vendor final
post-processing.  The adapter never calls vendor `main` or `interactive_loop`.
Resources are injected, QA-only, cache family `v1_qa`, and state-free.  A proxy
forces the formal non-secret generation configuration while retaining vendor
prompt and generation logic.

Offline tests use only synthetic resources and a fake client.  The adapter suite
passed 18/18 tests; the related frozen-evaluation regression suites passed 19/19
tests.  They cover lazy imports, provenance verification, contract rejection,
fixed parameters, state isolation, and transport-free deterministic execution.
Known limitation: this adapter is **not integrated with formal runner**; real API
not called.
