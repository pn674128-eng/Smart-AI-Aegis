const cols = {
  antigravity: document.getElementById("col-ag"),
  cursor: document.getElementById("col-cu"),
  aegis: document.getElementById("col-ae"),
  master: document.getElementById("col-ma"),
};

function renderMessages(column, items) {
  column.innerHTML = "";
  (items || []).forEach((m) => {
    const div = document.createElement("div");
    div.className = "msg";
    div.innerHTML =
      `<div class="meta">${m.role || ""} · ${m.at || ""}</div>` +
      `<div>${escapeHtml(m.content || "")}</div>`;
    column.appendChild(div);
  });
  column.scrollTop = column.scrollHeight;
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

async function api(path, body) {
  const opt = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify(body),
      }
    : {};
  const r = await fetch(path, opt);
  return r.json();
}

function setStatus(t) {
  document.getElementById("status-bar").textContent = t;
}

async function refresh() {
  const data = await api("/api/session");
  if (data.columns) {
    renderMessages(cols.antigravity, data.columns.antigravity);
    renderMessages(cols.cursor, data.columns.cursor);
    renderMessages(cols.aegis, data.columns.aegis);
    renderMessages(cols.master, data.columns.master);
  }
  const st = data.collab_status;
  if (st) {
    const miss = (st.missing_participants || []).join(", ") || "無";
    setStatus(
      `ticket ${data.session?.ticket_id || "—"} | 討論 ${st.discussion_turns?.total || 0} 則 | 缺發言: ${miss}`
    );
  }
}

document.getElementById("btn-start").onclick = async () => {
  const topic = prompt("協作主題", "四方協作") || "四方協作";
  setStatus("啟動中…");
  const r = await api("/api/start", { topic });
  if (!r.ok) {
    setStatus("啟動失敗: " + (r.data?.error || r.error || "unknown"));
    return;
  }
  await refresh();
  setStatus("協作已啟動 — 在下方輸入，三方將同輪回覆");
};

document.getElementById("btn-refresh").onclick = refresh;

document.getElementById("btn-send").onclick = async () => {
  const text = document.getElementById("input").value.trim();
  if (!text) return;
  const btn = document.getElementById("btn-send");
  btn.disabled = true;
  setStatus("三方思考中…（約 15～45 秒）");
  const r = await api("/api/send", {
    text,
    reply_antigravity: document.getElementById("chk-ag").checked,
    reply_cursor: document.getElementById("chk-cu").checked,
    reply_aegis: document.getElementById("chk-ae").checked,
  });
  btn.disabled = false;
  if (!r.ok) {
    setStatus("發送失敗: " + (r.error || JSON.stringify(r.data)));
    return;
  }
  document.getElementById("input").value = "";
  if (r.columns) {
    renderMessages(cols.antigravity, r.columns.antigravity);
    renderMessages(cols.cursor, r.columns.cursor);
    renderMessages(cols.aegis, r.columns.aegis);
    renderMessages(cols.master, r.columns.master);
  }
  await refresh();
};

document.getElementById("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    document.getElementById("btn-send").click();
  }
});

refresh();
setInterval(refresh, 8000);
