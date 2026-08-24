# Formal Evaluation Stage B4 Implementation Plan

**Status:** APPROVED AND FROZEN — the first complete plan was initially `DRAFT`; the first independent review returned `CHANGES_REQUIRED`; B4-1 and B4-2 were corrected; the correction candidate completed; focused independent rereview token `STAGE_B4_PLAN_FOCUSED_REREVIEW_PASS` returned verdict `PASS` for the exact pre-finalization reviewed candidate SHA-256 `96457b8ba98f035e7b0d9fef7a7b09e276335f19032ec5442f2c4433815835d6`; this approval authorized only lifecycle finalization. Stage B4 implementation and the plan-publication commit remain separately unauthorized and pending.

**Stage:** B4 — offline production-resource preflight.

**Document role:** approved-and-frozen implementation plan only. Approval and freeze do not authorize Stage B4 implementation, the real production-resource probe, production-resource access, Stage B5, credentials or Provider access, network access, client construction, real or canary mode, formal evaluation, or response generation.

Normative words such as **must**, **must not**, **may**, and **should** define the approved-and-frozen technical contract for a separately authorized future implementation; they do not themselves grant implementation authority. A decision marked **NEW-B4** is an approved B4-specific plan contract; it is not a previously frozen fact and does not authorize implementation or execution.

## 1. Status, purpose, and authority

### 1.1 Exact purpose

Stage B4 will provide one deterministic, offline, fail-closed preflight for the local production resources needed by the already frozen formal-evaluation systems. It will answer only this question:

> Do the fixed local source files, cached corpora, cached embeddings, local embedding-model snapshot, and relevant runtime dependencies form a present, internally consistent, locally usable, unchanged snapshot whose exact identities can be presented to a later authorization stage?

Passing B4 will produce evidence about an observed resource snapshot. It will not approve that snapshot, authorize a formal run, make a run authoritative, or establish a model result.

### 1.2 Relationship to the formal-evaluation stages

- The formal-evaluation protocol and pre-execution amendments remain the umbrella research authorities.
- Stage A remains authoritative for the formal-system registry, generation and transport contracts, `ProductionResourceIdentity`, resource counts, path syntax, cache-family binding, and production-versus-synthetic identity rules.
- Stage B1 remains authoritative for system dispatch, injected runtime-resource binding, dialogue orchestration, and checkpoint semantics.
- Stage B2 remains authoritative for the offline fake-only durable private store, run contract, inflight recovery, locking, and canonical private commits. B4 neither changes nor opens that store.
- Stage B3 remains authoritative for the blinded reviewer-output projection from eligible canonical private commits. B4 neither changes nor opens the private evidence or reviewer-projection roots.
- Stage B4 is only the production-resource preflight described here.
- Stage B5 owns real authorization and eventual guarded real-client integration. Section 14 lists the explicit deferrals.

The tracked `docs/evaluation/formal_evaluation_protocol.md` is the master protocol. The staged implementation boundary is further established by the completed B2 and B3 plans and their committed implementations. No separate tracked document currently supplies a more specific B4 resource contract; this plan therefore derives it from those authorities and the current resource-loading code.

### 1.3 Authority order and ambiguity rule

For B4, the later implementation must apply this precedence:

1. an explicit task authorization for that invocation;
2. repository `AGENTS.md` safety and research-integrity boundaries;
3. frozen formal protocol, amendments, manifest, baseline specification, and Stage A/B1/B2/B3 contracts;
4. this plan, but only after independent approval/freeze;
5. current implementation behavior and focused tests where the higher authorities are silent.

Older wording that broadly says the runner “loads resources,” “uses production,” or “resumes evaluation” must not be read as permission to cross a later stage boundary. This plan's narrower B4 prohibitions control B4 once approved. Any conflict with a frozen identity, plan fingerprint, formal-system mapping, generation parameter, or evidence contract is a blocker; B4 must not silently reinterpret it.

The first complete plan was initially `DRAFT`. Its first independent review returned `CHANGES_REQUIRED`; B4-1 (runtime priority compatibility) and B4-2 (the optional-import boundary) were corrected, and the correction candidate completed. The exact pre-finalization reviewed candidate, SHA-256 `96457b8ba98f035e7b0d9fef7a7b09e276335f19032ec5442f2c4433815835d6`, subsequently received focused independent rereview token `STAGE_B4_PLAN_FOCUSED_REREVIEW_PASS` with verdict `PASS`. That approval applies to the exact reviewed candidate and authorized only this lifecycle finalization. The plan is approved and frozen; implementation and the plan-publication commit remain separately unauthorized and pending.

## 2. Scope and non-goals

### 2.1 In scope

B4 will:

- resolve only the fixed repository-relative production source and cache paths already named by tracked code;
- resolve the exact local cache location for the already selected embedding model using the installed Sentence Transformers/Hugging Face cache rules in Section 4.4;
- validate lexical and resolved path boundaries before content access;
- require fixed files/directories to exist with the expected types and no forbidden redirections;
- hash required source, corpus, embedding, model-snapshot, authority, and implementation files without emitting their content;
- safely load the minimum structures needed to prove cached corpus, NumPy embedding, and local model compatibility;
- validate exact counts, shapes, cache metadata, source links, model binding, and cross-family invariants;
- construct all four Stage A production resource identities and validate them through Stage A's public validators;
- return an immutable in-memory result;
- publish or reopen one canonical, sanitized, non-authorizing B4 evidence artifact after a completely successful fresh validation;
- detect change during an invocation and preserve all inputs;
- be safe to invoke repeatedly.

For unchanged files, installed dependency versions, model-cache configuration, and B4 authority files, the classification and evidence bytes must be deterministic. Filesystem timestamps and wall-clock time must not enter the evidence.

### 2.2 Required operating properties

B4 must remain:

- offline;
- deterministic for unchanged validation inputs;
- read-only with respect to source data, production caches, model snapshots, and B2/B3 evidence;
- non-generative;
- Provider-free;
- credential-free;
- fail-closed;
- safe for repeated invocation;
- bounded to a local, single-user MSc evaluation tool.

Publishing the B4 evidence file is the only proposed persistent write. It occurs in a dedicated B4 evidence root, not in a production-resource or B2/B3 root.

### 2.3 Explicit non-goals

B4 must not:

- read `outputs/.env` or any other credential source;
- enumerate arbitrary environment variables or resolve an API key;
- import or construct an OpenAI-compatible or Provider client;
- call a Provider, DNS resolver, socket, HTTP library, or network service;
- use real mode, run a canary, or generate a formal response;
- invoke an evaluator, reviewer, B3 projection, or statistical analysis;
- authorize B5 or implement any B5 workflow;
- create a B2 run contract, acquire the B2 run-wide lock, open/recover the B2 store, or open/recover B3 projection state;
- change formal-system identity, request identity, plan content or fingerprint, response projection, success semantics, reviewer output, metrics, or generation parameters;
- mutate, repair, rebuild, re-encode, redownload, replace, quarantine, normalize, or delete a production resource;
- call `outputs.rag_answer_demo.load_or_create_cache`, any demo `main`, or any loader that can create a directory or rebuild a cache;
- read frozen evaluation cases, Gold rows, candidate pools, formal answers, or row-level B2/B3 evidence;
- establish that cached embeddings are semantically ideal or independently reproduce them by rebuilding;
- install or update a dependency.

## 3. Current architecture and dependency inventory

### 3.1 Existing authority and call surfaces

The implementation review established the following current architecture:

| Concern | Current authority/surface | B4 use |
|---|---|---|
| Formal systems and resource identity | `scripts/formal_evaluation_transport.py` | Reuse `validate_registry()`, `formal_identity()`, `ProductionResourceIdentity`, `validate_resource_identity()`, and `resource_identity_sha256()`; never call `parse_deepseek_config()` or Provider code. |
| Frozen systems and generation metadata | `evaluation/formal_evaluation_manifest.json`, the formal protocol, and amendments | Hash and validate only safe metadata required by B4; do not change it or read case rows. |
| Reconstructed baseline | `evaluation/formal_qa_only_baseline_spec.json`, `scripts/formal_qa_only_baseline/adapter.py`, and its frozen vendor module | Confirm the baseline's fixed `v1_qa`, model, count, dimension, and top-k binding. Do not call the query adapter because it requires a client. |
| V2 cache construction contract | `outputs/rag_answer_demo.py` | Treat its fixed paths, filenames, source-hash algorithm, cache attributes, column construction, model ID, and normalization behavior as resource-format evidence. Do not call its mutating loader. |
| Runtime consumption | `scripts/formal_evaluation_runtime.py` | Validate that the resources B4 observes have the injected shapes and model behavior the runtime expects. Do not invoke a dialogue or generation path. |
| B1 orchestration | `scripts/formal_evaluation_orchestration.py` | Preserve its resource-family and top-k dispatch contract; no orchestration call is required. |
| Interactive/school-demo launch | `app.py`, `outputs/rag_retrieval_demo.py`, `README.md`, and `docs/requirements.md` | These confirm local dependency/model/cache expectations but are not formal B4 loaders. B4 does not invoke their model-by-ID, cache-building, UI, or Provider paths. |
| B2 private execution | `scripts/formal_evaluation_store.py`, `scripts/formal_evaluation_inflight.py`, and the B2 plan/amendment | Reuse design conventions for strict JSON, Windows path checks, create-only publication, and locking. Do not reuse the fixed fake-only B2 builder or open its root. |
| B3 reviewer projection | `scripts/formal_evaluation_review_projection.py` and the B3 plan | Preserve its non-synthetic source-eligibility gate and create-only evidence conventions. Do not open its source or output roots. |
| Current runner | `scripts/run_formal_evaluation.py` | Its real gate remains disabled. B4 will not add a runner mode. |

### 3.2 Physical resources identified by tracked code

`outputs/rag_answer_demo.py` identifies these production paths and formats:

| Resource | Canonical repository-relative path | Format/role |
|---|---|---|
| Cleaned QA source | `data/processed/jd_final_safe_qa_refined_category.csv` | Raw source whose SHA-256 binds both cache families. |
| Reviewed snippet source | `data/processed/knowledge_snippets_v2_reviewed.csv` | Additional raw source for the mixed V2 family. |
| V1 corpus | `outputs/cache/v1_qa/qa_corpus.pkl` | Pandas pickle, QA-only cached corpus. |
| V1 embeddings | `outputs/cache/v1_qa/qa_embeddings.npy` | NumPy embedding matrix. |
| V2 corpus | `outputs/cache/v2_mixed/mixed_corpus_v2.pkl` | Pandas pickle, QA rows followed by snippet rows. |
| V2 embeddings | `outputs/cache/v2_mixed/mixed_embeddings_v2.npy` | NumPy embedding matrix. |
| Embedding model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Exact local Sentence Transformers snapshot, 384 dimensions. |

