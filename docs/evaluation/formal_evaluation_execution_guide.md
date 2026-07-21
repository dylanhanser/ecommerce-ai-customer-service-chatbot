# Formal evaluation execution guide

Run the offline rehearsal with `python scripts/run_formal_evaluation.py --mode dry-run`.
It creates only ignored row-level artifacts under `data/formal_eval/dry_run/`. Dry-run never reads `.env`, creates a client, loads a model, downloads assets, or calls an API. Its responses begin with `DRY_RUN_NOT_MODEL_OUTPUT` and are solely plumbing markers.

The plan is SHA-256 namespace-derived from base seed `20260721`; it contains 190 immutable requests. RQ1/RQ2 compare `qa_only_reconstructed_baseline` with `v2`; RQ3 compares `single_turn` with `context_aware`. The baseline is a frozen QA-only reconstructed comparator based on a verifiable source blob, not a restored historical production V1 or a single-component ablation. Results are complete-system comparisons and cannot establish the causal effect of any one component.

Responses are append-safe, keyed by immutable request ID, and a first successful response is retained. A payload mismatch, including a legacy V1-labelled result, blocks resume; only connection failures, timeouts, 429, and 5xx are retryable (three attempts).

The future controlled command is:

`python scripts/run_formal_evaluation.py --mode real --confirm-real-api FORMAL_EVAL_20260721`

Before any real execution, review the pre-execution implementation-correction amendment and verify that its recorded implementation SHA values match the checked-out commit.

Real execution is gate-protected by a clean worktree and every frozen SHA. This build deliberately leaves the real transport disabled, so the command cannot call an API until separately implemented and approved. A future baseline adapter must implement only the behavior frozen in `formal_qa_only_baseline_spec.json`; it must not pass a QA-only cache to current V2 `run_rag_query()`.
