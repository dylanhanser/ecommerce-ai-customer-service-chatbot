# Project Requirements

## 1. Project Scope

This project develops a **domain-specific e-commerce customer-service chatbot** for footwear retail support, rather than a general-purpose conversational assistant.

The system is designed to assist with repetitive product, policy, and after-sales questions that commonly appear in online shoe-store customer service. It combines retrieval-augmented generation (RAG) over historical JD customer-service conversations and manually reviewed structured knowledge snippets, with explicit safety boundaries for high-risk financial and operational requests.

The current system version is **V2.1a**. It is implemented as a FastAPI Web demo with mixed-corpus retrieval, rule-based reranking, DeepSeek / mock LLM answer generation, intent and risk guards, and lightweight multi-turn follow-up handling.

This is an applied research and engineering project. Its academic goal is to evaluate how retrieval quality, knowledge structuring, safety filters, and conversation-context design affect customer-service answer quality in a real e-commerce setting.

## 2. Target Users

The system is intended for three primary user groups:

1. **Online customers**  
   Customers asking product-attribute, size, shipping, return/exchange, quality, refund, or after-sales questions through chat.

2. **E-commerce customer-service staff**  
   Human agents who may use the system as a draft assistant for common questions, while retaining responsibility for order-specific decisions and backend operations.

3. **Store owner / business operator**  
   A business stakeholder who wants to reduce repetitive support workload, improve response consistency, and lower the risk of unsafe historical replies being reused.

Secondary users include developers and researchers who inspect debug fields, evaluation reports, and regression results during system iteration.

## 3. Business Scenarios

The chatbot must support the following business scenarios:

| Scenario | Example user intent |
| --- | --- |
| Product attribute questions | Anti-slip performance, sole softness, breathability, authenticity, materials |
| Size consultation | Whether sizing runs large/small, wide-foot advice, size mapping |
| Return and exchange policy | Whether returns/exchanges are supported; seven-day no-reason return |
| Shipping and freight insurance | Courier options, freight insurance availability |
| Quality-related questions | Glue separation, wrong item shipped, foot discomfort (with medical boundary) |
| Backend-required questions | Live logistics, order status, refund progress, courier urging |
| Financial risk questions | Compensation amounts, price difference, shipping-fee reimbursement, discounts, invoices, payment transfer |
| Review incentive questions | Cashback for positive reviews, screenshot rewards |
| Aftersales operation questions | Reshipment, size exchange, replacement, backend notes |
| Multi-turn fragmented messages | Short confirmations and follow-ups such as “真的吗”, “下雨呢”, “我这个退回去” |

These scenarios reflect real JD footwear customer-service traffic, where users often mix product questions with policy, logistics, and negotiation-style requests.

## 4. Functional Requirements

### FR1: Answer common product questions using RAG

The system shall retrieve relevant knowledge and generate customer-service style answers for common product questions, such as anti-slip performance, sole hardness, and related footwear attributes.

### FR2: Retrieve from historical QA pairs and reviewed structured knowledge

The system shall retrieve from a mixed corpus containing:

- cleaned JD historical customer-service QA pairs;
- manually reviewed structured service-script knowledge snippets.

Current corpus scale used in V2.1a:

- **15,333** cleaned JD historical QA pairs;
- **355** manually reviewed structured knowledge snippets;
- **15,688** total mixed corpus documents.

### FR3: Generate customer-service style responses

The system shall produce concise, polite, customer-service-oriented answers. When LLM generation is unavailable, a reproducible mock fallback must still return a usable answer.

### FR4: Handle short follow-up queries

The system shall detect short multi-turn follow-ups (for example, “真的吗”, “下雨呢”, “那怎么办”) and use previous-turn context to avoid treating them as isolated standalone queries when previous context is available.

### FR5: Detect backend-required questions and avoid pretending to access backend systems

The system shall identify questions that require live order, logistics, refund, or courier-operation data. In such cases it must not invent tracking results, refund arrival times, or completed backend actions. It should recommend human verification.

### FR6: Detect compensation, refund amount, price difference and shipping-fee reimbursement risks

The system shall detect financial-risk queries involving compensation amounts, refund status/amount, price-difference claims, shipping-fee reimbursement, payment transfer, discounts/price changes, invoices, and legal compensation requests, and return safe boundary answers without concrete commitments.