The demo also has a fallback QA path and command-line path overrides. Those are interactive-demo conveniences and are not permitted B4 production identities. B4 uses only the canonical paths above.

### 3.3 Formal mappings already frozen by Stage A

| `system_config_id` | `formal_system_id` | cache family | top-k | B4 physical family |
|---|---|---:|---:|---|
| `qa_only_reconstructed_baseline` | `qa_only_reconstructed_baseline` | `v1_qa` | 5 | V1 |
| `v2` | `current_v2` | `v2_mixed` | 10 | V2 |
| `single_turn` | `v2_without_context_management` | `v2_mixed` | 10 | V2 |
| `context_aware` | `v21b_context_aware` | `v2_mixed` | 10 | V2 |

One V1 and one V2 physical snapshot therefore yield four distinct Stage A identities. The three V2 identities must contain identical resource hashes and counts while retaining their distinct system identifiers.

### 3.4 Resource-family disposition

| Family | Disposition | Reason |
|---|---|---|
| Cleaned QA and reviewed snippet source files | Required for B4, hash-only | Current cache validity binds cache attributes to raw source hashes. B4 need not parse row content or rebuild. |
| V1/V2 corpus pickles | Required for B4, bounded safe-load | Runtime needs their structured rows and attrs; metadata-only file hashing cannot prove pandas/runtime compatibility. |
| V1/V2 NumPy embeddings | Required for B4, read-only mmap plus bounded full validation | Runtime needs exact shapes, finite float data, and normalized rows. |
| Exact local embedding-model snapshot | Required for B4, bounded local-only load | A cache can be structurally valid while the runtime model is absent or unusable. |
| Frozen manifest, baseline specification, B4 plan, and named implementation authorities | Required for B4, hash and safe metadata only | They bind the evidence to the code/contract that interpreted it. |
| Installed Python/runtime dependencies | Required for B4 | The repository declarations are not pinned; exact installed versions and successful imports/probes are the available compatibility evidence. |
| `outputs/.env`, API key, base URL, Provider model/client settings | Deliberately outside B4 | Stage B5. |
| Formal case files, Gold files, acceptable-response rules, request plan, reviewer material | Outside B4 | They do not establish production retrieval-resource usability. Their frozen contracts remain unchanged. |
| B2 private commits and B3 projections | Outside B4 | Their presence affects later lifecycle stages, not resource preflight. |
| DeepSeek response cache or any generated output | Irrelevant/forbidden | B4 is non-generative. |

There is no tracked frozen SHA for the current production corpus files, embedding files, or local model snapshot. Section 7 addresses this without inventing one: B4 records a freshly validated observational identity, and a later stage must separately authorize that exact evidence. B4 does not call an observed hash “approved” or “frozen.”

### 3.5 Dependency inventory

The implementation will require only dependencies already declared or already required by the application: Python, NumPy, pandas, scikit-learn, sentence-transformers, transformers, huggingface-hub, and torch. The evidence records exact installed versions under these canonical names:

`python`, `numpy`, `pandas`, `scikit-learn`, `sentence-transformers`, `transformers`, `huggingface-hub`, `torch`.

The parent discovers dependency versions without importing any optional package. Under Python 3.11 it obtains the Python version from `platform.python_version()` and calls only the standard-library `importlib.metadata.version(distribution_name)` for the seven distribution names above, mapping `importlib.metadata.PackageNotFoundError` to `B4_DEPENDENCY_UNAVAILABLE`. It must not use `importlib.import_module()`, `__import__()`, `importlib.util.find_spec()`, or a package import as a discovery mechanism. NumPy and pandas are imported only by the resource worker; NumPy, scikit-learn, sentence-transformers, transformers, huggingface-hub, and torch are imported only by the model worker, after Section 6.3 controls are active. A required worker import or required-symbol failure is also `B4_DEPENDENCY_UNAVAILABLE` under the precedence in Section 8.

No B4 semver range is invented. Metadata discovery plus successful imports and the explicit cache/model probes establishes compatibility. B4 will not change `outputs/requirements.txt` or any dependency declaration.

Every recorded version is a 1–128 character ASCII string matching `^[0-9A-Za-z][0-9A-Za-z._+!-]{0,127}$`; an absent or unsafe version string is `B4_DEPENDENCY_UNAVAILABLE`. This prevents package metadata from becoming a path/content leak while preserving normal PEP 440 and local build versions.

## 4. Production-resource contract

### 4.1 Contract sources and identifiers

The minimum B4 resource contract is derived as follows:

- canonical source/cache paths, cache filenames, cache attributes, column construction, source-hash algorithm, model ID, and normalized float32 creation: `outputs/rag_answer_demo.py`;
- formal system/cache-family mapping, exact production identity fields, counts, dimension, relative-path syntax, and identity hashing: `scripts/formal_evaluation_transport.py`;
- baseline family/model/count/top-k: the baseline specification, adapter, and vendor snapshot;
- runtime usability: `scripts/formal_evaluation_runtime.py`;
- dependency declarations: `outputs/requirements.txt`.

The B4 evidence contract identifier will be the literal `formal_production_resource_preflight_v1` (**NEW-B4**). The stage literal will be `B4`, schema version will be integer `1`, and a passing status will be the literal `passed`.

### 4.2 Repository path and file contract

The parent module must derive the repository root from its own tracked location. The public API and CLI accept no resource-root, evidence-root, model, file, or URL override. Private test-only seams may substitute a complete path bundle only from `tmp_path`/OS temporary storage.

For source and cache resources, the implementation must:

1. validate each authority string with Stage A-compatible canonical POSIX relative-path rules;
2. join it beneath the derived repository root without `expanduser()` or environment interpolation;
3. reject `.`/`..`, alternate separators, drive/UNC/device syntax, URI syntax, percent expansion, trailing separators, and NUL characters;
4. resolve and verify that every component remains beneath its exact expected root (`data/processed`, `outputs/cache/v1_qa`, or `outputs/cache/v2_mixed`);
5. reject a symlink, junction, mount-point redirection, or Windows reparse point in any production source/cache component;
6. require each leaf to be one regular file, not a directory, device, FIFO, or socket;
7. repeat type/reparse checks before and after content validation.

The source and cache files each have a 268,435,456-byte maximum (**NEW-B4**). The cap is a guard against accidental wrong-file selection and unbounded deserialization, not an expected exact size. Independent review must confirm that it is proportionate before approval; a real production probe must fail rather than relax it.

### 4.3 Exact family contracts

#### V1 QA-only

- Cache family: `v1_qa`.
- Identity corpus version: `production_v1_qa_only` (**NEW-B4**, required because Stage A production identities require a `production_` prefix).
- Cache attr `corpus_version`: `v1_qa_only` (existing core contract).
- Corpus: `outputs/cache/v1_qa/qa_corpus.pkl`.
- Embeddings: `outputs/cache/v1_qa/qa_embeddings.npy`.
- Counts: 15,333 rows, 15,333 QA, 0 snippets.
- Embedding shape: `(15333, 384)`.
- Cache attr `source_sha256`: ordinary SHA-256 of the raw QA source bytes.

#### V2 mixed

- Cache family: `v2_mixed`.
- Identity corpus version: `production_v2_mixed` (**NEW-B4**, for the same Stage A prefix requirement).
- Cache attr `corpus_version`: `v2_mixed` (existing core contract).
- Corpus: `outputs/cache/v2_mixed/mixed_corpus_v2.pkl`.
- Embeddings: `outputs/cache/v2_mixed/mixed_embeddings_v2.npy`.
- Counts: 15,688 rows, 15,333 QA, 355 snippets.
- Embedding shape: `(15688, 384)`.
- Cache attr `source_sha256`: the existing `combined_source_hash` result, calculated in the exact order QA then snippets as ordinary SHA-256 over:
  `qa_basename_utf8 || qa_sha256_lowercase_ascii || snippet_basename_utf8 || snippet_sha256_lowercase_ascii`.

For both families:

- cache attr `model_name` must equal `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`;
- the corpus must be a pandas `DataFrame` with `RangeIndex(start=0, stop=row_count, step=1)`;
- the exact ordered columns must be:
  `doc_id`, `source_type`, `category`, `title`, `text_for_embedding`, `answer_or_content`, `question`, `answer`, `priority`, `allowed_for_answer`, `needs_backend_api`, `source_file`, `session_id`;
- `doc_id` must be non-empty and unique;
- `text_for_embedding` and `answer_or_content` must be non-empty after string stripping;
- every `allowed_for_answer` value must be true and every `needs_backend_api` value must be Boolean;
- every required `priority` value must satisfy the one runtime-compatibility predicate below, and every QA-row priority must normalize to the tracked builder's fixed value `50`;
- V1 rows and the first 15,333 V2 rows must have `source_file == "jd_final_safe_qa_refined_category.csv"` and `source_type == "chat_qa"`;
- the final 355 V2 rows must have `source_file == "knowledge_snippets_v2_reviewed.csv"` and a non-empty `source_type`;
- V1 must equal the first 15,333 V2 rows across all 13 ordered columns using `DataFrame.equals()`; attrs are compared separately;
- no row value, difference, or sample may leave the worker or enter a public error.

The exact priority predicate is derived from the two tracked builders and both frozen rerank paths. The builders place Python integers in the cached `priority` column: every QA row receives `DEFAULT_QA_PRIORITY == 50`, while each included snippet row receives the result of the existing integer conversion without a further bound. Both rerankers then apply `int(priority)` and `max(0.0, (priority - 50) / 500.0)`. Accordingly, a cached priority is compatible if and only if it is present; is a non-null scalar; is a Python `int` or NumPy integer scalar; is neither `bool` nor `numpy.bool_`; converts through `int(value)` without error; and the exact rerank arithmetic above completes with a finite result. Strings, floats, `None`, pandas/NumPy missing sentinels, NaN, Boolean values, arrays, containers, and other scalar types are incompatible even if Python could coerce some of them. After this predicate succeeds, every QA value must equal `50`. Snippet values have no new B4 range or bound: any value satisfying the predicate is accepted. B4 must not use the runtime's falsey fallback to excuse an absent, null, Boolean, or invalid cached value.

