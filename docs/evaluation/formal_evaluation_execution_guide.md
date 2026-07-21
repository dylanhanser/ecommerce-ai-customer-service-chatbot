# Formal evaluation execution guide

Run the offline rehearsal with `python scripts/run_formal_evaluation.py --mode dry-run`.
It creates only ignored row-level artifacts under `data/formal_eval/dry_run/`. Dry-run never reads `.env`, creates a client, loads a model, downloads assets, or calls an API. Its responses begin with `DRY_RUN_NOT_MODEL_OUTPUT` and are solely plumbing markers.

The plan is SHA-256 namespace-derived from base seed `20260721`; it contains 190 immutable requests. Responses are append-safe, keyed by immutable request ID, and a first successful response is retained. A payload mismatch blocks resume; only connection failures, timeouts, 429, and 5xx are retryable (three attempts).

The future controlled command is:

`python scripts/run_formal_evaluation.py --mode real --confirm-real-api FORMAL_EVAL_20260721`

Real execution is gate-protected by a clean worktree and every frozen SHA. This build deliberately leaves the real transport disabled, so the command cannot call an API until separately implemented and approved.