### FR7: Detect review cashback / rating incentive risks

The system shall detect review-incentive requests (for example, cashback for five-star reviews or screenshot rewards) and refuse to promise evaluation incentives.

### FR8: Detect after-sales operation requests such as reshipment, exchange, size replacement and backend notes

The system shall detect aftersales operation requests, including reshipment, size exchange, replacement shipment, and requests to add backend notes or arrange exchanges, and shall not pretend that such operations have already been completed.

### FR9: Filter risky historical QA answers

The system shall filter or suppress risky historical customer-service answers that claim completed backend actions or unsafe promises, such as already refunded, already paid, review cashback, concrete compensation amounts, already noted, already arranged, or already reshipped.

### FR10: Provide debug information for development and evaluation

The system shall expose debug fields useful for development and evaluation, including query type, skip-retrieval status, backend requirement, follow-up status, retrieval query, inheritance flags, and top retrieved/reranked results.

## 5. Non-functional Requirements

### 5.1 Safety

The system must prioritise safe refusal and human handover over fluent but risky commitments, especially for money, backend operations, review incentives, and medical diagnosis.

### 5.2 Reliability

Core guards and retrieval behaviour should behave consistently across repeated runs on the same corpus and the same query set.

### 5.3 Reproducibility

Baseline evaluation should be runnable without an external LLM judge. Mock LLM mode must support deterministic regression and baseline comparison across versions.

### 5.4 Data privacy

Historical chat logs used for corpus construction should be cleaned and anonymised where practical. The demo must not require exposing real customer order credentials to the chatbot.

### 5.5 Response speed

Interactive Web demo responses should remain suitable for local demonstration, with embedding cache reuse to avoid rebuilding the full corpus on every query.

### 5.6 Maintainability

Guards, evaluation cases, and documentation should be organised so that later versions (for example, V2.1b structured conversation state) can be compared without rewriting the entire system.

### 5.7 Explainability / debug visibility

Developers and evaluators should be able to inspect why a query skipped retrieval, which query type was assigned, whether financial or aftersales inheritance occurred, and which corpus item ranked first.

## 6. System Boundaries

The V2.1a system explicitly **cannot**:

- access a real order backend;
- check live logistics or refund status;
- promise compensation amounts;
- promise review cashback or rating incentives;
- perform backend operations such as note-taking, reshipment, exchange arrangement, interception, or courier urging;
- make medical diagnoses for foot discomfort;
- modify order prices or guarantee extra discounts;
- confirm invoice registration or payment transfer completion.

When such capabilities are required, the correct system behaviour is to explain the limitation and recommend human customer-service verification.

## 7. Success Criteria

The project is considered successful if it can demonstrate measurable progress on the following criteria:

1. **Relevant answers for common questions**  
   Product, size, and ordinary policy questions receive topically relevant answers grounded in retrieved knowledge.

2. **Correct handover for backend-required cases**  
   Live order/logistics/refund queries trigger backend-required handling and human handover rather than fabricated status.

3. **No risky historical answer leakage**  
   High-risk historical phrases (for example, already refunded, review cashback, already noted, concrete compensation) are not emitted as final answers in safety-critical evaluation cases.

4. **Multi-turn follow-up handling**  
   Short follow-ups can inherit topic or risk boundaries in supported scenarios (product follow-ups, financial confirmation, aftersales confirmation).

5. **Measurable improvement over earlier versions**  
   Version progression from historical-QA-only retrieval to mixed corpus and lightweight follow-up handling can be shown through regression tests and a formal baseline evaluation.

### Current V2.1a baseline evidence

On the fixed baseline evaluation set (`evaluation/v21a_baseline_cases.json`):

- 40 single-turn + 20 multi-turn cases;
- **59/60** passed (**98.3%** overall pass rate);
- average relevance **1.933**, average correctness **1.950**;
- safety boundary accuracy **100%** (42/42);
- handover appropriateness **97.3%** (36/37);
- multi-turn context accuracy **95%** (19/20);
- risky leakage rate **0%** (0/60).

The remaining failure (M017: logistics follow-up “那你帮我查一下”) motivates the planned V2.1b structured conversation-state design described in `docs/context_design.md`.
