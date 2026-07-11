# Context Design

## 1. Motivation

In real e-commerce customer-service chats, users rarely type one complete, self-contained question. Instead, they often send **fragmented multi-turn messages**.

Typical product follow-up pattern:

1. `这鞋防滑吗`
2. `真的吗`
3. `下雨呢`

Typical aftersales follow-up pattern:

1. `能补发么39码么`
2. `我这个退回去`

From a retrieval perspective, the second-turn utterances are incomplete. Without previous-turn context, a RAG system may:

- treat “真的吗” as an unclear short query;
- retrieve unrelated historical QA;
- drop an already established safety boundary;
- answer a logistics follow-up as if it were a new ordinary retrieval question.

Therefore, the chatbot must handle **fragmented and multi-turn customer messages**, not only clean single-turn queries.

This document describes:

- offline context handling during historical chat preprocessing;
- online lightweight context handling in **V2.1a**;
- current limitations revealed by baseline evaluation;
- planned structured conversation-state design for **V2.1b**.

## 2. Offline Context Handling in Data Preprocessing

Before online RAG, historical JD customer-service chats are processed into reusable QA pairs. Offline context handling is important because raw chat logs are turn-based and noisy.

Main preprocessing steps:

1. **Parse raw JD chat logs**  
   Extract timestamps, speaker roles, and message text from historical customer-service exports.

2. **Split conversations by session**  
   Keep each customer–agent conversation within its session boundary so that context is not mixed across unrelated buyers.

3. **Merge consecutive user messages**  
   Customers often send several short messages in sequence. Merging consecutive user turns recovers a more complete user intent for QA extraction.

4. **Merge consecutive customer-service messages**  
   Agents may reply in multiple bubbles. Merging consecutive agent turns produces a more coherent answer candidate.

5. **Extract QA pairs**  
   Convert cleaned user/agent segments into question–answer pairs suitable for retrieval.

6. **Clean and anonymise data**  
   Remove empty content, reduce personally identifiable information where practical, and normalise noisy text.

7. **Filter short / invalid / risky content**  
   Drop unusable fragments and reduce unsafe historical promises that should not become retrieval targets without further filtering.

**Design rationale:** consecutive user-message merging improves recovery of real user intent. For example, fragmented messages such as “39码” + “能补发吗” are more useful as one aftersales intent than as two isolated retrieval queries.

The resulting cleaned historical corpus used in V2.1a contains **15,333** JD QA pairs. These are combined with **355** manually reviewed structured knowledge snippets into a mixed corpus of **15,688** documents.

## 3. Online Context Handling in V2.1a

V2.1a introduces **lightweight online follow-up handling** on top of the mixed-corpus RAG pipeline. It is intentionally rule-based and minimal, rather than a full dialogue-state tracker.

### 3.1 Session memory

The Web demo keeps a short in-memory session history. For each new user message, the system can pass:

- `previous_user_query`
- `previous_assistant_answer`

into `run_rag_query()`.

### 3.2 Follow-up detection

The system detects short confirmation / continuation queries using phrase lists and length heuristics, for example:

- `真的吗`
- `确定吗`
- `那怎么办`
- `真不可以吗`
- `我这个退回去`

Intent-priority queries (identity, human handover, abusive/irrelevant, backend-required standalone triggers) are excluded from ordinary follow-up rewriting when appropriate.

### 3.3 Contextual query construction

When a follow-up is detected and previous context exists, V2.1a builds a `contextual_query` that combines previous topic cues with the current short utterance. Topic-specific rewrite rules exist for cases such as:

- anti-slip follow-ups;
- post-shipment refund follow-ups;
- quality / compensation follow-ups;
- foot-discomfort follow-ups.

The contextual query is then used as the retrieval query.

### 3.4 Debug visibility

V2.1a exposes debug fields for inspection and evaluation, including:

- `original_query`
- `is_followup_query`
- `contextual_query`
- `previous_user_query`
- `retrieval_query`
- `inherited_financial_risk`
- `inherited_aftersales_operation`

This visibility is important for dissertation analysis and for comparing later context designs.

## 4. Safety Boundary Inheritance

In addition to topical follow-up rewriting, V2.1a supports **safety-boundary inheritance** for high-risk dialogues. This is necessary because users often challenge a refusal with a short confirmation rather than restating the risky request.

### 4.1 Financial risk follow-up inheritance

If the previous turn was a financial-risk query (for example, compensation, price difference, shipping-fee reimbursement, refund status, payment transfer, discount, invoice, or legal compensation), and the current turn is a short confirmation follow-up, V2.1a inherits the same financial safe answer and skips ordinary retrieval.

Example:

1. `好评能返现吗`
2. `真不可以吗`

Expected behaviour: remain in `review_incentive_request` safe boundary; do not retrieve unrelated historical QA.

### 4.2 Review incentive and compensation inheritance

Review-cashback and concrete-compensation dialogues are covered by the financial inheritance path. Short challenges such as `真的不行吗` should continue to refuse unsafe commitments.

Example:

1. `能给我补偿两块吗`
2. `真的不行吗`

