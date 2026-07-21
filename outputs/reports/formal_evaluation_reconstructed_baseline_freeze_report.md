# QA-only reconstructed baseline formal freeze

## Design revision

The former unverified historical-V1 label is superseded by the frozen `qa_only_reconstructed_baseline`. It is a provenance-informed QA-only complete-system comparator, not an original production V1, an exact historical reproduction, or a single-component ablation.

Its verified provenance source is commit `12136b7c084e5b68dc4ca6672da20ed800a8a11b`, path `outputs/rag_answer_demo.py`, Git blob `5906f6af2a65584af7b54d08d3e3aa252d3551ea`, SHA-256 `2a1585575162de62de30df3fca809048f5a81878b491050e57565e548936fcdc`.

RQ1/RQ2 compare complete frozen configurations. They cannot identify the isolated causal contribution of snippets, reranking, or guards. Such claims require a separate ablation design.

## Freeze hashes

- Gold-51: `773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444`
- Baseline specification: `ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399`
- RQ1 schema: `a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b`
- RQ2 cases (unchanged): `4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417`
- RQ3 cases (unchanged): `c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95`
- Protocol: `361ff39e405846757d454c4d9f49838049b5a7996d929a580310d092316f3f1f`
- Manifest: `38f29a9714168b8b319023fb64c650e01051c7180727ac623e7c4ae8426b6d7c`

Superseded RQ1 schema SHA: `dac0bcc70915106513bd059bb4fe42dd2482dc5b1c25a811151cf57df42e422b`.

## Deterministic plan

The offline plan remains 190 response units: RQ1 102, RQ2 40, RQ3 48. Its new SHA-256 fingerprint is `4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`; it is distinct from legacy V1-labelled planning. Legacy result rows are rejected on resume.

No real transport, baseline adapter, API call, environment read, model load, download, or formal model response was performed.
