const form = document.querySelector("#chatForm");
const input = document.querySelector("#questionInput");
const button = document.querySelector("#sendButton");
const chatWindow = document.querySelector("#chatWindow");
const finalAnswer = document.querySelector("#finalAnswer");
const backendFlag = document.querySelector("#backendFlag");
const invalidFlag = document.querySelector("#invalidFlag");
const skipFlag = document.querySelector("#skipFlag");
const queryTypeFlag = document.querySelector("#queryTypeFlag");
const retrievedResults = document.querySelector("#retrievedResults");
const rerankedResults = document.querySelector("#rerankedResults");

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "\u4f60" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  message.appendChild(avatar);
  message.appendChild(bubble);
  chatWindow.appendChild(message);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function setLoading(isLoading) {
  button.disabled = isLoading;
  input.disabled = isLoading;
  button.textContent = isLoading ? "\u751f\u6210\u4e2d..." : "\u53d1\u9001";
}

function asText(value) {
  return String(value ?? "");
}

function addTag(parent, text) {
  const span = document.createElement("span");
  span.className = "tag";
  span.textContent = text;
  parent.appendChild(span);
}

function renderResults(container, results, mode) {
  container.innerHTML = "";
  container.classList.remove("empty");

  if (!results || results.length === 0) {
    container.classList.add("empty");
    container.textContent = "\u6682\u65e0\u7ed3\u679c";
    return;
  }

  for (const item of results) {
    const card = document.createElement("article");
    card.className = "result-item";

    const meta = document.createElement("div");
    meta.className = "result-meta";
    const rankText =
      mode === "rerank"
        ? `#${item.rank} / original #${item.original_rank}`
        : `#${item.rank}`;
    addTag(meta, rankText);
    addTag(meta, `type: ${asText(item.source_type || "chat_qa")}`);
    if (item.needs_backend_api) {
      addTag(meta, "needs_backend_api");
    }
    addTag(meta, `category: ${asText(item.category)}`);
    addTag(meta, `similarity: ${asText(item.similarity)}`);
    if (mode === "rerank") {
      addTag(meta, `rerank: ${asText(item.rerank_score)}`);
      addTag(meta, `reason: ${asText(item.rerank_reason)}`);
    }

    const question = document.createElement("div");
    question.className = "result-question";
    const questionLabel = document.createElement("span");
    questionLabel.className = "label";
    questionLabel.textContent =
      item.source_type && item.source_type !== "chat_qa" ? "Title: " : "Q: ";
    question.appendChild(questionLabel);
    const questionText =
      item.source_type && item.source_type !== "chat_qa"
        ? asText(item.title || item.question)
        : asText(item.question);
    question.appendChild(document.createTextNode(questionText));

    const answer = document.createElement("div");
    answer.className = "result-answer";
    const answerLabel = document.createElement("span");
    answerLabel.className = "label";
    answerLabel.textContent =
      item.source_type && item.source_type !== "chat_qa" ? "Content: " : "A: ";
    answer.appendChild(answerLabel);
    answer.appendChild(document.createTextNode(asText(item.answer)));

    card.appendChild(meta);
    card.appendChild(question);
    card.appendChild(answer);
    container.appendChild(card);
  }
}

function renderSkipped(container) {
  container.innerHTML = "";
  container.classList.add("empty");
  container.textContent = "Skipped retrieval due to intent guard.";
}

function setFlag(element, label, value, isWarning) {
  element.textContent = `${label}: ${value}`;
  element.classList.toggle("true", Boolean(isWarning));
}

function renderResponse(data) {
  finalAnswer.textContent = data.final_answer || "";
  setFlag(invalidFlag, "Invalid input", data.invalid_input, data.invalid_input);
  setFlag(skipFlag, "Skip retrieval", data.skip_retrieval, data.skip_retrieval);
  setFlag(queryTypeFlag, "Query type", data.query_type || "-", false);
  setFlag(
    backendFlag,
    "Requires backend API",
    data.requires_backend_api,
    data.requires_backend_api,
  );
  if (data.skip_retrieval) {
    renderSkipped(retrievedResults);
    renderSkipped(rerankedResults);
  } else {
    renderResults(retrievedResults, data.retrieved_results, "retrieved");
    renderResults(rerankedResults, data.reranked_results, "rerank");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();

  appendMessage("user", question || "\uff08\u7a7a\u8f93\u5165\uff09");
  input.value = "";
  setLoading(true);
  finalAnswer.textContent = "\u6b63\u5728\u5904\u7406...";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const data = await response.json();
    renderResponse(data);
    appendMessage("bot", data.final_answer || "\u6ca1\u6709\u751f\u6210\u56de\u7b54\u3002");
  } catch (error) {
    const message = `\u8bf7\u6c42\u5931\u8d25\uff1a${error.message}`;
    finalAnswer.textContent = message;
    appendMessage("bot", message);
  } finally {
    setLoading(false);
    input.focus();
  }
});