A missing `priority` column is the existing exact-column `B4_IDENTITY_MISMATCH`. A present value that fails the compatibility predicate is `B4_RESOURCE_INCOMPATIBLE`; this check runs before the QA fixed-value check. A compatible QA value other than `50` is `B4_IDENTITY_MISMATCH`. The worker may return only aggregate booleans proving that all priorities passed and all QA priorities were `50`; it must not return or persist a priority value, range, minimum, maximum, sample, row identifier, or offending payload.

The embeddings must be a NumPy `.npy` array that loads with `allow_pickle=False` and `mmap_mode="r"`; has exactly two dimensions and the family shape above; has native `float32` dtype; contains only finite values; and has every row L2-normalized within absolute tolerance `1e-3` (**NEW-B4**, directly reflecting the existing `normalize_embeddings=True` construction). Validation must scan in bounded row chunks and must not copy the entire matrix solely to test norms.

### 4.4 Local embedding-model contract

The exact model ID is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. B4 must not accept an alternative alias or CLI model path.

To mirror the current library's cache selection without importing sentence-transformers, transformers, huggingface-hub, torch, or any other optional package, the parent uses only Python 3.11 standard-library `os.environ.get()`, `os.path.expanduser()`, and `pathlib`. It may inspect only these non-secret path settings and must not print their values: `SENTENCE_TRANSFORMERS_HOME`, `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `HF_HOME`, and `XDG_CACHE_HOME`. Empty values are absent. Cache-root resolution is the first applicable item:

1. `SENTENCE_TRANSFORMERS_HOME`;
2. `HF_HUB_CACHE`;
3. `HUGGINGFACE_HUB_CACHE`;
4. `<HF_HOME>/hub`;
5. `<XDG_CACHE_HOME>/huggingface/hub`;
6. expanded `~/.cache/huggingface/hub`;
7. no fallback search outside that one resolved root.

This is path derivation, not dependency discovery or package import. The same lexical, resolved-containment, and non-disclosure checks apply to the selected root.

The exact model repository directory is `models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2`. `refs/main` must be a regular, non-reparse text file containing exactly one lowercase 40-hex commit revision plus an optional final LF. The selected directory must be exactly `snapshots/<revision>` beneath that model repository.

Ordinary files in the selected snapshot are allowed. Hugging Face snapshot-file symlinks are allowed only when each resolved target is a regular file beneath the same model repository root (normally its `blobs` directory). Directory symlinks, junctions, other reparse directories, dangling links, escapes, devices, and URLs are forbidden. `trust_remote_code` must be false. No code file may be imported from the snapshot as custom remote code.

The logical snapshot is bounded to at most 4,096 files and 2,147,483,648 total resolved bytes (**NEW-B4**). The snapshot tree hash is:

```text
SHA256(
  UTF8("formal-evaluation-b4-model-tree-v1\0") ||
  for each logical regular-file path in ascending Unicode POSIX-path order:
      U64BE(len(UTF8(path))) || UTF8(path) ||
      U64BE(file_size) || RAW32(SHA256(file_bytes))
)
```

The parent must hash the logical tree before and after the model probe and require the same revision, file set, sizes, targets, and hash.

The worker must then instantiate `SentenceTransformer` from the exact resolved snapshot directory, not from the model ID, with `local_files_only=True`, `trust_remote_code=False`, `token=False`, and `backend="torch"`. It must encode the exact synthetic sentinel `formal-evaluation-b4-offline-probe-v1` with `convert_to_numpy=True`, `normalize_embeddings=True`, and no progress bar. The result must have exact dtype `float32`, shape `(1, 384)`, only finite values, and unit norm within `1e-3`. The worker must also run the installed `sklearn.metrics.pairwise.cosine_similarity` on the probe against itself and require a finite `(1, 1)` result within `1e-5` of `1.0` (**NEW-B4**). Only booleans, dtype, shapes, and the probe identifier may leave the worker; neither vector nor similarity value may leave it.

The model revision and B4 tree hash are observed identity fields, not a claim that a currently unrecorded revision was previously frozen.

### 4.5 Production identities

After all physical checks, B4 constructs exactly four `ProductionResourceIdentity` values in this order:

1. `qa_only_reconstructed_baseline`;
2. `v2`;
3. `single_turn`;
4. `context_aware`.

Each value must use:

- `schema_version = 1`;
- `resource_type = "production_frozen"`;
- `synthetic = false`;
- the Stage A `system_config_id`, `formal_system_id`, and cache family;
- the exact repository-relative corpus/embedding paths in Section 3.2;
- ordinary raw-file SHA-256 values calculated by B4;
- the B4 identity corpus version from Section 4.3;
- exact Stage A counts and dimension;
- the exact model ID.

`logical_resource_id` must be the Stage A-derived literal `production_frozen_<cache_family>_<corpus_version>`. Every identity must pass `validate_resource_identity()`, and its hash must be calculated only by `resource_identity_sha256()`. B4 must not replace or “improve” Stage A's existing canonical-JSON hash with a new domain.

### 4.6 Hash domains and cross-resource invariants

- Raw source, corpus, embedding, and authority-file identities are ordinary lowercase SHA-256 of exact bytes.
- The legacy V2 combined source hash remains the existing concatenation in Section 4.3; B4 must not domain-separate or reinterpret it.
- Stage A resource identity hashes remain Stage A's existing canonical hash.
- Only the new model-tree and B4 evidence self-hashes use the new B4 domains defined here.

The final candidate must prove all of these cross-resource invariants:

1. each cache attr source hash matches the fixed raw source file(s);
2. each cache attr model and core corpus version match its family;
3. corpus counts match Stage A and the `source_file` partition;
4. every cached priority satisfies the single Section 4.3 runtime-compatibility predicate and every QA priority is exactly `50`;
5. embedding rows match corpus rows and Stage A; dimensions equal 384;
6. V1 is the exact QA prefix of V2;
7. all three V2 formal identities have the same physical paths, hashes, counts, version, and model;
8. the baseline identity uses only V1;
9. the local model probe dimension matches the embedding dimension;
10. the runtime cosine-similarity probe is locally usable;
11. all before/after hashes and path/type checks match;
12. network, Provider, client-construction, and generation attempt counts are zero.

## 5. Preflight sequencing

The implementation must perform phases in this exact order. It stops on the first classified failure and publishes no passing artifact.

1. **Bootstrap and platform gate.** Start stdlib-only, set `sys.dont_write_bytecode = True`, require supported Windows behavior, derive the repository and B4 evidence roots from module locations, reject public arguments other than `--help`, and install the parent no-network guard before importing the stdlib-only Stage A authority module. The parent never imports an optional data/model package.
2. **Authority gate.** Validate the Stage A registry and the fixed B4 authority-path list lexically. Hash the named tracked authorities once. Do not open any frozen row-level fixture.
3. **Configuration resolution.** Resolve only the fixed repository paths and the allowlisted model-cache settings in Section 4.4. Do not inspect `.env` or Provider configuration.
4. **Lexical/boundary validation.** Validate relative strings, resolved containment, overlap, symlink/reparse policy, and exact permitted roots before reading production content. Validate the existing B4 evidence layout read-only if it already exists; an unknown member or malformed final evidence fails closed.
5. **Existence/type/size validation.** Require all source, corpus, embedding, model-ref, and snapshot paths and bounds. A missing resource is not rebuilt or downloaded.
6. **Metadata-only dependency discovery.** The parent reads the Python version and the exact installed distribution versions only through the Section 3.5 Python 3.11 standard-library mechanisms. It does not import or probe an optional package. Missing or unsafe metadata is `B4_DEPENDENCY_UNAVAILABLE`; no installation or fallback is attempted. Actual optional imports are deferred to the applicable scrubbed worker.
7. **First identity pass.** Hash raw source, corpus, embedding, authority, and logical model-snapshot bytes; read the model revision; derive the legacy combined source hash. Store only hashes, sizes, and safe identifiers.
8. **Structural resource worker.** In one isolated worker invocation, establish every Section 6.3 control, import pandas and NumPy, load both corpora and both matrices read-only, and validate attrs, schema, counts, partitions, the priority predicate/QA fixed value, finite/norm properties, and the V1/V2 prefix invariant. Receive only bounded aggregate JSON.
9. **Local model worker.** In a separate isolated worker invocation, establish every Section 6.3 control, import the required local data/model stack, load the exact local snapshot, run the synthetic embedding probe, and receive only bounded aggregate JSON.
10. **Formal identity and compatibility gate.** Construct and validate the four Stage A identities, identity hashes, baseline binding, runtime dimension, and every cross-resource invariant.
11. **Second identity pass.** Repeat authority, source, corpus, embedding, model-ref, snapshot-tree, type, and reparse observations. Any difference is `B4_RESOURCE_MUTATED`; discard the candidate.
12. **Canonical candidate construction.** Build and recursively validate the exact schema in Section 7, calculate its self-hash, and enforce byte limits. No timestamp is added.
13. **Short publication unit of work.** Only now create/open the fixed B4 evidence root, acquire its B4 lock, rescan the evidence layout, clean only recognized B4-owned temp files, and publish create-only or reopen an exact existing artifact. Production files are not opened under this lock.
14. **Final readback and result.** Read back and strictly validate the final artifact. Return `created` or `already_complete`; emit only the sanitized public result.

### 5.1 Position in the wider formal lifecycle

B4 is pre-lock dependency validation. It runs before any future real authorization, real-client construction, B2 run-wide lock, first production run-contract creation, Provider request, or response generation. It does not take the B2 lock because lengthy file/model validation under that lock would couple independent state and would not prevent external resource mutation.

B4 does not reopen or recover B2/B3 state. In a future authorized workflow, B2 reopening/recovery remains governed by B2 under its own lock, and B3 reopening/recovery remains governed by B3 after eligible B2 completion. A B4 pass can coexist with absent, partial, complete, or malformed B2/B3 state; it says nothing about that state.

The minimum interface handed toward B5 is the immutable result's evidence hash and four validated identities. B5 must decide, under its own separately reviewed authority, how to bind a fresh result to authorization and a production run contract. The existence of a B4 artifact alone must never make a formal run authoritative.

## 6. Safe loading and offline enforcement

### 6.1 What is only inspected

- Raw QA/snippet sources: exact path/type/size and full raw-byte hash only. B4 does not parse their CSV rows because the cache attrs already define the existing provenance link and rebuilding is forbidden.
- Authority/configuration files: exact path/type/size/hash plus only already public safe metadata required by the contract. Frozen row-level fixtures are not opened.
- Installed dependencies: Python's version plus bounded distribution-version metadata through Python 3.11 standard-library `platform` and `importlib.metadata` only. The parent does not import an optional distribution to inspect it.
- Model ref and tree: ref text, paths, sizes, link targets, and full file hashes. No model file content is logged.
- Existing B4 evidence: strict bounded JSON parse only.