### 4.3 Aftersales operation follow-up inheritance

If the previous turn was an aftersales operation request (reshipment, size exchange, replacement, backend note), a short continuation such as returning the item or asking for a note should inherit the aftersales safe boundary.

Example:

1. `能补发么39码么`
2. `我这个退回去`

Expected behaviour: remain in `aftersales_operation_request`; do not answer with courier-policy or “already noted / already reshipped” historical phrases.

### 4.4 Design principle

Safety inheritance in V2.1a is **risk-type specific**. It is implemented as targeted inheritance functions rather than a general conversation-state machine. This reduces unsafe RAG leakage quickly, but it does not cover every backend-required follow-up pattern.

## 5. Current Limitation

V2.1a is a **rule-based lightweight context design**, not complete structured state tracking.

It can:

- rewrite some topical follow-ups;
- inherit selected financial and aftersales risk boundaries.

It does **not** yet maintain a general conversation state object that persists fields such as:

- current topic;
- active query type;
- whether backend access is required;
- last safe answer type.

### Evidence from baseline evaluation

In the V2.1a baseline evaluation (`evaluation/v21a_baseline_cases.json`), case **M017** failed:

- Turn 1: `我的物流到哪了`
- Turn 2: `那你帮我查一下`

Observed problem:

- the second turn did **not** inherit `backend_required` state;
- the system entered ordinary RAG retrieval;
- the answer leaked a placeholder logistics-style reply instead of preserving backend/handover behaviour.

This failure is important. Financial and aftersales confirmation follow-ups already pass, but backend-required follow-ups remain incompletely covered. That gap motivates V2.1b.

## 6. Planned V2.1b Context Design

V2.1b is planned as a move from scattered follow-up rules to **structured conversation state tracking**.

### 6.1 Proposed state fields

A conversation state object may include:

- `current_topic`
- `query_type`
- `risk_type` / `risk_level`
- `requires_backend_api`
- `last_safe_answer_type`
- optional inheritance metadata

### 6.2 Example state JSON

For the failed logistics dialogue, Turn 1 should establish a state similar to:

```json
{
  "current_topic": "logistics_status",
  "query_type": "backend_required",
  "requires_backend_api": true,
  "risk_level": "backend_operation",
  "last_safe_answer_type": "backend_required_answer"
}
```

When the user continues with `那你帮我查一下`, V2.1b should:

1. detect that the current utterance is a short follow-up / action request;
2. read the previous conversation state;
3. inherit `requires_backend_api = true`;
4. skip ordinary retrieval;
5. return the backend-required safe handover answer.

### 6.3 Intended coverage

Structured state tracking should generalise beyond today’s separate inheritance functions and support at least:

- backend-required state inheritance;
- financial risk state inheritance;
- aftersales operation state inheritance;
- topical product/policy continuation where useful.

### 6.4 Encoding and data-quality requirement

All V2.1b test inputs, detector keywords, contextual-query templates, comments,
debug fixtures, evaluation cases, and generated reports must use readable
Simplified Chinese encoded as UTF-8. Mojibake must never be treated as a valid
user-intent example or detector keyword.

Canonical examples include:

- `我的物流到哪了？` → `那你帮我查一下？`
- `退款多久到账？` → `那你帮我查一下？`
- `我的订单现在什么状态？` → `你能看一下吗？`
- `这鞋防滑吗？` → `能给我补偿两块吗？`
- `这鞋防滑吗？` → `下雨呢？`
- `能给我补偿两块吗？` → `真不可以吗？`
- a readable reshipment or exchange request → `我这个退回去`

Implementation checklist:

1. Save every modified Python, JSON, CSV, Markdown, JavaScript, or HTML file
   containing Chinese as UTF-8.
2. Use `encoding="utf-8"` for Python reads and writes involving Chinese.
3. Use `ensure_ascii=False` when serialising JSON intended for human review.
4. Do not convert already-corrupted text into canonical detector inputs.
5. Run the reusable mojibake sanity check over test queries, follow-up detector
   keywords, contextual-query templates, expected answer keywords, and loaded
   V2.1b evaluation cases before behavioural evaluation begins.
6. Fail early with a clear encoding/data-quality error if corrupted text is
   found.

## 7. Expected Benefit

Compared with V2.1a’s lightweight rule patches, V2.1b structured conversation state is expected to:

1. **Reduce missed inheritance cases** such as M017;
2. **Make multi-turn behaviour more systematic**, instead of adding one-off phrase rules for each failure mode;
3. **Improve debugability**, because the active topic/risk/backend state can be inspected directly;
4. **Support fair version comparison**, using the same baseline evaluation cases to measure whether multi-turn context accuracy improves from V2.1a to V2.1b;
5. **Align better with real customer chat behaviour**, where users continue a previous request with short operational follow-ups rather than restating the full question.

In short, V2.1a demonstrates that lightweight follow-up handling and risk inheritance are necessary and already effective for many safety-critical dialogues. V2.1b aims to make conversation context a first-class system component rather than a collection of specialised patches.
