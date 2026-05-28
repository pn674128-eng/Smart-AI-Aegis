// cam-helper Web UI - vanilla JS, SSE streaming chat
// 0 dependencies, 0 CDN

(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const messagesEl = $('#messages');
  const inputEl = $('#input');
  const sendBtn = $('#btn-send');
  const stopBtn = $('#btn-stop');
  const resetBtn = $('#btn-reset');
  const toolsListEl = $('#tools-list');
  const toolsCountEl = $('#tools-count');

  let currentController = null;
  let currentAssistantBubble = null;
  let currentToolsContainer = null;
  let isFirstMessage = true;
  let startTime = 0;

  // ================================
  //  Init
  // ================================

  refreshStatus();
  refreshTools();
  setInterval(refreshStatus, 8000);

  // 點擊建議問題
  $$('.suggested').forEach((b) => {
    b.addEventListener('click', () => {
      inputEl.value = b.dataset.q;
      send();
    });
  });

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      send();
    } else if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
      // 單獨 Enter 不送（避免誤觸），用 Ctrl+Enter
    } else if (e.key === 'Escape') {
      stopGeneration();
    }
  });

  sendBtn.addEventListener('click', send);
  stopBtn.addEventListener('click', stopGeneration);
  resetBtn.addEventListener('click', resetConversation);

  // ================================
  //  Status
  // ================================

  async function refreshStatus() {
    try {
      const r = await fetch('/api/status');
      const data = await r.json();
      $('#status-ollama').className = 'status-dot ' +
        (data.ollama.ok ? 'dot-ok' : 'dot-fail');
      $('#status-ollama').title = data.ollama.ok
        ? '在線 (' + (data.ollama.models || []).length + ' models)'
        : '離線: ' + (data.ollama.error || '');
      $('#status-mcp').className = 'status-dot ' +
        (data.mcp.ok ? 'dot-ok' : 'dot-fail');
      $('#status-mcp').title = data.mcp.ok
        ? data.mcp.host + ':' + data.mcp.port
        : 'MCP 離線';
      $('#status-model').textContent = data.model;
      $('#status-history').textContent = data.history_len;
    } catch (e) {
      $('#status-ollama').className = 'status-dot dot-fail';
      $('#status-mcp').className = 'status-dot dot-fail';
    }
  }

  async function refreshTools() {
    try {
      const r = await fetch('/api/tools');
      const data = await r.json();
      const tools = data.tools || [];
      toolsCountEl.textContent = tools.length;
      toolsListEl.innerHTML = '';
      tools.forEach((t) => {
        const div = document.createElement('div');
        div.className = 'tool-item';
        div.title = t.desc;
        div.innerHTML =
          '<div class="tool-name">' + esc(t.name) + '</div>' +
          '<div class="tool-desc">' + esc(t.desc) + '</div>';
        toolsListEl.appendChild(div);
      });
    } catch (e) {
      toolsListEl.innerHTML = '<div class="tool-loading">載入失敗</div>';
    }
  }

  // ================================
  //  Send / Stream
  // ================================

  function send() {
    const text = inputEl.value.trim();
    if (!text) return;
    if (currentController) return;  // 已在生成中

    if (isFirstMessage) {
      // 移除 welcome
      const welcome = messagesEl.querySelector('.welcome');
      if (welcome) welcome.remove();
      isFirstMessage = false;
    }

    appendUserMessage(text);
    inputEl.value = '';
    inputEl.style.height = 'auto';

    appendAssistantPlaceholder();

    setSendingState(true);
    startTime = performance.now();

    streamChat(text);
  }

  async function streamChat(message) {
    currentController = new AbortController();
    let assistantText = '';
    let tokenCount = 0;

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
        signal: currentController.signal,
      });

      if (!resp.ok) {
        appendError('HTTP ' + resp.status);
        setSendingState(false);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 拆 SSE event
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const ev of events) {
          if (!ev.trim()) continue;
          const parsed = parseSSE(ev);
          if (!parsed) continue;
          handleSSEEvent(parsed.event, parsed.data, () => tokenCount++);
        }
      }

      finalizeAssistantMessage(tokenCount);
    } catch (e) {
      if (e.name !== 'AbortError') {
        appendError(String(e.message || e));
      } else {
        finalizeAssistantMessage(tokenCount, '(已停止)');
      }
    } finally {
      currentController = null;
      setSendingState(false);
      refreshStatus();
    }
  }

  function parseSSE(text) {
    let event = 'message';
    let data = '';
    for (const line of text.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    if (!data) return null;
    try {
      return { event: event, data: JSON.parse(data) };
    } catch {
      return null;
    }
  }

  function handleSSEEvent(event, data, onToken) {
    switch (event) {
      case 'token':
        appendTokenToCurrentBubble(data.text);
        onToken();
        break;
      case 'tool_call':
        appendToolChip(data.name, data.args);
        break;
      case 'tool_result':
        markToolDone(data.name, data);
        break;
      case 'status':
        // optional: show round indicator
        break;
      case 'done':
        // 結束 - 內容已經透過 token 累積
        break;
      case 'error':
        appendError(data.message || 'Unknown error');
        break;
    }
  }

  function stopGeneration() {
    if (currentController) {
      currentController.abort();
    }
  }

  async function resetConversation() {
    if (!confirm('清空對話歷史？')) return;
    await fetch('/api/reset', { method: 'POST' });
    messagesEl.innerHTML = '';
    isFirstMessage = true;
    location.reload();
  }

  // ================================
  //  DOM helpers
  // ================================

  function appendUserMessage(text) {
    const msg = document.createElement('div');
    msg.className = 'msg user';
    msg.innerHTML =
      '<div class="role">你</div>' +
      '<div class="bubble"></div>';
    msg.querySelector('.bubble').textContent = text;
    messagesEl.appendChild(msg);
    scrollToBottom();
  }

  function appendAssistantPlaceholder() {
    const msg = document.createElement('div');
    msg.className = 'msg assistant';
    msg.innerHTML =
      '<div class="role">助理</div>' +
      '<div class="tool-calls"></div>' +
      '<div class="bubble"><span class="cursor"></span></div>' +
      '<div class="msg-meta"></div>';
    messagesEl.appendChild(msg);
    currentAssistantBubble = msg.querySelector('.bubble');
    currentToolsContainer = msg.querySelector('.tool-calls');
    scrollToBottom();
  }

  function appendTokenToCurrentBubble(text) {
    if (!currentAssistantBubble) return;
    // 移除 cursor，附加新內容，再加上 cursor
    const cursor = currentAssistantBubble.querySelector('.cursor');
    if (cursor) cursor.remove();
    currentAssistantBubble.appendChild(document.createTextNode(text));
    const newCursor = document.createElement('span');
    newCursor.className = 'cursor';
    currentAssistantBubble.appendChild(newCursor);
    scrollToBottom();
  }

  function appendToolChip(name, args) {
    if (!currentToolsContainer) return;
    const chip = document.createElement('div');
    chip.className = 'tool-chip';
    chip.dataset.name = name;
    chip.innerHTML =
      '<span class="spinner"></span>' +
      '<span>' + esc(name) + (args && Object.keys(args).length ? '(...)' : '()') + '</span>';
    chip.title = args ? JSON.stringify(args, null, 2) : '';
    currentToolsContainer.appendChild(chip);
    scrollToBottom();
  }

  function markToolDone(name, data) {
    if (!currentToolsContainer) return;
    const chip = currentToolsContainer.querySelector(
      '.tool-chip[data-name="' + name + '"]:not(.done):not(.fail):not(.offline)'
    );
    if (!chip) return;
    chip.querySelector('.spinner')?.remove();
    let icon = '✓';
    let cls = 'done';
    if (data.offline) { icon = '○'; cls = 'offline'; }
    else if (!data.success) { icon = '✗'; cls = 'fail'; }
    chip.classList.add(cls);
    const span = chip.querySelector('span:last-child');
    if (span) span.textContent = icon + ' ' + name;
    if (data.preview) chip.title = data.preview;
  }

  function finalizeAssistantMessage(tokenCount, suffix) {
    if (!currentAssistantBubble) return;
    // 移除 cursor
    currentAssistantBubble.querySelector('.cursor')?.remove();

    // 如果空，顯示提示
    if (!currentAssistantBubble.textContent.trim()) {
      currentAssistantBubble.textContent = suffix || '(模型未產生回應)';
    } else if (suffix) {
      currentAssistantBubble.appendChild(document.createTextNode(' ' + suffix));
    }

    // 套用簡易 markdown
    applyMarkdown(currentAssistantBubble);

    // Meta info
    const meta = currentAssistantBubble.parentElement.querySelector('.msg-meta');
    if (meta) {
      const dt = (performance.now() - startTime) / 1000;
      const tps = tokenCount > 0 ? (tokenCount / dt).toFixed(1) : '-';
      meta.textContent = `${dt.toFixed(1)}s · ${tokenCount} tokens · ${tps} tok/s`;
    }
    currentAssistantBubble = null;
    currentToolsContainer = null;
  }

  function appendError(message) {
    if (currentAssistantBubble) {
      const msg = currentAssistantBubble.parentElement;
      msg.classList.add('error');
      currentAssistantBubble.querySelector('.cursor')?.remove();
      currentAssistantBubble.textContent = '錯誤：' + message;
      currentAssistantBubble = null;
      currentToolsContainer = null;
      return;
    }
    const msg = document.createElement('div');
    msg.className = 'msg assistant error';
    msg.innerHTML =
      '<div class="role">錯誤</div>' +
      '<div class="bubble">' + esc(message) + '</div>';
    messagesEl.appendChild(msg);
    scrollToBottom();
  }

  function setSendingState(sending) {
    sendBtn.disabled = sending;
    stopBtn.disabled = !sending;
    inputEl.disabled = sending;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ================================
  //  Simple markdown
  // ================================

  function applyMarkdown(el) {
    let html = el.innerHTML;
    // 我們先存原始文字，應用 markdown 後 set innerHTML
    let text = el.textContent;
    text = esc(text);

    // code block ```...```
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, function (m, lang, code) {
      return '<pre><code>' + code.trim() + '</code></pre>';
    });

    // inline code `...`
    text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // bold **...**
    text = text.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');

    // 簡易表格（| col | col | with --- 分隔）
    text = text.replace(/((?:^\|.*\|$\n?)+)/gm, function (m) {
      const lines = m.trim().split('\n');
      if (lines.length < 2) return m;
      const isSep = lines[1].match(/^\|[\s\-|:]+\|$/);
      if (!isSep) return m;
      const headers = lines[0].slice(1, -1).split('|').map(s => s.trim());
      const rows = lines.slice(2).map(line =>
        line.slice(1, -1).split('|').map(s => s.trim())
      );
      let html = '<table><thead><tr>' +
        headers.map(h => '<th>' + h + '</th>').join('') +
        '</tr></thead><tbody>';
      rows.forEach(r => {
        html += '<tr>' + r.map(c => '<td>' + c + '</td>').join('') + '</tr>';
      });
      html += '</tbody></table>';
      return html;
    });

    el.innerHTML = text;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

})();