### 6.2 What must be loaded and why

The corpus pickles must be fully deserialized because file hashes and pickle opcode/header inspection cannot prove that pandas can produce the exact DataFrame, attrs, columns, index, and values consumed by the runtime. The embedding arrays must be opened because `.npy` header bytes alone cannot prove all values are finite and normalized. The model must be instantiated and used once because directory presence alone cannot prove Sentence Transformers/torch compatibility or a 384-dimensional local encode.

The worker reads the complete pickle payloads, the `.npy` headers plus all embedding rows in bounded chunks, and the model files required by the library. It performs no broader row inspection than the exact aggregate predicates in Section 4.3. Optional import and probe compatibility cannot be established by parent-side metadata, so those imports occur only inside the applicable worker.

### 6.3 Worker boundary

`scripts/formal_evaluation_resource_preflight_worker.py` will have two private modes selected only by a fixed parent-generated invocation: `resource` and `model`. It is stdlib-only until the controls below are complete and is not a user-facing production CLI. The parent supplies a bounded, allowlisted argument set and a newly created temporary directory, launches the worker with a newly constructed allowlisted environment, applies the time/output limits, and never sends an evidence/output path.

Before importing pandas, NumPy, scikit-learn, sentence-transformers, transformers, huggingface-hub, torch, or any other optional data/model package, each worker must, using only the standard library:

- install a process-wide guard that rejects `socket.socket`, `socket.create_connection`, and `socket.getaddrinfo`, increments a local attempt counter, and raises a B4-internal offline exception;
- validate the bounded mode-specific arguments and establish bounded stdout/stderr handling before third-party code can write;
- change to the newly created OS-temporary working directory;
- validate and re-establish the allowlisted subprocess environment containing only Windows/Python execution essentials and the explicit offline/cache variables, removing no value into output and rejecting any forbidden credential, Provider, token, proxy, API-key, or authorization setting;
- set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, and `TOKENIZERS_PARALLELISM=false`;
- set `PYTHONDONTWRITEBYTECODE=1` and direct `TEMP`, `TMP`, `PYTHONPYCACHEPREFIX`, `HF_HOME`, `HF_HUB_CACHE`, `TRANSFORMERS_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `TORCH_HOME`, and `XDG_CACHE_HOME` beneath that worker's OS-temporary directory;
- omit token, proxy, API-key, auth-header, `.env`, and Provider variables;
- receive only already validated absolute input paths over parent-created arguments, never a URL.

Only after every applicable control is active may the resource mode import NumPy and pandas, or the model mode import NumPy, scikit-learn, sentence-transformers, transformers, huggingface-hub, and torch. The worker must not import the demo module, a Provider/client package, or an environment loader. Test-only injected import hooks must observe the socket guard, scrubbed environment, offline variables, temporary cache roots, temporary current directory, and bounded output redirection already active at the first optional import.

The parent also installs its own socket guard. Any attempted DNS/socket operation is `B4_OFFLINE_VIOLATION`, even if a library would otherwise catch it.

Worker stdout is exactly one canonical JSON object plus LF, limited to 32,768 bytes (**NEW-B4**); stderr is discarded at the public boundary; wall time is limited to 300 seconds per mode (**NEW-B4**); nonzero exit, timeout, extra output, duplicate keys, noncanonical JSON, or schema mismatch fails closed. Neither worker output schema contains a free-text exception or path field.

Each worker redirects third-party stdout/stderr before importing and while probing, then emits only its own final object. Success uses exact top-level fields `schema_version`, `status`, `probe`, and `result`, with values `1`, `passed`, `resource|model`, and the fixed aggregate result schema. The resource result includes only the aggregate booleans `priority_values_runtime_compatible == true` and `qa_priority_fixed_50 == true`; it never includes a priority value or distribution. A known failure uses exactly `category`, `schema_version`, and `status`, where `status == "failed"` and `category` is one of `B4_DEPENDENCY_UNAVAILABLE`, `B4_RESOURCE_MALFORMED`, `B4_RESOURCE_INCOMPATIBLE`, `B4_IDENTITY_MISMATCH`, or `B4_OFFLINE_VIOLATION`; it exits `2`.

Missing parent metadata, an unsafe version string, or failure to import a required optional package/symbol under fully active controls and with zero network attempts is `B4_DEPENDENCY_UNAVAILABLE`. This includes missing modules and local binary-extension/DLL import failures, but never exposes the caught exception. A detected DNS/socket/remote/token/remote-code attempt remains `B4_OFFLINE_VIOLATION`, rather than being relabelled as dependency unavailability. A crash, signal/forced termination, failure JSON with any other category, or missing valid object maps to `B4_INTERNAL_FAILURE`, except a parent-observed launch/read/timeout failure maps to `B4_IO_FAILURE`. Worker text never becomes the parent exception text.

### 6.4 Deserialization and malformed-input boundary

Pandas pickle is executable serialization. B4 cannot turn an untrusted pickle into a safe format without rebuilding or changing the frozen runtime resource. Therefore:

- a later production invocation requires explicit authorization of the exact cache root before any pickle load;
- path, reparse, type, and size gates run first;
- the load occurs in a fresh credential-free, network-blocked subprocess with a temporary current directory;
- the worker imports no Provider code and receives no output/evidence path;
- the parent accepts only the fixed aggregate schema;
- every exception or wrong type/schema becomes a sanitized failure;
- every optional-package import failure becomes only `B4_DEPENDENCY_UNAVAILABLE` when the Section 6.3 zero-network condition holds;
- the subprocess is an isolation/bounding measure, not a claim of an adversarial-code sandbox.

This is proportionate to trusted, locally generated dissertation artifacts. B4 must not describe arbitrary third-party pickle loading as safe. If independent review cannot accept the origin trust assumption, implementation is blocked until an authoritative non-executable cache format or frozen hash is approved; it must not silently add a brittle pickle-global allowlist.

NumPy loading always uses `allow_pickle=False`. Model loading uses the exact local path and disabled remote code. Memory remains bounded by the stated file/tree caps, read-only mmap and chunking for embeddings, one corpus-worker process, one model-worker process, and sequential—not concurrent—worker execution.

### 6.5 Content sanitization

The worker may compute only aggregate counts, booleans, shapes, hashes, and fixed identifiers. It must never return or log:

- a corpus cell, query, answer, retrieved text, document ID, source row, or differing value;
- an embedding value/vector;
- a priority value, range, minimum, maximum, sample, row identifier, or invalid priority payload;
- a model tensor, weight name, cache path, or configuration payload;
- a traceback, package-internal exception, exception message, local absolute path, `repr` of loaded objects, environment value, credential, or model-cache content.

The parent discards worker stderr and maps failure to Section 8. Public output contains no absolute path. Tests must force representative exceptions containing synthetic secret/path/row markers and prove none cross the boundary.

## 7. B4 result and artifact contract

### 7.1 Why both forms are required

B4 needs both:

1. an immutable in-memory result for a same-process caller; and
2. a durable, sanitized evidence artifact for audit between the separately authorized production probe and later authorization.

An in-memory-only result would leave no reviewable record of the exact observed hashes, dependency versions, or model revision. The durable file is nevertheless observational evidence, not a new frozen authority and not run authorization. A later stage may rely on it only after a fresh B4 invocation returns the same self-hash and that stage applies its own authorization rules.

### 7.2 Fixed location and layout

The production B4 evidence root is:

`data/formal_eval/resource_preflight`

Its only permitted durable members are:

- `run.lock`;
- `production_resource_preflight_v1.json`.

The only recognized temporary filename is:

`.production_resource_preflight_v1.json.<32 lowercase hex>.tmp`

The broad existing `data/` ignore rule already covers this root; no `.gitignore` change is needed. The B4 root must not overlap source/cache/model/B2/B3 roots. Unknown members, reparse points, aliases, or path overlap fail closed.

### 7.3 Exact in-memory result

The public module will expose one frozen dataclass:

```python
ProductionResourcePreflightResultV1(
    schema_version: int,                  # exactly 1
    action: str,                          # "created" or "already_complete"
    status: str,                          # exactly "passed"
    preflight_sha256: str,                # 64 lowercase hex
    resource_identities: tuple[ProductionResourceIdentity, ...],  # exactly four
)
```

The tuple order is Section 4.5. Construction validates exact types/literals and defensively owns the tuple. The result contains no absolute paths or loaded data.

### 7.4 Exact durable schema

The artifact is strict UTF-8 canonical JSON: `ensure_ascii=False`, keys sorted lexicographically, separators `,` and `:`, no NaN/infinity, and exactly one final LF. Duplicate keys, extra/missing fields, non-exact primitive types, or noncanonical bytes are invalid. The maximum is 131,072 bytes, with the established B2 recursive limits: depth 16, string/key UTF-8 length 262,144, mapping members 128, and array members 256.

The exact top-level fields are:

```text
authority_files
checks
contract_id
dependency_versions
embedding_model
preflight_sha256
resource_families
resource_identities
schema_version
source_files
stage_id
status
```

Their exact shape is:

```json
{
  "authority_files": [
    {"byte_count": 1, "path": "repository/relative/path", "sha256": "<64hex>"}
  ],
  "checks": {
    "authority_files_unchanged": true,
    "client_construction_count": 0,
    "corpus_files_unchanged": true,
    "embedding_files_unchanged": true,
    "generation_call_count": 0,
    "model_snapshot_unchanged": true,
    "network_attempt_count": 0,
    "provider_call_count": 0,
    "runtime_cosine_probe_valid": true,
    "source_files_unchanged": true,
    "v1_is_exact_v2_qa_prefix": true
  },
  "contract_id": "formal_production_resource_preflight_v1",
  "dependency_versions": [
    {"name": "python", "version": "<bounded-safe-version>"}
  ],
  "embedding_model": {
    "backend": "torch",
    "dimensions": 384,
    "local_only": true,
    "model_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "probe_all_finite": true,
    "probe_dtype": "float32",
    "probe_id": "formal-evaluation-b4-offline-probe-v1",
    "probe_shape": [1, 384],
    "probe_unit_normalized": true,
    "revision": "<40hex>",
    "snapshot_file_count": 1,
    "snapshot_sha256": "<64hex>",
    "snapshot_total_bytes": 1,
    "trust_remote_code": false
  },
  "preflight_sha256": "<64hex>",
  "resource_families": [
    {
      "cache_family": "v1_qa",
      "corpus": {
        "byte_count": 1,
        "format": "pandas_pickle",
        "path": "outputs/cache/v1_qa/qa_corpus.pkl",
        "sha256": "<64hex>"
      },
      "corpus_metadata": {
        "allowed_for_answer_all_true": true,
        "cache_corpus_version": "v1_qa_only",
        "columns": ["<exact Section 4.3 columns>"],
        "doc_ids_unique": true,
        "index_kind": "range_0_based_contiguous",
        "logical_corpus_version": "production_v1_qa_only",
        "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "needs_backend_api_all_boolean": true,
        "nonempty_retrieval_text": true,
        "priority_values_runtime_compatible": true,
        "qa_count": 15333,
        "qa_priority_fixed_50": true,
        "row_count": 15333,
        "snippet_count": 0,
        "source_partition_valid": true,
        "source_sha256": "<64hex>"
      },
      "embeddings": {
        "all_finite": true,
        "byte_count": 1,
        "dimensions": 384,
        "dtype": "float32",
        "format": "numpy_npy",
        "path": "outputs/cache/v1_qa/qa_embeddings.npy",
        "rows": 15333,
        "sha256": "<64hex>",
        "unit_normalized": true
      }
    }
  ],
  "resource_identities": [
    {
      "resource_identity": {
        "cache_family": "v1_qa",
        "corpus_path": "outputs/cache/v1_qa/qa_corpus.pkl",
        "corpus_sha256": "<64hex>",
        "corpus_version": "production_v1_qa_only",
        "embedding_dimensions": 384,
        "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_rows": 15333,
        "embeddings_path": "outputs/cache/v1_qa/qa_embeddings.npy",
        "embeddings_sha256": "<64hex>",
        "formal_system_id": "qa_only_reconstructed_baseline",
        "logical_resource_id": "production_frozen_v1_qa_production_v1_qa_only",
        "qa_count": 15333,
        "resource_type": "production_frozen",
        "row_count": 15333,
        "schema_version": 1,
        "snippet_count": 0,
        "synthetic": false,
        "system_config_id": "qa_only_reconstructed_baseline"
      },
      "resource_identity_sha256": "<64hex>"
    }
  ],
  "schema_version": 1,
  "source_files": [
    {
      "byte_count": 1,
      "id": "qa_source",
      "path": "data/processed/jd_final_safe_qa_refined_category.csv",
      "role": "cleaned_qa_source",
      "sha256": "<64hex>"
    }
  ],
  "stage_id": "B4",
  "status": "passed"
}
```

Angle-bracket values above are schema metavariables, not literals or invented production values. Integer examples `1` mean a positive exact integer within the relevant cap, except where an exact count is stated.

Each `resource_identity` object has exactly the 18 Stage A fields shown, with no alias or path-derived ID. The remaining three objects use the exact system/family/count/path values in Sections 3.3–4.5. Every nested mapping shown has exactly its displayed fields. The V2 `resource_families` object has the same field set as V1 with the V2 literals/counts/paths from Section 4.3. The two priority fields are predicate-level evidence only; they are true in every passing family and no priority value or derived range is recorded. The two source objects have the same field set with their exact IDs, roles, paths, byte counts, and hashes.

Array order is normative:

- `authority_files`: ascending canonical path;
- `dependency_versions`: `python`, `numpy`, `pandas`, `scikit-learn`, `sentence-transformers`, `transformers`, `huggingface-hub`, `torch`;
- `source_files`: `qa_source`, then `snippet_source` (the latter uses role `reviewed_snippet_source` and its exact path);
- `resource_families`: `v1_qa`, then `v2_mixed`, each using its exact Section 4.3 values;
- `resource_identities`: the four-system order in Section 4.5;
- `columns`: exact Section 4.3 order.

The fixed authority-file set is (**NEW-B4**):

1. `docs/evaluation/formal_evaluation_baseline_identity_correction_amendment.md`;
2. `docs/evaluation/formal_evaluation_pre_execution_amendment.md`;
3. `docs/evaluation/formal_evaluation_protocol.md`;
4. `docs/evaluation/formal_evaluation_stage_b4_plan.md`;
5. `evaluation/formal_evaluation_manifest.json`;
6. `evaluation/formal_qa_only_baseline_spec.json`;
7. `outputs/rag_answer_demo.py`;
8. `outputs/requirements.txt`;
9. `scripts/formal_evaluation_orchestration.py`;
10. `scripts/formal_evaluation_resource_preflight.py`;
11. `scripts/formal_evaluation_resource_preflight_worker.py`;
12. `scripts/formal_evaluation_runtime.py`;
13. `scripts/formal_evaluation_transport.py`;
14. `scripts/formal_qa_only_baseline/adapter.py`;
15. `scripts/formal_qa_only_baseline/vendor/rag_answer_demo_12136b7.py`;
16. `scripts/run_formal_evaluation.py`.

These files are included because they define or consume the identity being observed. B2/B3 files are not included because their bytes do not define production resource usability.

### 7.5 Self-hash

`preflight_sha256` is:

```text
SHA256(
  UTF8("formal-evaluation-b4-preflight-v1\0") ||
  CANONICAL_JSON_BYTES(artifact with preflight_sha256 omitted)
)
```

The final LF is not part of the self-hash input. Reopen recalculates the hash, validates every nested field and Stage A identity, then requires canonical bytes plus LF.

### 7.6 Publication, reopen, and recovery

- Publication uses a same-directory owned temp, flush, `fsync`, close, Windows create-only move, parent-directory durability where the existing platform pattern supports it, and final readback.
- A final file is never overwritten.
- If an existing final is byte-for-byte the fresh candidate, return `already_complete`.
- If an existing final is valid but differs from the fresh candidate, return `B4_EVIDENCE_STALE`; preserve both the final and all resources, and publish nothing.
- If an existing final is malformed, noncanonical, oversized, or self-hash-invalid, return `B4_EVIDENCE_INVALID`; preserve it and publish nothing.
- An interruption before the create-only move leaves no final. On retry, only a recognized owned temp may be removed while holding the B4 lock. An interruption after the move is resolved by strict final readback.
- Unknown temp-like names are not removed. Lock or temp cleanup must never enter a source/cache/model/B2/B3 root.
- The lock coordinates only the reachable evidence publication race. No database, service, distributed lock, lease, or background daemon is introduced.

## 8. Failure taxonomy and sanitization

### 8.1 Closed public categories and precedence

The implementation exposes only these categories, in precedence order when one observation satisfies more than one category:

| Order | Category | Trigger and classification | Retry/preservation |
|---:|---|---|---|
| 1 | `B4_PLATFORM_UNSUPPORTED` | Required Windows path/lock/durable create-only behavior is unavailable. Platform invalidity. | No automatic retry; preserve everything. |
| 2 | `B4_AUTHORITY_INVALID` | Stage A registry, a fixed authority path/hash pass, B4 constants, or the approved schema cannot be validated. Authority/configuration invalidity. | Correct reviewed code/authority first; no automatic retry. |
| 3 | `B4_DEPENDENCY_UNAVAILABLE` | Required parent-side distribution metadata is absent/unsafe, or an applicable scrubbed worker cannot import a required optional package or symbol with all controls active and zero network attempts. Deterministic local dependency unavailability. | Safe to rerun only after separately authorized dependency remediation. B4 never installs. |
| 4 | `B4_PATH_UNSAFE` | Lexical escape, root overlap, forbidden symlink/reparse/junction/device, remote syntax, or unexpected evidence-tree member. Unsafe path resolution. | No automatic retry; preserve paths. |
| 5 | `B4_RESOURCE_MISSING` | A required source/cache/model ref/snapshot member does not exist. Missing resources. | Safe manual retry after external provisioning; B4 does not repair/download. |
| 6 | `B4_RESOURCE_TYPE_INVALID` | A required leaf/root has the wrong file/directory type or violates a size/file-count bound. Resource configuration invalidity. | Manual correction only; preserve. |
| 7 | `B4_EVIDENCE_INVALID` | Existing B4 final evidence is malformed, noncanonical, over limit, wrong schema, or hash-invalid. Malformed B4 artifact. | No automatic repair/overwrite; preserve for review. |
| 8 | `B4_RESOURCE_MALFORMED` | Pickle/NPY/ref/worker data cannot be decoded or has a wrong fundamental structure/type. Malformed production artifact. | Manual resource review; no repair or automatic retry. |
| 9 | `B4_RESOURCE_INCOMPATIBLE` | Structurally readable resource cannot be used by installed pandas/NumPy/model runtime, contains a present priority value that fails the Section 4.3 runtime-compatibility predicate, or violates dtype/finite/norm/local model-probe requirements. Compatibility failure. | Rerun only after an authorized external-state change. |
| 10 | `B4_IDENTITY_MISMATCH` | Source hash, cache attr, count, column (including a missing required `priority` column), partition, compatible QA priority other than fixed `50`, V1/V2 prefix, formal mapping, model ID/dimension, or Stage A identity/hash invariant disagrees. Identity mismatch. | Deterministic until inputs change; no automatic retry. |
| 11 | `B4_OFFLINE_VIOLATION` | Any socket/DNS/network attempt, remote fallback request, token resolution, or remote-code request occurs. Offline enforcement failure. | Stop; do not retry until code/config is reviewed. |
| 12 | `B4_RESOURCE_MUTATED` | Any authority/resource/model observation changes between first and second pass. Concurrent mutation/unstable snapshot. | Preserve; safe manual retry only once external writers are quiescent. |
| 13 | `B4_EVIDENCE_STALE` | Existing valid evidence differs from a fully validated fresh candidate. Stale observational evidence. | Preserve/no overwrite; requires an explicit later decision, not automatic retry. |
| 14 | `B4_LOCK_BUSY` | Another live B4 publisher holds the evidence lock. Concurrency condition. | Safe manual retry; no mutation except an already existing lock file. |
| 15 | `B4_IO_FAILURE` | A bounded local read, worker launch, lock, flush, durability, create-only move, or readback fails without a more specific category. Local I/O failure. | Preserve; retry only after the I/O condition is understood. |
| 16 | `B4_INTERNAL_FAILURE` | An otherwise unclassified invariant/implementation fault reaches the boundary. Internal failure. | No automatic retry; inspect code without exposing traceback publicly. |

Within a phase, the table controls overlaps. Across phases, the first completed observation in Section 5 controls. Metadata absence/invalidity in phase 6 and a zero-network optional import failure in phase 8 or 9 have the same stable meaning, `B4_DEPENDENCY_UNAVAILABLE`, and precede resource compatibility/identity classifications. A worker import accompanied by a detected network/remote attempt is specifically `B4_OFFLINE_VIOLATION`, not a dependency classification. Priority compatibility is evaluated before the QA fixed-value identity check. An operating-system error is mapped to a more specific missing/type/path category when the facts establish it; otherwise it is `B4_IO_FAILURE`. No raw third-party exception category is public.

### 8.2 Public CLI behavior

Success exits `0` and writes exactly one compact JSON line to stdout containing only:

```json
{"action":"created|already_complete","family_count":2,"preflight_sha256":"<64hex>","schema_version":1,"status":"passed","system_count":4}
```

The notation `created|already_complete` means the field contains exactly one of those two literals; the vertical bar is not emitted. `<64hex>` is replaced by the validated lowercase digest. Serialization uses the same sorted compact JSON convention plus LF.

Failure exits `2`, writes no stdout, and writes exactly `<CATEGORY>\n` to stderr. The library raises a B4 exception carrying only a validated category literal. `--help` exits normally without accessing resources.

No public output, exception string, log, or `repr` may contain credentials, environment values, absolute paths, local usernames, row content, retrieved text, document IDs, embedding/model contents, pickle/NumPy payloads, library error text, or traceback details. Detailed diagnostic state may be held only as local variables and must not be persisted.

The implementation performs no automatic retry. “Retry safe” in the table means a separately initiated invocation is non-mutating and well-defined after the stated condition is addressed.

## 9. Idempotence, restart, and concurrency

- **Repeated success:** every invocation revalidates the current resources. Exact evidence bytes yield `already_complete`; B4 never treats mere artifact presence as proof.
- **Interrupted validation:** no evidence root is created before a complete candidate exists. OS-temporary worker directories are best-effort removed; no production input was mutated.
- **Interrupted publication:** Section 7.6 create-only recovery applies. A recognized temp is not authoritative.
- **Malformed/partial evidence:** fail `B4_EVIDENCE_INVALID`; do not rename, repair, delete, or overwrite it.
- **Changed resources after a prior pass:** fresh validation yields a different candidate and `B4_EVIDENCE_STALE`, or detects an in-pass change as `B4_RESOURCE_MUTATED`. The old evidence is preserved.
- **Concurrent attempts:** validation may run concurrently because it is read-only. A short B4 publication lock plus create-only final move handles the actual shared race. One process may create; another either reopens exact evidence, reports lock busy, or reports stale evidence. There is no reachable need for a broader run lock.
- **Existing B2/B3 state:** ignored and untouched. It neither makes B4 pass nor blocks B4; its own stage later classifies it.
- **Deterministic failure:** repeated unchanged inputs return the same specific category. There is no backoff loop.
- **Stale lock state:** follow the established Windows lock-owner/liveness validation pattern; never infer safety from age alone and never delete a live/ambiguous lock. Exact lock-record details are private B4 mechanics, not evidence authority.

B4 uses the repository's unit-of-work principles—validate before mutation, fixed layout, held lock, create-only publication, readback, owned-temp cleanup—but does not import the private B2/B3 lock or atomic helpers. Those helpers are stage-root-specific and their direct reuse would couple B4 to fake-only/private or projection state. The new module implements the smallest B4-local equivalents and tests the same failure points.

## 10. Production safety boundary

### 10.1 Four distinct root classes

| Root class | Use | Default access in implementation tests |
|---|---|---|
| Synthetic test roots | Small and exact-count generated CSV/pickle/NPY/fake-model structures under `tmp_path` | Allowed and required. |
| OS-temporary verification roots | Worker CWD, pycache, transient test evidence | Allowed; removed or outside repository. |
| Actual production resource roots | `data/processed`, `outputs/cache`, and the one resolved local model repository | Forbidden unless the invocation has separate, exact authorization. |
| Production B2/B3 evidence roots | `data/formal_eval/private_state` and `data/formal_eval/reviewer_projection` | Always outside B4; no B4 implementation/probe access. |

The production B4 evidence root is a fifth, dedicated output root. It stores only Section 7 evidence and lock/temp mechanics; it is not a production input or a B2/B3 evidence root.

### 10.2 Acceptance versus real probe

Implementation acceptance must use only synthetic and OS-temporary roots. A real production-resource preflight is **not** part of implementation acceptance. It is a separate post-implementation gate requiring a fresh explicit authorization naming the exact resolved source, cache, model, and B4 evidence roots.

That later probe must be read-only for all production resources, offline, Provider-free, non-generative, and content-sanitized. Its verification record must establish before/after exact-root inventories, file hashes, type/reparse observations, and no mutation. It must not open B2/B3 roots. A passing probe may create only the ignored Section 7 B4 evidence artifact/lock and still does not authorize B5.

No test or implementation command may “try” the real paths in an expected-failure branch without this authorization. The test suite must fail if a production path is touched.

## 11. Implementation design

### 11.1 Maximum path budget

The entire B4 implementation slice has a maximum of **three new tracked paths** and **zero modified existing paths**:

1. `scripts/formal_evaluation_resource_preflight.py`
2. `scripts/formal_evaluation_resource_preflight_worker.py`
3. `scripts/test_formal_evaluation_resource_preflight.py`

No manifest, runner, runtime, store, transport, baseline, dependency, fixture, ignore, or documentation change is in budget. If implementation proves an existing path must change, stop for explicit scope expansion/amendment; do not consume a fourth path silently.

### 11.2 Parent module responsibilities

`scripts/formal_evaluation_resource_preflight.py` will own:

- fixed contract/path/schema/constants and the closed failure set;
- immutable `ProductionResourcePreflightResultV1`;
- public `preflight_production_resources() -> ProductionResourcePreflightResultV1` with no parameters;
- `main(argv: Sequence[str] | None = None) -> int`, accepting no operational options;
- path/reparse/type/size/tree validation;
- ordinary, model-tree, and evidence self-hashing;
- authority inventory and Python 3.11 stdlib-only dependency-metadata discovery;
- no-network parent guard and scrubbed sequential worker launch;
- strict worker and evidence JSON validation;
- Stage A identity construction/validation using public functions;
- cross-resource checks;
- short B4 lock, atomic create-only publication, reopen/recovery, and public sanitization.

The parent may import standard-library modules and the verified stdlib-only Stage A transport authority. It must not import NumPy, pandas, scikit-learn, sentence-transformers, transformers, huggingface-hub, torch, or any other optional data/model package. Its responsibilities are safe orchestration (including bounded stdlib path/hash checks), metadata-only dependency discovery, bounded scrubbed-worker invocation, sanitized worker-result validation, resource-identity checks, and evidence publication.

Private test-only entry points may accept a frozen `_PreflightPathsV1` and worker launcher so tests can use `tmp_path`. They must be underscore-prefixed, reject production roots while the test guard is active, and must not become CLI/public configuration.

### 11.3 Worker responsibilities

`scripts/formal_evaluation_resource_preflight_worker.py` will be stdlib-only at import time and will:

- establish credential/Provider scrubbing, offline variables, temporary cache roots, temporary working directory, socket/network guards, and bounded input/output controls before optional imports;
- import NumPy/pandas only in `resource` mode and the required NumPy/scikit-learn/sentence-transformers/transformers/huggingface-hub/torch stack only in `model` mode;
- implement fixed `resource` and `model` probes;
- load/validate only the explicitly passed fixed resources, including the single priority predicate and QA fixed-`50` rule;
- emit only the exact bounded aggregate schemas;
- contain no evidence publisher, Provider/client import, environment loader, repair/rebuild path, or user-facing diagnostic.

### 11.4 Test responsibilities

`scripts/test_formal_evaluation_resource_preflight.py` will contain every new B4 test. A second helper/test file is not in budget. Session/module fixtures may generate exact-count synthetic resources once in OS temporary storage to keep runtime and memory proportionate.

### 11.5 Dependency direction and reuse

```text
test module
  -> B4 parent -> public Stage A transport identity APIs
               -> Python 3.11 stdlib importlib.metadata (version strings only)
               -> stdlib subprocess -> B4 worker -> installed local data/model libraries

