# Formal Dissertation Evaluation Results

All tables are aggregate-only. Systems were unblinded exclusively through the canonical B3 ID mapping; no question or answer text was used for joins.

## Scoring-data validity and sample sizes

| Check | Result |
| --- | --- |
| Validation status | PASS |
| Reviewer bundle ID | `b3b_df58ae0ecc6666a7feff0aa2` |
| JSON exports | 2 |
| Canonical projection integrity | PASS |
| Missing, unknown, duplicate, or conflicting IDs | 0 |
| Score-domain or derived-score conflicts | 0 |
| Text matching used for joins | No |

| Reviewer / section | Scored units | Expected units | Coverage |
| --- | ---: | ---: | ---: |
| Reviewer 1 — RQ1 primary responses | 102 | 102 | 100% |
| Reviewer 1 — RQ2 responses | 40 | 40 | 100% |
| Reviewer 1 — RQ3 dialogues | 24 | 24 | 100% |
| Reviewer 1 — RQ3 source turns | 48 | 48 | 100% |
| Reviewer 2 — RQ1 secondary responses | 22 | 22 | 100% |
| RQ1 paired questions | 51 | 51 | 100% |
| RQ2 paired cases | 20 | 20 | 100% |
| RQ3 paired dialogue cases | 12 | 12 | 100% |

Canonical unblinding maps `qa_only_reconstructed_baseline` to the **QA-only reconstructed baseline** (`formal_system_id = qa_only_reconstructed_baseline`) and `v2` to **V2** (`formal_system_id = current_v2`). For RQ3, `single_turn` is V2 without context management and `context_aware` is V2.1b context-aware.

## Inter-rater reliability

Reliability uses the 22 shared RQ1 response records (11 complete paired questions). Kappa uses each rubric's fixed score domain.

| Outcome | n | Exact agreement | Linear-weighted Cohen's κ |
| --- | ---: | ---: | ---: |
| Quality total (0–8) | 22 | 10/22 (45.5%) | 0.622 |
| Relevance | 22 | 19/22 (86.4%) | 0.718 |
| Factual Policy Correctness | 22 | 14/22 (63.6%) | 0.560 |
| Completeness Actionability | 22 | 15/22 (68.2%) | 0.601 |
| Safety Boundary Compliance | 22 | 17/22 (77.3%) | 0.375 |
| Acceptable (binary) | 22 | 20/22 (90.9%) | 0.818 |

All four RQ1 dimensions matched simultaneously for 8/22 shared responses (36.4%).

## RQ1 results

### System descriptives

| System | n | Quality total, mean (SD) | Median | Acceptable | Total-score distribution (score: n) |
| --- | ---: | ---: | ---: | ---: | --- |
| QA-only reconstructed baseline | 51 | 5.82 (1.68) | 6.0 | 32/51 (62.7%) | 0: 0; 1: 0; 2: 2; 3: 1; 4: 12; 5: 4; 6: 12; 7: 10; 8: 10 |
| V2 | 51 | 6.02 (1.84) | 6.0 | 35/51 (68.6%) | 0: 0; 1: 0; 2: 2; 3: 4; 4: 7; 5: 3; 6: 13; 7: 6; 8: 16 |

### Predeclared paired comparisons

Positive differences and effect sizes favour V2.

| Outcome | Paired difference | Test | p | Effect size / interval |
| --- | ---: | --- | ---: | --- |
| Quality total | mean 0.20; median 0.0 | Wilcoxon W=29.5 | 0.285 | rank-biserial 0.352; paired-bootstrap 95% CI [-0.14, 0.55] |
| Acceptable | 5.9 percentage points | exact McNemar (1 vs 4 discordant) | 0.375 | paired rate difference |

### Rubric dimensions (exploratory)

| Dimension | Baseline mean (SD) | V2 mean (SD) | Mean paired difference | Wilcoxon p | Holm p | Rank-biserial |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Relevance | 1.75 (0.44) | 1.73 (0.49) | -0.02 | 1.000 | 1.000 | -0.333 |
| Factual Policy Correctness | 1.25 (0.59) | 1.31 (0.58) | 0.06 | 0.438 | 1.000 | 0.467 |
| Completeness Actionability | 1.04 (0.75) | 1.16 (0.78) | 0.12 | 0.109 | 0.438 | 0.600 |
| Safety Boundary Compliance | 1.78 (0.46) | 1.82 (0.39) | 0.04 | 0.766 | 1.000 | 0.250 |

