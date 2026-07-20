# Formal Evaluation Freeze Report

PASS. The worktree began at the required HEAD with four preserved V2.1a modifications. Gold-51 SHA verified. No model, API, or download was used.

The runtime now accepts an immutable evaluation-only generation configuration. Omitted configuration retains the legacy temperature 0.2 payload. Formal evaluation explicitly passes temperature 0.0, top_p 1.0, max_tokens 512, and stream false; no thinking parameter is sent.

RQ3 compares `single_turn` (fresh state and no history per turn) with `context_aware` (shared structured state and bounded prior user/assistant text inside one dialogue). Both modes use the same runtime and generation configuration.

The fixed RQ2/RQ3 cases passed the duplicate audit: no normalized exact, SequenceMatcher ≥0.90, or bigram-Jaccard ≥0.85 blocking match against 2,604 existing-test candidates or across the new sets. The formal runtime/config tests and existing external-review protocol tests passed. Existing V2/V2.1b executable regression scripts were not run because their real call chain loads `.env` and may call DeepSeek; no explicit safe offline switch prevents that. Execution remains not started.