B4 parent -/-> runner/store/inflight/review projection/Provider/config parser
B4 worker -/-> transport/runner/store/Provider/evidence publication
```

Direct reuse is limited to public Stage A identity/registry/hash functions because they are the canonical identity authority. The B4 module follows, but does not import, private B2/B3 strict-JSON, path, lock, and create-only publication patterns. It reads constants/metadata from tracked authorities only where doing so cannot trigger a loader. It must not import `outputs.rag_answer_demo` merely to reach constants because that module also exposes mutating/generative surfaces; fixed values are restated with authority-file hashing and compatibility tests. Optional dependency discovery in the parent is limited to `platform.python_version()` and `importlib.metadata.version()`; only the scrubbed workers may import optional data/model packages.

### 11.6 CLI, API, migration, and dependency changes

- New CLI: `python scripts/formal_evaluation_resource_preflight.py`; no resource/root/model/real flags.
- Existing runner CLI: unchanged; no B4 or real mode is added.
- New public Python API: only the result dataclass and `preflight_production_resources()`.
- Existing public APIs: unchanged.
- Data migration: none.
- Dependency additions/upgrades: none.
- Production resource rewrite: none.
- B2/B3 migration or reopen behavior: none.

## 12. Test and verification plan

### 12.1 New focused test collection

The single proposed test file will use this exact class/node structure. Individual bullets name required methods; parameterization may expand node counts without changing semantics.

#### `TestB4ContractAndDiscovery`

- `test_fixed_resource_contract_matches_tracked_authorities`
- `test_stage_a_registry_yields_exact_four_family_bindings`
- `test_public_api_accepts_no_root_model_or_real_override`
- `test_dependency_inventory_is_exact_and_bounded`
- `test_authority_inventory_is_exact_sorted_and_unchanged`

Assertions: exact paths/names/model/counts/columns/versions/system order; production identities pass Stage A and V2 hashes are shared; no fallback QA path; exact three-file implementation budget.

#### `TestB4DependencyBoundary`

- `test_parent_never_imports_optional_data_or_model_packages`
- `test_parent_dependency_discovery_uses_only_stdlib_metadata`
- `test_worker_optional_imports_begin_only_after_all_controls`
- `test_worker_dependency_import_failure_maps_only_to_b4_dependency_unavailable`
- `test_dependency_failure_is_sanitized_nonpublishing_and_preserving`

Assertions: parent discovery calls only `platform.python_version()` and `importlib.metadata.version()` with the fixed names and treats `PackageNotFoundError` deterministically; parent import traps for NumPy, pandas, scikit-learn, sentence-transformers, transformers, huggingface-hub, torch, and transitive optional data/model packages remain untouched; the first injected worker import observes credential/Provider scrubbing, offline variables, temporary cache roots, temporary working directory, socket guards, and bounded I/O already active; a synthetic package exception containing secret/path/cache markers yields only `B4_DEPENDENCY_UNAVAILABLE`; stdout has no success, no B4 artifact is created, and synthetic production/B2/B3 sentinels and inventories remain byte-for-byte unchanged.

#### `TestB4PathBoundary`

- `test_rejects_relative_escape_drive_unc_uri_and_alternate_separator`
- `test_rejects_source_or_cache_symlink_junction_and_reparse_component`
- `test_allows_only_model_file_links_resolving_within_model_repository`
- `test_rejects_model_link_escape_dangling_link_and_directory_reparse`
- `test_rejects_wrong_type_size_file_count_and_overlapping_roots`
- `test_production_root_guard_fails_before_any_production_access`

Assertions: `B4_PATH_UNSAFE`/`B4_RESOURCE_TYPE_INVALID` precedence, no worker start, no evidence write, all synthetic input bytes unchanged.

#### `TestB4ResourceStructure`

- `test_accepts_exact_count_synthetic_v1_and_v2_snapshot`
- `test_rejects_missing_family_member_without_rebuild`
- `test_rejects_truncated_wrong_object_and_wrong_attr_pickles`
- `test_rejects_npy_object_dtype_wrong_dtype_shape_nan_inf_and_bad_norm`
- `test_rejects_wrong_columns_index_counts_partition_and_empty_fields`
- `test_rejects_duplicate_doc_ids_and_nonboolean_flags`
- `test_accepts_builder_compatible_qa_and_snippet_priorities`
- `test_rejects_non_integer_compatible_priority`
- `test_rejects_null_priority`
- `test_rejects_boolean_priority`
- `test_rejects_qa_priority_other_than_fixed_50`
- `test_rejects_source_hash_and_legacy_combined_hash_mismatch`
- `test_rejects_v1_v2_qa_prefix_mismatch_without_emitting_difference`
- `test_worker_output_is_aggregate_canonical_and_bounded`

Assertions: exact failure category; valid fixtures use QA integer priority `50` and builder-compatible integer snippet priorities without imposing a snippet range; non-integer-compatible/null/Boolean values are `B4_RESOURCE_INCOMPATIBLE`; a compatible QA integer other than `50` is `B4_IDENTITY_MISMATCH`; only the two aggregate priority booleans cross the worker boundary; `allow_pickle=False`; mmap/read-only/chunked embedding validation; no cache builder call; no priority/row/vector marker in stdout/stderr/exception/evidence.

#### `TestB4OfflineModelProbe`

- `test_local_snapshot_probe_uses_exact_path_and_offline_arguments`
- `test_rejects_missing_ref_revision_snapshot_or_model_files`
- `test_rejects_remote_code_remote_fallback_and_any_socket_attempt`
- `test_rejects_wrong_probe_shape_nonfinite_or_nonunit_output`
- `test_rejects_unusable_or_invalid_runtime_cosine_similarity`
- `test_model_tree_hash_is_deterministic_and_path_sensitive`
- `test_worker_environment_omits_credentials_proxies_and_tokens`
- `test_worker_timeout_crash_extra_output_and_schema_error_fail_closed`

Assertions: no URL/model-ID load, exact constructor/encode/cosine arguments, exact float32 probe, network attempt counter remains zero on success, no model path/vector/similarity/error content crosses the parent boundary.

#### `TestB4ArtifactLifecycle`

- `test_first_success_publishes_exact_canonical_artifact_and_result`
- `test_exact_reopen_revalidates_resources_and_returns_already_complete`
- `test_valid_different_existing_artifact_is_stale_and_not_overwritten`
- `test_malformed_noncanonical_oversized_and_hash_bad_artifact_is_preserved`
- `test_interruption_before_and_after_create_only_move_recovers_closed`
- `test_only_owned_temp_is_removed_while_lock_is_held`
- `test_unknown_member_and_ambiguous_lock_fail_closed`
- `test_two_publishers_create_or_reopen_without_overwrite`

Assertions: exact schema/order/self-hash/LF, final readback, lock ownership, no overwrite, correct `created`/`already_complete`, deterministic concurrency classification, and no production/B2/B3 access.

#### `TestB4FailureBoundaryAndPreservation`

- `test_failure_taxonomy_is_closed_and_precedence_is_stable`
- `test_cli_success_and_failure_bytes_and_exit_codes_are_exact`
- `test_public_boundary_removes_path_secret_row_vector_and_traceback_markers`
- `test_before_after_mutation_is_detected_without_publication`
- `test_every_failure_preserves_inputs_and_existing_b2_b3_sentinels_byte_for_byte`
- `test_ast_has_no_provider_client_env_loader_generation_or_mutating_loader_path`
- `test_help_and_import_have_zero_resource_network_or_write_effects`

Assertions: exact category-only failures, zero Provider/client/generation counters, zero sockets, repository-relative evidence only, byte-for-byte and directory-inventory equality.

### 12.2 Test controls

Every focused test uses synthetic or `tmp_path` roots. An autouse guard must:

- reject any B4 open/stat/hash/worker path beneath the fixed actual `data/processed`, `outputs/cache`, resolved real model repository, B2 private-state, or B3 reviewer-projection roots;
- monkeypatch `socket.socket`, `socket.create_connection`, and `socket.getaddrinfo` to increment then fail;
- trap any `OpenAI`, `parse_deepseek_config`, `load_dotenv`, Provider proxy, `run_rag_query`, `run_dialogue_checkpointed`, B3 projection, `load_or_create_cache`, corpus builder, encoder-rebuild, or save call;
- record Provider/client/generation call counters and require all zero;
- seed synthetic exception messages with fake credential, absolute-path, row-text, and vector markers and assert that none appears publicly;
- install parent optional-import traps and worker import-order hooks, with synthetic dependency exceptions containing fake credential, absolute-path, and model-cache markers;
- inventory/hash all test input and B2/B3 sentinel files before and after each failure/success.

The exact-count integration fixture creates 15,333 V1 rows and 15,688 V2 rows with 384-column float32 `.npy` arrays once per test session under OS temporary storage. Smaller private-seam fixtures cover malformed cases. The model is a test-only local snapshot with an injected fake `SentenceTransformer` implementation; implementation acceptance must not depend on the actual local model cache. Link/reparse policy tests use a deterministic private filesystem-classification seam where Windows test privileges do not permit symlink creation; they must not skip.

### 12.3 Existing compatibility coverage

Do not duplicate invariants already covered by existing suites:

- Stage A identity/Provider boundary: `scripts/test_formal_evaluation_transport.py` and `scripts/test_formal_evaluation_inflight.py`;
- Stage B1 binding/orchestration: `scripts/test_formal_evaluation_orchestration.py`;
- Stage B2 durability and runner gate: `scripts/test_formal_evaluation_store.py` and `scripts/test_run_formal_evaluation.py`;
- Stage B3 source eligibility/projection: `scripts/test_formal_evaluation_review_projection.py`;
- frozen authority, runtime, and baseline behavior: `scripts/test_formal_evaluation_freeze.py`, `scripts/test_formal_evaluation_runtime.py`, and `scripts/test_formal_qa_only_baseline_adapter.py`.

B4 adds only compatibility assertions needed to show its new imports/API did not change those contracts. Frozen-fixture-reading compatibility suites require explicit authorization for that later implementation task, must remain in-process/offline, and may report only aggregate test counts—not row content.

### 12.4 Exact command matrix

All commands use the repository `.venv` and OS-temporary pycache:

```powershell
$VenvPython = (Resolve-Path ".venv\Scripts\python.exe").Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "formal-evaluation-b4-pycache"

