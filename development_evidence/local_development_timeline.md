# Local Development Timeline

GitLab access was obtained after the initial local development phase. Before the repository was available, the project was developed locally through scripts, intermediate datasets, evaluation reports, and web prototypes.

## 2026-06-22

- Started analysing JD customer-service chat records.
- Developed initial scripts for parsing and filtering chat logs.
- Generated early statistics for valid files, rejected files, sender types, and extracted QA candidates.

## 2026-06-23

- Improved QA extraction from historical customer-service conversations.
- Added turn-based QA extraction.
- Added consecutive customer-message and service-message merging.
- Added filtering for short keyword questions and low-quality QA pairs.
- Produced dataset statistics and category distribution reports.

## 2026-06-24

- Built the first V1 RAG chatbot prototype using cleaned JD QA pairs.
- Added embedding-based retrieval, rule-based reranking, and answer generation.
- Built a FastAPI web demo.
- Added pre-retrieval intent guards for identity queries, human handover, backend-required queries, invalid input, and emotional input.

## 2026-07-06 onwards

- Added structured JD service-script knowledge snippets.
- Manually reviewed and corrected the V2 knowledge base.
- Added V2 mixed corpus retrieval.
- Added backend capability boundaries, risky answer filtering, conservative response templates, and final answer cleanup.
- Added evaluation scripts and reports for V2 testing.