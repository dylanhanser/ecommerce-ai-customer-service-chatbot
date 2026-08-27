const form = document.querySelector("#chatForm");
const input = document.querySelector("#questionInput");
const button = document.querySelector("#sendButton");
const chatWindow = document.querySelector("#chatWindow");
const pageLayout = document.querySelector(".page");
const internalDebugPanel = document.querySelector(".debug-card");

if (internalDebugPanel) {
  internalDebugPanel.remove();
}

if (pageLayout) {
  pageLayout.classList.add("chat-only");
}

function appendMessage(role, text) {
  const message = document.createElement("div");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "\u4f60" : "AI";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.appendChild(document.createTextNode(String(text ?? "")));

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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();

  appendMessage("user", question || "\uff08\u7a7a\u8f93\u5165\uff09");
  input.value = "";
  setLoading(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    const data = await response.json().catch(() => ({}));
    const answer =
      typeof data.final_answer === "string" && data.final_answer
        ? data.final_answer
        : "\u6682\u65f6\u65e0\u6cd5\u5904\u7406\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002";
    appendMessage("bot", answer);
  } catch {
    appendMessage("bot", "\u6682\u65f6\u65e0\u6cd5\u5904\u7406\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
  } finally {
    setLoading(false);
    input.focus();
  }
});