# Non-executing syntax/AST compile checks; pycache remains outside the repository.
& $VenvPython -m py_compile `
  scripts/formal_evaluation_resource_preflight.py `
  scripts/formal_evaluation_resource_preflight_worker.py `
  scripts/test_formal_evaluation_resource_preflight.py

# Establish the exact focused count, then require every collected test to pass.
& $VenvPython -m pytest scripts/test_formal_evaluation_resource_preflight.py `
  --collect-only -q -p no:cacheprovider
& $VenvPython -m pytest scripts/test_formal_evaluation_resource_preflight.py `
  -q -p no:cacheprovider

# Stage A compatibility.
& $VenvPython -m pytest `
  scripts/test_formal_evaluation_transport.py `
  scripts/test_formal_evaluation_inflight.py `
  -q -p no:cacheprovider

# Stage B1 compatibility.
& $VenvPython -m pytest `
  scripts/test_formal_evaluation_orchestration.py `
  -q -p no:cacheprovider

# Stage B2 and runner compatibility.
& $VenvPython -m pytest `
  scripts/test_formal_evaluation_store.py `
  scripts/test_run_formal_evaluation.py `
  -q -p no:cacheprovider

# Stage B3 compatibility.
& $VenvPython -m pytest `
  scripts/test_formal_evaluation_review_projection.py `
  -q -p no:cacheprovider

# Frozen/runtime/baseline compatibility; run only with explicit frozen-fixture authority.
& $VenvPython -m pytest `
  scripts/test_formal_evaluation_freeze.py `
  scripts/test_formal_evaluation_runtime.py `
  scripts/test_formal_qa_only_baseline_adapter.py `
  -q -p no:cacheprovider
```

For every pytest command, record collection count, passed count, failed/error/skipped/xfail count, and deselections. Acceptance requires collected = passed, with zero failure/error/skip/xfail and no unexplained deselection.

Repository verification after tests:

```powershell
git diff --check
git status --short --untracked-files=all
git diff --cached --name-status
git check-ignore -q data/formal_eval/resource_preflight/production_resource_preflight_v1.json
```

Verify exactly the three authorized implementation paths changed, the index is empty, no repository pycache/pytest/temp/evidence artifact exists, and no production/B2/B3 path changed. A non-writing AST check must confirm that the parent has no optional data/model import and uses only the Section 3.5 metadata calls for dependency discovery, that optional data/model imports appear only in the worker after its stdlib control setup, and that neither new module imports/calls Provider clients, `.env` loaders, generation, B2/B3 execution, or mutating cache builders. The focused dependency-boundary, resource-structure, and failure-boundary tests above are the executable authorities for those assertions, including all priority cases and the `B4_DEPENDENCY_UNAVAILABLE` path.

### 12.5 Separately authorized production probe

The following command is deliberately excluded from implementation acceptance and must not be run without a new exact authorization:

```powershell
& $VenvPython scripts/formal_evaluation_resource_preflight.py
```

