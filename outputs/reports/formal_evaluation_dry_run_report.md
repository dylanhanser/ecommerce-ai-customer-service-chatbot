# Formal evaluation dry-run report

## Run gate

- Git HEAD: `ed6b8a2d59810e54f59615cae2bae7b06ead3650`
- API execution: not called.
- Model execution/loading/download: not performed.
- Responses are deterministic transport markers, not model answers.

## Frozen inputs

- Gold-51: `773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444`
- RQ1 schema: `dac0bcc70915106513bd059bb4fe42dd2482dc5b1c25a811151cf57df42e422b`
- RQ2 cases: `4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417`
- RQ3 cases: `c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95`
- Runner SHA-256: `27e09d61fc9c4e6e3d002ded65df41b0c566e71afb8b26f85cace2b789894f28`

## Deterministic plan and controls

- 190 units: RQ1 102, RQ2 40, RQ3 48.
- SHA-256 namespace ordering uses base seed `20260721`; IDs include protocol, RQ, case, turn, system, input, generation, and frozen-file hashes.
- Config: DeepSeek / `https://api.deepseek.com` / `deepseek-chat`; temperature 0.0, top_p 1.0, max_tokens 512, stream false, thinking not applicable.
- V1 is QA-only, 15,333 QA, Top-K 5; V2 is mixed, 15,333 QA plus 355 snippets, Top-K 10. RQ3 contrasts context disabled/enabled only.
- Payload-leak checks cover all 190 execution payloads. Gold and scoring metadata are separated.
- Fake transport validates first-success locking, resume, retry classification/max-three, and payload-mismatch blocking.

## Scoring and blinding

- RQ1 primary template: 102 rows; secondary: 22 rows over 11 paired questions.
- RQ2 template: 40 rows. RQ3 template: 48 turn rows, grouped by anonymous conversation.
- System identity and retrieval/execution metadata are absent from reviewer templates; mappings are in ignored manifests.
- All human scoring fields are blank.

## Deterministic artifacts (SHA-256)

- Request plan: `4e53f92343fd4609b7c3e1644a9075ef808dbc6af8f4c387076f915cab63a654`
- Fake-response projection: `2b74935ffc77ab5b694bc4cb3e403367634447d0370a827564ce4aab4968dd8e`
- Deterministic manifest: `c0f11556ba01ab804157d6063874c846302315385240ac6fc8cb77cdd48c5fa5`
- RQ1 primary / secondary / manifest: `8b07f34e57618a1663796bb8bac72296a4bc6367cb246d85d5648ca822c36374`, `4d231a7044a4ada58e1f3840e1d47cf2294fd416d9267a716afca2237f48a98f`, `7ad31578710d9865c8105daaa3d4b0547e4fbb686ffaaa945288d6075aff7e29`
- RQ2 template / manifest: `6fbe03f94313ea9d98232ee85ecfa4ccf05158a1ddb14e4004ae29d08a02a1f3`, `5b87cc852afcff52aa00deb35ebb95868d4484110691b5b718074888b111fa36`
- RQ3 template / manifest: `f12109fc3b20aad474f10c752cd5089a6735ed056e5d6d56bbdf78a9fc4bd64d`, `5ef7ab485602046b72b8f758be2beeba886cd41ce268f842014a6b0508cd700a`

Two independent temporary dry-runs were byte-identical for every listed deterministic artifact. Dynamic event records had equal count and status.

## Verification

- New runner suite: 8 tests passed.
- Existing formal/runtime, freeze, V2.1a, external-review, adjudication and finalization suites: 32 tests passed.
- All row-level dry-run artifacts are matched by the existing `data/` ignore rule.

## Controlled future command (not executed)

`python scripts/run_formal_evaluation.py --mode real --confirm-real-api FORMAL_EVAL_20260721`

Real mode additionally requires a clean worktree and matching frozen SHA values. This build intentionally keeps its real transport disabled.