## RQ2 results

All inferential RQ2 comparisons are exploratory. Positive differences favour V2; Holm p-values adjust the four-outcome RQ2 family.

| Outcome | Baseline pass | V2 pass | Difference | Discordant (baseline-only / V2-only) | Exact McNemar p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Route Pass | 15/20 (75.0%) | 15/20 (75.0%) | 0.0 pp | 2 / 2 | 1.000 | 1.000 |
| Required Content Pass | 10/20 (50.0%) | 11/20 (55.0%) | 5.0 pp | 1 / 2 | 1.000 | 1.000 |
| Forbidden Content Pass | 19/20 (95.0%) | 19/20 (95.0%) | 0.0 pp | 0 / 0 | 1.000 | 1.000 |
| Case Pass | 10/20 (50.0%) | 11/20 (55.0%) | 5.0 pp | 1 / 2 | 1.000 | 1.000 |

## RQ3 results

All RQ3 inferential comparisons are exploratory. Positive differences favour V2.1b context-aware. Dialogue-level inference uses 12 paired dialogue cases; turn-level inference is separated by turn index to avoid treating two turns from the same dialogue as independent.

### Dialogue-level outcomes

| Outcome | Single-turn pass | Context-aware pass | Difference | Discordant (single-only / context-only) | Exact McNemar p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dialogue Pass | 7/12 (58.3%) | 8/12 (66.7%) | 8.3 pp | 0 / 1 | 1.000 | 1.000 |
| No Safety Violation | 12/12 (100.0%) | 12/12 (100.0%) | 0.0 pp | 0 / 0 | 1.000 | 1.000 |

### Turn-level outcomes by turn index

| Turn | Outcome | Single-turn pass | Context-aware pass | Difference | Exact McNemar p | Holm p |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Route Pass | 11/12 (91.7%) | 11/12 (91.7%) | 0.0 pp | 1.000 | 1.000 |
| 1 | Required Content Pass | 9/12 (75.0%) | 10/12 (83.3%) | 8.3 pp | 1.000 | 1.000 |
| 1 | Forbidden Content Pass | 12/12 (100.0%) | 12/12 (100.0%) | 0.0 pp | 1.000 | 1.000 |
| 1 | Turn Pass | 9/12 (75.0%) | 10/12 (83.3%) | 8.3 pp | 1.000 | 1.000 |
| 2 | Route Pass | 11/12 (91.7%) | 11/12 (91.7%) | 0.0 pp | 1.000 | 1.000 |
| 2 | Required Content Pass | 8/12 (66.7%) | 8/12 (66.7%) | 0.0 pp | 1.000 | 1.000 |
| 2 | Forbidden Content Pass | 12/12 (100.0%) | 12/12 (100.0%) | 0.0 pp | 1.000 | 1.000 |
| 2 | Turn Pass | 8/12 (66.7%) | 8/12 (66.7%) | 0.0 pp | 1.000 | 1.000 |

### Factual interpretation

Across the 22 shared RQ1 responses, exact total-score agreement was 45.5% and linear-weighted Cohen's kappa was 0.622.

Safety-boundary compliance had the lowest dimension-level inter-rater reliability: exact agreement was 17/22 (77.3%) and linear-weighted Cohen's kappa was 0.375. This lower Safety reliability is a limitation when interpreting Safety-related results.

RQ1 does not provide statistically significant evidence of a paired overall quality-score difference between V2 and the QA-only reconstructed baseline. The observed mean paired difference was 0.20 points (paired-bootstrap 95% CI -0.14 to 0.55).

The predeclared exact McNemar test did not find a statistically significant difference in RQ1 acceptability rates.

RQ2's exploratory exact McNemar comparison did not find a statistically significant case-pass difference between the systems.

RQ3's exploratory dialogue-level exact McNemar comparison did not find a statistically significant dialogue-pass difference between context-aware and single-turn V2. Turn-level inference is separated by turn index because turns are clustered within dialogues.

Overall, the observed headline paired differences were small and favoured V2 or context-aware V2, but the reported predeclared and Holm-adjusted tests did not provide statistically significant evidence of improvement.

RQ1/RQ2 compare complete system configurations; these results do not identify the causal contribution of an individual retrieval, reranking, snippet, or guard component.

Exploratory p-values should be interpreted as secondary evidence rather than as predeclared primary tests. Holm-adjusted p-values are reported within each exploratory outcome family.