Before that command, the operator must record safe exact-root inventories/hashes without printing content; after it, repeat them and prove that only the permitted ignored B4 evidence root changed. The command must report only the Section 8 public result. It must not be combined with real mode, a canary, a client, a B2/B3 command, or formal generation.

## 13. Acceptance criteria

A later implementation review may return PASS only if all of these objective criteria are met:

1. The implementation changes exactly the three new tracked paths in Section 11 and no existing path.
2. The public API and CLI have no path, root, model, URL, real, canary, repair, rebuild, or credential override.
3. Resource discovery resolves exactly the two source files, two corpus files, two embedding files, and one model snapshot defined here.
4. Actual production roots and B2/B3 evidence roots are never accessed by implementation acceptance tests.
5. All lexical, containment, type, reparse, overlap, and bound checks fail closed with the specified precedence.
6. Source/cache/model/authority observations are repeated before publication and any change yields `B4_RESOURCE_MUTATED`.
7. Raw source linkage and the exact legacy V2 combined-source hash are correct.
8. Corpus attrs, exact columns/index, counts, partitions, uniqueness, non-empty retrieval fields, the single runtime-compatible priority predicate, fixed QA priority `50`, and V1/V2 QA-prefix equality are validated without exposing priority values or rows and without inventing a snippet-priority range.
9. Embeddings require non-pickle read-only load, exact float32 shapes, all-finite values, and the reviewed normalization tolerance.
10. The model is resolved from the one local cache root, tree-hashed, loaded from the exact snapshot path with local-only/remote-code-disabled settings, produces only the exact float32 synthetic 384-dimensional probe, and passes the bounded runtime cosine-similarity self-check.
11. Parent and worker network guards prove zero DNS/socket attempts; remote fallback is impossible and classified if attempted.
12. Parent dependency discovery is Python 3.11 stdlib metadata-only; import/AST traps prove the parent imports no optional data/model package, every such import occurs only in its applicable scrubbed worker after all controls are active, and zero credential resolution, Provider calls, client construction, generation, evaluation, reviewer projection, or mutating loader activity occurs.
13. Exactly four production resource identities are built in the fixed order, pass Stage A validation, and have Stage A hashes; all three V2 identities share the exact physical snapshot.
14. The in-memory result has the exact immutable schema and contains no absolute path or content.
15. The durable artifact has the exact schema, array ordering, canonical bytes/LF, self-hash, bounds, and safe fields in Section 7.
16. A passing artifact is observational only; code and documentation contain no path by which its presence alone authorizes or creates a formal run.
17. First publication is atomic/create-only with readback; exact reopen is idempotent; stale or malformed evidence is preserved and never overwritten.
18. The only introduced concurrency mechanism is the short B4 evidence-publication lock, and its reachable two-publisher race test passes.
19. Every public failure is one closed category, exits `2`, has empty stdout/category-only stderr, and leaks no path, credential, row, priority, vector, payload, package-internal exception, model-cache content, or traceback; every deterministic metadata or zero-network worker import failure maps only to `B4_DEPENDENCY_UNAVAILABLE` with its specified precedence.
20. Byte-for-byte hashes and inventories prove zero mutation of synthetic inputs and existing B2/B3 sentinels in every focused success/failure test, including dependency-unavailable failures, and no failed dependency path publishes a B4 success artifact.
21. No dependency, migration, manifest, frozen fixture, runner mode, runtime contract, baseline contract, B2 contract, or B3 contract changes.
22. `py_compile`, focused collection/execution, and every authorized compatibility batch in Section 12 pass exactly, with counts reported honestly.
23. `git diff --check` passes, the index is empty, and repository inventory shows no temp/cache/evidence residue.
24. A real production probe has not been used to make implementation acceptance pass. If separately authorized later, its exact-root/no-mutation/offline sanitized record passes Section 10.2.
25. Independent review explicitly approves every **NEW-B4** decision before implementation begins; otherwise the implementation remains blocked.

## 14. Explicit deferrals to Stage B5

The following concerns are wholly deferred to Stage B5 and must not be designed or implemented by B4 beyond consuming the minimal B4 result interface described in Section 5.1:

- whether, when, and by whom a real run is authorized;
- credential-file selection and API-key resolution;
- Provider base URL, SDK settings, and real-client construction;
- network permission, DNS/TLS behavior, and Provider access;
- real-mode and canary CLI semantics;
- binding authorization to a fresh B4 evidence hash and production run contract;
- production first-contract creation and restart-safe real execution;
- Provider-call tracking, response validation, retry classification, uncertain outcomes, and fallback rejection in real execution;
- response-generation authorization and dispatch;
- billing, quota, rate-limit, and spend behavior;
- resume after real success/failure and formal completion;
- any B3 invocation after eligible non-synthetic B2 completion.

B4 exposes only `preflight_sha256` plus four validated `ProductionResourceIdentity` objects. It does not prescribe B5's authorization record, lock timing, CLI, client factory, or retry implementation.

## 15. Risks and decisions

### 15.1 Concrete risks and mitigations

| Risk supported by the repository | Decision/mitigation |
|---|---|
| The existing cache loader rebuilds and writes when cache validity fails. | B4 never calls it; it uses a new read-only worker and AST/call traps. |
| Production corpus caches are pandas pickles. | Require exact-root authorization, pre-hash/type/size gates, a fresh scrubbed offline subprocess, fixed aggregate output, and fail-closed decode; do not claim hostile-pickle sandboxing. |
| Existing model construction by ID could download on cache miss. | Resolve the exact local snapshot first, load by local path with offline flags/socket guards/`local_files_only`, and reject absence rather than download. |
| There is no tracked frozen production cache/model hash. | Record a deterministic observed identity in non-authorizing evidence; require a fresh matching result for any later reliance. Do not invent expected hashes. |
| Stage A requires production corpus versions to start with `production_`, while core cache attrs use `v1_qa_only`/`v2_mixed`. | Keep the concepts separate: proposed identity versions `production_v1_qa_only`/`production_v2_mixed`, and validate the unchanged core attrs independently. |
| Three formal systems share one V2 cache and could drift in identity construction. | Build once-observed V2 facts into three separately Stage A-validated identities and require their physical fields to match exactly. |
| Error messages from pandas/NumPy/model libraries can contain paths or object content. | Worker returns fixed aggregate JSON only; parent maps every failure to a closed category and discards third-party text. |
| A resource can change while it is being checked. | Hash/type/tree observations before and after; fail `B4_RESOURCE_MUTATED`; do not add a broad resource lock unsupported by current architecture. |
| Dependency declarations are unpinned. | Record exact installed versions through Python 3.11 stdlib metadata only, import/probe optional packages exclusively inside the applicable fully scrubbed worker, map sanitized failures to `B4_DEPENDENCY_UNAVAILABLE`, and do not update dependencies in B4. |

### 15.2 Decisions made and evidence

1. **Standalone B4 CLI/API, no runner edit.** The current runner is deliberately fake-only/real-disabled; adding a B4 mode would widen a frozen surface and blur B5.
2. **Three-file maximum.** One parent, one safety worker, and one focused test module are the smallest coherent slice.
3. **Both in-memory and durable evidence.** The separate production-probe/authorization gates need audit evidence, while same-process integration needs validated objects.
4. **Evidence is observational, not authoritative.** No frozen physical hashes currently exist; the plan preserves that fact instead of silently blessing local bytes.
5. **Hash raw sources but do not parse them.** The existing cache format binds their byte hashes, while cached structure—not source-row semantics—is what the runtime consumes.
6. **Load corpus/embeddings/model only where metadata is insufficient.** These are the minimum compatibility checks that establish local usability without rebuilding.
7. **One narrow publication lock.** The only shared mutation is one evidence file; validation remains read-only and outside B2/B3 locks.
8. **No timestamps.** Omitting them gives exact deterministic bytes for unchanged inputs.
9. **Production probe after implementation acceptance.** Tests cannot safely establish the real snapshot without the separate access authority required by repository policy.

### 15.3 Rejected alternatives

- **Use `load_or_create_cache`.** Rejected because it can create directories, rebuild embeddings, and overwrite production resources.
- **Let Sentence Transformers load by model ID.** Rejected because missing files could trigger remote resolution/download.
- **Put B4 into Stage B2 or B3 roots/locks.** Rejected because those stages have distinct fixed layouts, evidence semantics, and recovery responsibilities.
- **Make the B4 artifact a run authorization.** Rejected because authorization belongs to B5 and observed hashes are not pre-existing frozen approvals.
- **Use only in-memory evidence.** Rejected because a separately authorized real probe would leave no reviewable, sanitized snapshot record.
- **Accept arbitrary root/model CLI arguments.** Rejected because they weaken the exact production identity and make accidental production/test crossover reachable.
- **Rebuild to prove embedding provenance.** Rejected because B4 is read-only, and rebuilding would mutate scope and potentially change frozen behavior.
- **Add a database, service, distributed lock, watcher, or background health check.** Rejected because the only reachable race is local create-only publication by two processes.
- **Silently allow arbitrary pickle globals as “safe.”** Rejected because pickle is executable; the explicit local-origin trust boundary must remain visible.

### 15.4 Review history and current authorization status

The first complete plan was initially `DRAFT`. Its first independent review returned `CHANGES_REQUIRED` for B4-1 (runtime priority compatibility) and B4-2 (the optional-import boundary). Both findings were corrected, and the correction candidate completed. The exact pre-finalization reviewed candidate, SHA-256 `96457b8ba98f035e7b0d9fef7a7b09e276335f19032ec5442f2c4433815835d6`, subsequently received focused independent rereview token `STAGE_B4_PLAN_FOCUSED_REREVIEW_PASS` with verdict `PASS`. The repository does not provide pre-approved production cache/model hashes, but that absence remains represented explicitly by the observational evidence and later-authorization boundary rather than hidden by an invented constant.

The focused independent rereview approved the exact reviewed candidate and authorized only this lifecycle finalization. The resulting plan is approved and frozen. Approval and freeze do not authorize Stage B4 implementation, the real production-resource probe, production-resource access, Stage B5, credentials or Provider access, network access, client construction, real or canary mode, formal evaluation, or response generation. The plan-publication commit remains separately unauthorized and pending.

---

**End status:** APPROVED AND FROZEN — first complete plan initially `DRAFT`; first independent review `CHANGES_REQUIRED`; B4-1 and B4-2 corrected; correction candidate completed; focused independent rereview `STAGE_B4_PLAN_FOCUSED_REREVIEW_PASS` / `PASS` for the exact pre-finalization reviewed candidate. Stage B4 implementation remains unauthorized; the plan-publication commit remains separately unauthorized and pending; the real production-resource probe and Stage B5 remain unauthorized.
