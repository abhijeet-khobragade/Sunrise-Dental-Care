// Chat widget: talks to the FastAPI backend at /api/chat.

const chat = document.getElementById("chat");
const launcher = document.getElementById("launcher");
const messages = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const chips = document.getElementById("chips");

const WELCOME =
  "Hi! 👋 I'm the Sunrise Dental Care assistant. I can answer questions about our " +
  "treatments, prices and timings, or book an appointment for you. How can I help?";

// Each browser gets its own conversation id, remembered across page reloads.
function newSessionId() {
  return crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);
}
let sessionId;
try {
  sessionId = localStorage.getItem("chat_session") || newSessionId();
  localStorage.setItem("chat_session", sessionId);
} catch {
  sessionId = newSessionId();
}

// ---------- Rendering ----------

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Minimal, safe Markdown: **bold** and "- " bullet lists. HTML is escaped first,
// so nothing the bot (or a user) writes can inject scripts into the page.
function renderMarkdown(text) {
  const bold = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  let html = "";
  let inList = false;
  for (const line of escapeHtml(text).split("\n")) {
    const item = line.match(/^\s*[-*•]\s+(.*)/);
    if (item) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${bold(item[1])}</li>`;
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim()) html += `<p>${bold(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "bot") div.innerHTML = renderMarkdown(text);
  else div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function addBadge(text) {
  const div = document.createElement("div");
  div.className = "badge";
  div.textContent = "✓ " + text;
  messages.appendChild(div);
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "msg bot typing";
  div.id = "typing";
  div.innerHTML = "<span></span><span></span><span></span>";
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function hideTyping() {
  document.getElementById("typing")?.remove();
}

// ---------- Sending ----------

let busy = false;

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  sendBtn.disabled = true;
  chips.hidden = true;
  addMessage("user", text);
  input.value = "";
  autoGrow();
  showTyping();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });
    const data = await res.json().catch(() => ({}));
    hideTyping();
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
      addMessage("error", detail);
    } else {
      data.actions.forEach(addBadge);
      addMessage("bot", data.reply);
    }
  } catch {
    hideTyping();
    addMessage("error", "Can't reach the server. Check your connection and try again.");
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

function autoGrow() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
}

// ---------- Events ----------

function openChat() {
  chat.hidden = false;
  if (!messages.children.length) addMessage("bot", WELCOME);
  input.focus();
}

launcher.addEventListener("click", () => (chat.hidden ? openChat() : (chat.hidden = true)));
document.getElementById("hero-chat").addEventListener("click", openChat);
document.getElementById("close-chat").addEventListener("click", () => (chat.hidden = true));

document.getElementById("new-chat").addEventListener("click", async () => {
  if (busy) return;
  fetch("/api/chat/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message: "reset" }),
  }).catch(() => {});
  sessionId = newSessionId();
  try { localStorage.setItem("chat_session", sessionId); } catch {}
  messages.innerHTML = "";
  chips.hidden = false;
  addMessage("bot", WELCOME);
});

form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});

// Enter sends, Shift+Enter adds a new line.
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send(input.value);
  }
});
input.addEventListener("input", autoGrow);

chips.querySelectorAll(".chip").forEach((chip) =>
  chip.addEventListener("click", () => send(chip.textContent))
);
