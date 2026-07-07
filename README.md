# Web-based RAG Chatbot for E-commerce Customer Support

This repository contains the code for an MSc dissertation project:

**A Web-based AI Customer Service Chatbot for E-commerce Customer Support using Retrieval-Augmented Generation (RAG).**

## Project Overview

The system is designed for shoe e-commerce customer service. It answers common customer questions such as size recommendation, product attributes, return and exchange policy, freight insurance, and delivery-related rules.

The system is not designed to fully replace human customer service. For questions that require real-time backend access, such as order status, logistics progress, refund progress, or after-sales progress, the chatbot returns a safe human-handover response instead of pretending to query the backend.

## Versions

- **V1**: Historical JD customer-service QA pairs only.
- **V2**: Historical QA pairs plus reviewed structured service-script knowledge snippets and safety controls.

## Key Features

- FastAPI web demo
- Embedding-based retrieval
- Rule-based reranking
- Mixed RAG corpus for V2
- Pre-retrieval intent guards
- Backend capability boundary
- Risky answer filtering
- Conservative response templates
- Final answer cleanup
- V2 evaluation script

## Run Web Demo

```bash
py -3 -m uvicorn app:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Run V2 Evaluation

```bash
py -3 scripts/run_v2_rag_test.py
```

The evaluation report is saved under:

```text
outputs/reports/
```

## Data Privacy

Raw customer chat logs and private backend-related data are not included in this repository. Only reviewed knowledge snippets and anonymised or non-sensitive supporting files are included.