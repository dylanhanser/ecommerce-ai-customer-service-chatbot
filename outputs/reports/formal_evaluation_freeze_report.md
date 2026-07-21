# Formal Evaluation Freeze Report

## QA-only reconstructed baseline revision

The formal comparator is `qa_only_reconstructed_baseline`, not a restored historical V1. Its provenance is the earliest verifiable RAG blob (`12136b7c084e5b68dc4ca6672da20ed800a8a11b`, `outputs/rag_answer_demo.py`, blob `5906f6af2a65584af7b54d08d3e3aa252d3551ea`). It is a pre-defined QA-only complete-system comparator with controlled formal generation parameters. RQ1/RQ2 results cannot be attributed to any individual component; a separate ablation design would be required.

Superseded RQ1 schema SHA: `dac0bcc70915106513bd059bb4fe42dd2482dc5b1c25a811151cf57df42e422b`.

Current baseline spec SHA: `ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399`; revised RQ1 SHA: `a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b`; RQ2/RQ3 remain byte-identical.

PASS. The worktree began at the required HEAD with four preserved V2.1a modifications. Gold-51 SHA verified. No model, API, or download was used.

The runtime now accepts an immutable evaluation-only generation configuration. Omitted configuration retains the legacy temperature 0.2 payload. Formal evaluation explicitly passes temperature 0.0, top_p 1.0, max_tokens 512, and stream false; no thinking parameter is sent.

RQ3 compares `single_turn` (fresh state and no history per turn) with `context_aware` (shared structured state and bounded prior user/assistant text inside one dialogue). Both modes use the same runtime and generation configuration.

The fixed RQ2/RQ3 cases passed the duplicate audit: no normalized exact, SequenceMatcher ≥0.90, or bigram-Jaccard ≥0.85 blocking match against 2,604 existing-test candidates or across the new sets. The formal runtime/config tests and existing external-review protocol tests passed. Existing V2/V2.1b executable regression scripts were not run because their real call chain loads `.env` and may call DeepSeek; no explicit safe offline switch prevents that. Execution remains not started.
