// ==UserScript==
// @name         Else AI Companion
// @namespace    https://else.fcim.utm.md
// @version      2.0.0
// @description  AI assistant for Moodle courses — chat, quiz, indexing
// @author       Else AI Companion
// @match        https://else.fcim.utm.md/*
// @match        https://*.moodle.org/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      localhost
// @run-at       document-idle
// @require      https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js
// ==/UserScript==

(function () {
  'use strict';

  // ── CONFIG ───────────────────────────────────────────────────────────────
  const API = 'http://localhost:8000';

  // ── STYLES ───────────────────────────────────────────────────────────────
  // Inject KaTeX CSS for math formula rendering
  const _katexCss = document.createElement('link');
  _katexCss.rel = 'stylesheet';
  _katexCss.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css';
  document.head.appendChild(_katexCss);

  const _style = document.createElement('style');
  _style.textContent = `
    :root {
      --ec-bg:       #111111;
      --ec-bg2:      #1a1a1a;
      --ec-bg3:      #222222;
      --ec-bg4:      #2a2a2a;
      --ec-accent:   #6366f1;
      --ec-accent-h: #4f46e5;
      --ec-green:    #22c55e;
      --ec-red:      #ef4444;
      --ec-text:     #f4f4f5;
      --ec-text-dim: #71717a;
      --ec-text-sub: #a1a1aa;
      --ec-border:   #2e2e2e;
      --ec-radius:   10px;
      --ec-shadow:   0 16px 48px rgba(0,0,0,0.6);
      --ec-font:     'Inter', 'Segoe UI', system-ui, sans-serif;
    }

    #ec-widget {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      font-family: var(--ec-font);
      font-size: 13px;
      color: var(--ec-text);
    }

    /* ── FAB ────────────────────────────────────── */
    #ec-fab {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: var(--ec-accent);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 20px rgba(99,102,241,0.4);
      transition: background .15s, transform .15s, box-shadow .15s;
      margin-left: auto;
    }
    #ec-fab:hover {
      background: var(--ec-accent-h);
      transform: translateY(-1px);
      box-shadow: 0 8px 28px rgba(99,102,241,0.5);
    }
    #ec-fab svg { width: 20px; height: 20px; fill: white; }

    /* ── Panel ──────────────────────────────────── */
    #ec-panel {
      width: 370px;
      height: 560px;
      background: var(--ec-bg);
      border: 1px solid var(--ec-border);
      border-radius: var(--ec-radius);
      box-shadow: var(--ec-shadow);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 10px;
      transition: opacity .2s, transform .2s;
    }
    #ec-panel.ec-hidden { opacity: 0; pointer-events: none; transform: translateY(8px) scale(.98); }

    /* ── Header ─────────────────────────────────── */
    #ec-header {
      background: var(--ec-bg2);
      padding: 13px 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 1px solid var(--ec-border);
      flex-shrink: 0;
    }
    #ec-header-icon {
      width: 28px; height: 28px;
      background: var(--ec-accent);
      border-radius: 7px;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    #ec-header-icon svg { width: 15px; height: 15px; fill: white; }
    #ec-header-info { flex: 1; min-width: 0; }
    #ec-header-title { font-weight: 600; font-size: 13px; color: var(--ec-text); line-height: 1.2; }
    #ec-header-sub { font-size: 11px; color: var(--ec-text-dim); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #ec-status-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--ec-green);
      box-shadow: 0 0 5px var(--ec-green);
      flex-shrink: 0;
      transition: background .3s, box-shadow .3s;
    }
    #ec-status-dot.offline { background: var(--ec-red); box-shadow: 0 0 5px var(--ec-red); }

    /* ── Tabs ───────────────────────────────────── */
    #ec-tabs {
      display: flex;
      background: var(--ec-bg2);
      border-bottom: 1px solid var(--ec-border);
      padding: 0 8px;
      gap: 2px;
      flex-shrink: 0;
    }
    .ec-tab {
      flex: 1;
      padding: 9px 6px;
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--ec-text-dim);
      cursor: pointer;
      font-size: 11px;
      font-family: var(--ec-font);
      font-weight: 500;
      letter-spacing: .3px;
      text-transform: uppercase;
      transition: color .15s, border-color .15s;
    }
    .ec-tab:hover { color: var(--ec-text-sub); }
    .ec-tab.active { color: var(--ec-accent); border-bottom-color: var(--ec-accent); }

    /* ── Tab panes ──────────────────────────────── */
    .ec-pane { display: none; flex: 1; flex-direction: column; overflow: hidden; }
    .ec-pane.active { display: flex; }

    /* ── Chat ───────────────────────────────────── */
    #ec-messages {
      flex: 1;
      overflow-y: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      scrollbar-width: thin;
      scrollbar-color: var(--ec-border) transparent;
    }
    .ec-msg {
      max-width: 86%;
      padding: 9px 13px;
      border-radius: 10px;
      line-height: 1.55;
      word-break: break-word;
      font-size: 13px;
    }
    .ec-msg.user {
      background: var(--ec-accent);
      color: white;
      align-self: flex-end;
      border-bottom-right-radius: 3px;
    }
    .ec-msg.assistant {
      background: var(--ec-bg2);
      color: var(--ec-text);
      align-self: flex-start;
      border-bottom-left-radius: 3px;
      border: 1px solid var(--ec-border);
    }
    .ec-msg.assistant code {
      background: var(--ec-bg3);
      padding: 1px 5px;
      border-radius: 4px;
      font-family: 'Menlo','Consolas',monospace;
      font-size: 12px;
    }
    .ec-msg.assistant pre {
      background: var(--ec-bg3);
      border: 1px solid var(--ec-border);
      border-radius: 6px;
      padding: 10px 12px;
      overflow-x: auto;
      margin: 6px 0;
      font-size: 12px;
      line-height: 1.5;
    }
    .ec-msg.assistant pre code {
      background: none;
      padding: 0;
      font-size: inherit;
    }
    .ec-msg.assistant .katex-display {
      margin: 6px 0;
      overflow-x: auto;
      overflow-y: hidden;
    }
    .ec-msg.assistant .katex {
      font-size: 1.05em;
    }
    .ec-msg.assistant h2, .ec-msg.assistant h3, .ec-msg.assistant h4 {
      margin: 8px 0 3px;
      color: var(--ec-text);
      font-weight: 600;
    }
    .ec-msg.assistant ul, .ec-msg.assistant ol {
      margin: 4px 0;
      padding-left: 18px;
    }
    .ec-msg.assistant li { margin: 2px 0; }
    .ec-sources {
      margin-top: 8px;
      padding-top: 7px;
      border-top: 1px solid var(--ec-border);
      font-size: 11px;
      color: var(--ec-text-dim);
    }
    .ec-sources span { display: block; margin-top: 2px; }
    .ec-msg.typing span {
      display: inline-block;
      width: 5px; height: 5px;
      background: var(--ec-text-dim);
      border-radius: 50%;
      margin: 0 2px;
      animation: ec-bounce .9s infinite;
    }
    .ec-msg.typing span:nth-child(2) { animation-delay: .18s; }
    .ec-msg.typing span:nth-child(3) { animation-delay: .36s; }
    @keyframes ec-bounce {
      0%,80%,100% { transform: translateY(0); }
      40%          { transform: translateY(-5px); }
    }

    #ec-chat-bar {
      display: flex;
      align-items: flex-end;
      gap: 8px;
      padding: 10px 12px;
      border-top: 1px solid var(--ec-border);
      background: var(--ec-bg2);
      flex-shrink: 0;
    }
    #ec-chat-input {
      flex: 1;
      background: var(--ec-bg3);
      border: 1px solid var(--ec-border);
      border-radius: 8px;
      padding: 8px 11px;
      color: var(--ec-text);
      font-family: var(--ec-font);
      font-size: 13px;
      resize: none;
      outline: none;
      max-height: 80px;
      line-height: 1.45;
      transition: border-color .15s;
    }
    #ec-chat-input::placeholder { color: var(--ec-text-dim); }
    #ec-chat-input:focus { border-color: var(--ec-accent); }
    #ec-chat-send {
      width: 34px; height: 34px;
      background: var(--ec-accent);
      border: none;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: background .15s;
    }
    #ec-chat-send:hover { background: var(--ec-accent-h); }
    #ec-chat-send:disabled { background: var(--ec-bg4); cursor: not-allowed; }
    #ec-chat-send svg { width: 15px; height: 15px; fill: white; }

    /* ── Shared button ──────────────────────────── */
    .ec-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 9px 14px;
      border-radius: 8px;
      border: 1px solid transparent;
      cursor: pointer;
      font-family: var(--ec-font);
      font-size: 12px;
      font-weight: 600;
      letter-spacing: .2px;
      transition: background .15s, opacity .15s, transform .1s;
      text-align: center;
    }
    .ec-btn:active { transform: scale(.97); }
    .ec-btn:disabled { opacity: .4; cursor: not-allowed; transform: none; }
    .ec-btn-primary  { background: var(--ec-accent); color: white; }
    .ec-btn-primary:hover:not(:disabled) { background: var(--ec-accent-h); }
    .ec-btn-ghost {
      background: transparent;
      color: var(--ec-text-sub);
      border-color: var(--ec-border);
    }
    .ec-btn-ghost:hover:not(:disabled) { background: var(--ec-bg3); color: var(--ec-text); }

    /* ── Shared form ────────────────────────────── */
    .ec-field { display: flex; flex-direction: column; gap: 5px; }
    .ec-label {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: .6px;
      color: var(--ec-text-dim);
    }
    .ec-input, .ec-select {
      background: var(--ec-bg3);
      border: 1px solid var(--ec-border);
      border-radius: 7px;
      padding: 8px 11px;
      color: var(--ec-text);
      font-family: var(--ec-font);
      font-size: 13px;
      outline: none;
      transition: border-color .15s;
    }
    .ec-input::placeholder { color: var(--ec-text-dim); }
    .ec-input:focus, .ec-select:focus { border-color: var(--ec-accent); }
    .ec-select option { background: var(--ec-bg2); }

    /* ── Index pane ─────────────────────────────── */
    #ec-index-wrap {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      overflow-y: auto;
      flex: 1;
    }
    .ec-pill {
      background: var(--ec-bg2);
      border: 1px solid var(--ec-border);
      border-radius: 8px;
      padding: 10px 13px;
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
    }
    .ec-pill-name {
      flex: 1;
      font-weight: 600;
      color: var(--ec-text);
      font-size: 12px;
      min-width: 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .ec-pill-badge { font-size: 10px; color: var(--ec-text-dim); white-space: nowrap; }
    .ec-progress-track {
      background: var(--ec-bg3);
      border-radius: 4px;
      overflow: hidden;
      height: 4px;
    }
    .ec-progress-bar {
      height: 100%;
      background: var(--ec-accent);
      transition: width .35s ease;
      border-radius: 4px;
    }
    .ec-progress-label { font-size: 11px; color: var(--ec-text-dim); margin-top: 3px; }
    .ec-log {
      background: var(--ec-bg2);
      border: 1px solid var(--ec-border);
      border-radius: 7px;
      padding: 9px 11px;
      font-size: 11px;
      color: var(--ec-text-dim);
      max-height: 120px;
      overflow-y: auto;
      line-height: 1.65;
      font-family: 'Menlo','Consolas',monospace;
      scrollbar-width: thin;
      scrollbar-color: var(--ec-border) transparent;
    }

    /* ── Quiz pane ──────────────────────────────── */
    #ec-quiz-wrap {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      overflow-y: auto;
      flex: 1;
    }
    .ec-row-2 { display: flex; gap: 10px; }
    .ec-row-2 > * { flex: 1; }
    .ec-question {
      background: var(--ec-bg2);
      border: 1px solid var(--ec-border);
      border-radius: 9px;
      padding: 13px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .ec-q-text { color: var(--ec-text); font-weight: 600; font-size: 13px; line-height: 1.45; }
    .ec-option {
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 8px 11px;
      border-radius: 7px;
      border: 1px solid var(--ec-border);
      cursor: pointer;
      transition: background .12s, border-color .12s, color .12s;
      color: var(--ec-text-sub);
      font-size: 12px;
      user-select: none;
    }
    .ec-option:hover { background: var(--ec-bg3); color: var(--ec-text); border-color: var(--ec-bg4); }
    .ec-option.selected { border-color: var(--ec-accent); color: var(--ec-text); background: rgba(99,102,241,.1); }
    .ec-option.correct  { border-color: var(--ec-green); background: rgba(34,197,94,.1); color: var(--ec-green); }
    .ec-option.wrong    { border-color: var(--ec-red); background: rgba(239,68,68,.1); color: var(--ec-red); }
    .ec-opt-letter {
      width: 20px; height: 20px;
      border-radius: 50%;
      background: var(--ec-bg4);
      display: flex; align-items: center; justify-content: center;
      font-size: 10px; font-weight: 700;
      flex-shrink: 0;
      color: var(--ec-text-dim);
    }
    .ec-explanation {
      display: none;
      font-size: 11.5px;
      color: var(--ec-text-sub);
      padding: 8px 10px;
      background: var(--ec-bg);
      border-radius: 6px;
      border-left: 2px solid var(--ec-accent);
      line-height: 1.55;
    }
    .ec-score {
      text-align: center;
      padding: 14px;
      background: var(--ec-bg2);
      border: 1px solid var(--ec-border);
      border-radius: 9px;
    }
    .ec-score-num { font-size: 26px; font-weight: 700; color: var(--ec-accent); }
    .ec-score-sub { font-size: 11px; color: var(--ec-text-dim); margin-top: 3px; }
    .ec-quiz-actions { display: flex; gap: 8px; }
    .ec-quiz-actions > * { flex: 1; }

    /* ── Toast ──────────────────────────────────── */
    #ec-toasts {
      position: fixed;
      bottom: 86px;
      right: 24px;
      z-index: 1000000;
      display: flex;
      flex-direction: column;
      gap: 6px;
      pointer-events: none;
    }
    .ec-toast {
      background: var(--ec-bg2);
      border: 1px solid var(--ec-border);
      color: var(--ec-text);
      padding: 9px 14px;
      border-radius: 8px;
      font-size: 12px;
      box-shadow: var(--ec-shadow);
      animation: ec-fadein .2s ease;
      max-width: 280px;
    }
    .ec-toast.success { border-left: 3px solid var(--ec-green); }
    .ec-toast.error   { border-left: 3px solid var(--ec-red); }
    .ec-toast.info    { border-left: 3px solid var(--ec-accent); }
    @keyframes ec-fadein {
      from { opacity: 0; transform: translateX(12px); }
      to   { opacity: 1; transform: translateX(0); }
    }

    /* ── Scrollbar polish ───────────────────────── */
    #ec-messages::-webkit-scrollbar,
    #ec-quiz-wrap::-webkit-scrollbar,
    #ec-index-wrap::-webkit-scrollbar,
    .ec-log::-webkit-scrollbar { width: 4px; }
    #ec-messages::-webkit-scrollbar-track,
    #ec-quiz-wrap::-webkit-scrollbar-track,
    #ec-index-wrap::-webkit-scrollbar-track,
    .ec-log::-webkit-scrollbar-track { background: transparent; }
    #ec-messages::-webkit-scrollbar-thumb,
    #ec-quiz-wrap::-webkit-scrollbar-thumb,
    #ec-index-wrap::-webkit-scrollbar-thumb,
    .ec-log::-webkit-scrollbar-thumb { background: var(--ec-border); border-radius: 4px; }
  `;
  document.head.appendChild(_style);

  // ── UTILS ─────────────────────────────────────────────────────────────────
  const $ = (sel, ctx = document) => ctx.querySelector(sel);

  function getCourseId() {
    const url = new URL(location.href);
    const id = url.searchParams.get('id');
    if (id && location.pathname.includes('/course/')) return parseInt(id);
    const m = location.pathname.match(/\/course\/(\d+)/);
    if (m) return parseInt(m[1]);
    return null;
  }

  function getCourseName() {
    return document.title.replace(' | Moodle', '').trim() ||
           $('h1.page-header-headings')?.textContent?.trim() ||
           `Course ${getCourseId()}`;
  }

  function toast(msg, type = 'info', duration = 4000) {
    const t = document.createElement('div');
    t.className = `ec-toast ${type}`;
    t.textContent = msg;
    $('#ec-toasts').appendChild(t);
    setTimeout(() => t.remove(), duration);
  }

  function log(msg) {
    const el = $('#ec-log');
    if (!el) return;
    el.textContent += `${msg}\n`;
    el.scrollTop = el.scrollHeight;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatMarkdown(text) {
    const slots = [];
    const slot = (html) => { const i = slots.length; slots.push(html); return `\x00S${i}\x00`; };
    const _katex = typeof katex !== 'undefined' ? katex : null;

    // 1. Extract fenced code blocks before escaping
    text = text.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) =>
      slot(`<pre><code>${escHtml(code.trim())}</code></pre>`)
    );

    // 2. Extract block math $$...$$
    text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => {
      if (!_katex) return slot(`<code>$$${escHtml(math)}$$</code>`);
      try { return slot(_katex.renderToString(math.trim(), { displayMode: true, throwOnError: false })); }
      catch { return slot(`<code>$$${escHtml(math)}$$</code>`); }
    });

    // 3. Extract inline math $...$
    text = text.replace(/\$([^\n$]+?)\$/g, (_, math) => {
      if (!_katex) return slot(`<code>$${escHtml(math)}$</code>`);
      try { return slot(_katex.renderToString(math.trim(), { displayMode: false, throwOnError: false })); }
      catch { return slot(`<code>$${escHtml(math)}$</code>`); }
    });

    // 4. HTML-escape the remaining text
    text = escHtml(text);

    // 5. Apply markdown formatting
    text = text
      .replace(/^### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^## (.+)$/gm, '<h3>$1</h3>')
      .replace(/^# (.+)$/gm, '<h2>$1</h2>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
      .replace(/\n/g, '<br>');

    // 6. Re-insert extracted slots
    text = text.replace(/\x00S(\d+)\x00/g, (_, i) => slots[+i]);

    return text;
  }

  // ── API HELPERS ───────────────────────────────────────────────────────────
  function apiPost(path, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: 'POST',
        url: `${API}${path}`,
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify(body),
        onload: r => {
          try {
            const parsed = JSON.parse(r.responseText);
            if (r.status >= 400) {
              reject(new Error(parsed.detail || `HTTP ${r.status}`));
            } else {
              resolve(parsed);
            }
          } catch {
            reject(new Error(`HTTP ${r.status}: ${r.responseText.slice(0, 200)}`));
          }
        },
        onerror: () => reject(new Error('Network error')),
      });
    });
  }

  function apiGet(path) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: 'GET',
        url: `${API}${path}`,
        onload: r => {
          try { resolve(JSON.parse(r.responseText)); }
          catch { reject(new Error(r.responseText)); }
        },
        onerror: () => reject(new Error('Network error')),
      });
    });
  }

  function apiSSE(path, body, onEvent, onDone) {
    let buffer = '';
    GM_xmlhttpRequest({
      method: 'POST',
      url: `${API}${path}`,
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      data: JSON.stringify(body),
      responseType: 'stream',
      onprogress: r => {
        buffer += r.responseText.slice(buffer.length);
        const lines = buffer.split('\n');
        buffer = lines.pop();
        let eventType = 'progress';
        for (const line of lines) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim();
          if (line.startsWith('data:')) {
            try {
              const data = JSON.parse(line.slice(5).trim());
              onEvent(data, eventType);
              if (eventType === 'done') { onDone && onDone(data); return; }
            } catch {}
          }
        }
      },
      onload: () => { onDone && onDone(null); },
      onerror: () => { onDone && onDone({ error: true }); },
    });
  }

  // ── STATE ─────────────────────────────────────────────────────────────────
  const state = {
    open: false,
    tab: 'chat',
    courseId: getCourseId(),
    courseName: getCourseName(),
    chatHistory: [],
    quizQuestions: [],
    quizAnswers: {},
    quizSubmitted: false,
    indexing: false,
    backendOnline: false,
  };

  // ── BUILD UI ──────────────────────────────────────────────────────────────
  function buildUI() {
    const toastsEl = document.createElement('div');
    toastsEl.id = 'ec-toasts';
    document.body.appendChild(toastsEl);

    const widget = document.createElement('div');
    widget.id = 'ec-widget';
    widget.innerHTML = `
      <div id="ec-panel" class="ec-hidden">

        <div id="ec-header">
          <div id="ec-header-icon">
            <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-3 10H7v-2h10v2zm0-3H7V7h10v2z"/></svg>
          </div>
          <div id="ec-header-info">
            <div id="ec-header-title">Else AI Companion</div>
            <div id="ec-header-sub">${state.courseId ? escHtml(state.courseName) : 'No course detected'}</div>
          </div>
          <div id="ec-status-dot" class="offline" title="Backend status"></div>
        </div>

        <div id="ec-tabs">
          <button class="ec-tab active" data-tab="chat">Chat</button>
          <button class="ec-tab" data-tab="index">Index</button>
          <button class="ec-tab" data-tab="quiz">Quiz</button>
        </div>

        <!-- CHAT PANE -->
        <div class="ec-pane active" id="ec-pane-chat">
          <div id="ec-messages">
            <div class="ec-msg assistant">
              Hey! I'm your AI assistant for this course.<br><br>
              ${state.courseId
                ? `Detected course <strong>ID&nbsp;${state.courseId}</strong>. Index the materials first, then ask me anything.`
                : 'Navigate to a Moodle course page to detect it automatically.'}
            </div>
          </div>
          <div id="ec-chat-bar">
            <textarea id="ec-chat-input" rows="1" placeholder="Ask something about the course\u2026"></textarea>
            <button id="ec-chat-send" title="Send">
              <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2z"/></svg>
            </button>
          </div>
        </div>

        <!-- INDEX PANE -->
        <div class="ec-pane" id="ec-pane-index">
          <div id="ec-index-wrap">
            <div id="ec-index-pill" class="ec-pill" style="display:none">
              <div style="flex:1;min-width:0">
                <div class="ec-pill-name" id="ec-pill-name">\u2014</div>
                <div class="ec-pill-badge" id="ec-pill-badge">Not indexed</div>
              </div>
              <span id="ec-pill-status"></span>
            </div>
            <button class="ec-btn ec-btn-primary" id="ec-btn-index">Index course</button>
            <button class="ec-btn ec-btn-ghost" id="ec-btn-reindex" style="display:none">Re-index everything</button>
            <div id="ec-progress-section" style="display:none">
              <div class="ec-progress-track">
                <div class="ec-progress-bar" id="ec-progress-bar" style="width:0%"></div>
              </div>
              <div class="ec-progress-label" id="ec-progress-label">0%</div>
            </div>
            <div class="ec-log" id="ec-log" style="display:none"></div>
          </div>
        </div>

        <!-- QUIZ PANE -->
        <div class="ec-pane" id="ec-pane-quiz">
          <div id="ec-quiz-wrap">
            <div id="ec-quiz-form">
              <div class="ec-field">
                <label class="ec-label">Topic (optional)</label>
                <input class="ec-input" id="ec-quiz-topic" placeholder="e.g. Operating Systems, Networks\u2026">
              </div>
              <div class="ec-row-2">
                <div class="ec-field">
                  <label class="ec-label">Questions</label>
                  <select class="ec-select" id="ec-quiz-count">
                    <option value="5">5</option>
                    <option value="10" selected>10</option>
                    <option value="15">15</option>
                    <option value="20">20</option>
                  </select>
                </div>
                <div class="ec-field">
                  <label class="ec-label">Difficulty</label>
                  <select class="ec-select" id="ec-quiz-difficulty">
                    <option value="easy">Easy</option>
                    <option value="medium" selected>Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                </div>
              </div>
              <button class="ec-btn ec-btn-primary" id="ec-btn-quiz">Generate Quiz</button>
            </div>
            <div id="ec-quiz-questions" style="display:none"></div>
          </div>
        </div>

      </div>

      <button id="ec-fab" title="Else AI Companion">
        <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-3 10H7v-2h10v2zm0-3H7V7h10v2z"/></svg>
      </button>
    `;
    document.body.appendChild(widget);
  }

  // ── EVENTS ────────────────────────────────────────────────────────────────
  function setupEvents() {
    $('#ec-fab').addEventListener('click', () => {
      state.open = !state.open;
      $('#ec-panel').classList.toggle('ec-hidden', !state.open);
      if (state.open) checkBackend();
    });

    document.querySelectorAll('.ec-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        state.tab = tab;
        document.querySelectorAll('.ec-tab').forEach(b => b.classList.toggle('active', b === btn));
        document.querySelectorAll('.ec-pane').forEach(p =>
          p.classList.toggle('active', p.id === `ec-pane-${tab}`)
        );
        if (tab === 'index') refreshIndexTab();
      });
    });

    $('#ec-chat-send').addEventListener('click', sendChat);
    $('#ec-chat-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    $('#ec-chat-input').addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    $('#ec-btn-index').addEventListener('click', () => startIndex(false));
    $('#ec-btn-reindex').addEventListener('click', () => startIndex(true));
    $('#ec-btn-quiz').addEventListener('click', generateQuiz);
  }

  // ── BACKEND STATUS ────────────────────────────────────────────────────────
  async function checkBackend() {
    try {
      const h = await apiGet('/api/health');
      state.backendOnline = h.status === 'ok' || h.status === 'degraded';
      const dot = $('#ec-status-dot');
      dot.classList.toggle('offline', !h.ollama_connected);
      dot.title = h.ollama_connected ? `Online \u2014 ${h.ollama_model}` : 'Ollama offline';
    } catch {
      state.backendOnline = false;
      $('#ec-status-dot').classList.add('offline');
      $('#ec-status-dot').title = 'Backend offline';
    }
  }

  // ── CHAT ──────────────────────────────────────────────────────────────────
  function addMessage(role, html, sources = []) {
    const el = document.createElement('div');
    el.className = `ec-msg ${role}`;
    if (role === 'assistant' && sources.length) {
      const srcHtml = sources.map(s =>
        `<span>\uD83D\uDCC4 ${escHtml(s.module_name)} \u2014 ${escHtml(s.section)}</span>`
      ).join('');
      el.innerHTML = `${html}<div class="ec-sources">${srcHtml}</div>`;
    } else {
      el.innerHTML = html;
    }
    $('#ec-messages').appendChild(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return el;
  }

  function addTyping() {
    const el = document.createElement('div');
    el.className = 'ec-msg assistant typing';
    el.innerHTML = '<span></span><span></span><span></span>';
    $('#ec-messages').appendChild(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    return el;
  }

  async function sendChat() {
    const input = $('#ec-chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    if (!state.courseId) { toast('Navigate to a course page first', 'error'); return; }

    input.value = '';
    input.style.height = 'auto';
    addMessage('user', escHtml(msg));

    const btn = $('#ec-chat-send');
    btn.disabled = true;
    const typing = addTyping();
    state.chatHistory.push({ role: 'user', content: msg });

    try {
      const res = await apiPost('/api/chat', {
        course_id: state.courseId,
        message: msg,
        history: state.chatHistory.slice(-10),
      });
      typing.remove();
      const answer = res.answer || res.detail || 'Unknown error';
      addMessage('assistant', formatMarkdown(answer), res.sources || []);
      state.chatHistory.push({ role: 'assistant', content: answer });
    } catch (e) {
      typing.remove();
      addMessage('assistant', `Error: ${escHtml(e.message)}`);
    } finally {
      btn.disabled = false;
    }
  }

  // ── INDEX ─────────────────────────────────────────────────────────────────
  async function refreshIndexTab() {
    if (!state.courseId) return;
    const pillEl = $('#ec-index-pill');
    $('#ec-pill-name').textContent = `${state.courseName} (ID: ${state.courseId})`;
    pillEl.style.display = 'flex';

    try {
      const res = await apiGet(`/api/index/status/${state.courseId}`);
      if (res.status === 'done') {
        $('#ec-pill-badge').textContent = 'Indexed';
        $('#ec-pill-status').textContent = '\u2713';
        $('#ec-btn-reindex').style.display = 'flex';
      } else {
        $('#ec-pill-badge').textContent = 'Not indexed';
        $('#ec-pill-status').textContent = '';
      }
    } catch {}
  }

  function startIndex(forceReindex) {
    if (!state.courseId) { toast('No course detected on this page', 'error'); return; }
    if (state.indexing) return;

    state.indexing = true;
    $('#ec-btn-index').disabled = true;
    $('#ec-btn-reindex').disabled = true;
    $('#ec-progress-section').style.display = 'block';
    $('#ec-log').style.display = 'block';
    $('#ec-log').textContent = '';

    log(`Indexing course ${state.courseId}\u2026`);

    apiSSE(
      '/api/index',
      { course_id: state.courseId, force_reindex: forceReindex },
      (data) => {
        if (data.progress !== undefined) {
          $('#ec-progress-bar').style.width = data.progress + '%';
          $('#ec-progress-label').textContent = `${Math.round(data.progress)}% \u2014 ${data.message}`;
          log(data.message);
        }
      },
      (finalData) => {
        state.indexing = false;
        $('#ec-btn-index').disabled = false;
        $('#ec-btn-reindex').disabled = false;

        if (finalData?.status === 'done') {
          toast('Indexing complete', 'success');
          log('Done.');
          refreshIndexTab();
        } else if (finalData?.status === 'error') {
          toast(`Error: ${finalData.message}`, 'error');
        } else {
          toast('Indexing finished', 'info');
        }
      }
    );
  }

  // ── QUIZ ──────────────────────────────────────────────────────────────────
  async function generateQuiz() {
    if (!state.courseId) { toast('No course detected', 'error'); return; }

    const btn = $('#ec-btn-quiz');
    btn.disabled = true;
    btn.textContent = 'Generating\u2026';

    state.quizQuestions = [];
    state.quizAnswers = {};
    state.quizSubmitted = false;

    try {
      const res = await apiPost('/api/quiz/generate', {
        course_id: state.courseId,
        topic: $('#ec-quiz-topic').value.trim() || null,
        num_questions: parseInt($('#ec-quiz-count').value),
        difficulty: $('#ec-quiz-difficulty').value,
      });

      state.quizQuestions = res.questions || [];
      if (!state.quizQuestions.length) throw new Error('No questions generated');

      renderQuiz();
      toast(`Quiz ready: ${state.quizQuestions.length} questions`, 'success');
    } catch (e) {
      toast(`Error: ${e.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generate Quiz';
    }
  }

  function renderQuiz() {
    const container = $('#ec-quiz-questions');
    container.innerHTML = '';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.gap = '14px';
    $('#ec-quiz-form').style.display = 'none';

    const LETTERS = ['A', 'B', 'C', 'D'];

    state.quizQuestions.forEach((q, qi) => {
      const qEl = document.createElement('div');
      qEl.className = 'ec-question';
      qEl.innerHTML = `
        <div class="ec-q-text">${qi + 1}. ${escHtml(q.question)}</div>
        ${q.options.map((opt, oi) => `
          <div class="ec-option" data-qi="${qi}" data-oi="${oi}">
            <div class="ec-opt-letter">${LETTERS[oi]}</div>
            <span>${escHtml(opt)}</span>
          </div>
        `).join('')}
        <div class="ec-explanation">${escHtml(q.explanation || '')}</div>
      `;
      container.appendChild(qEl);
    });

    const actions = document.createElement('div');
    actions.className = 'ec-quiz-actions';
    actions.innerHTML = `
      <button class="ec-btn ec-btn-primary" id="ec-quiz-submit">Check answers</button>
      <button class="ec-btn ec-btn-ghost" id="ec-quiz-reset">New quiz</button>
    `;
    container.appendChild(actions);

    container.addEventListener('click', e => {
      const opt = e.target.closest('.ec-option');
      if (!opt || state.quizSubmitted) return;
      const qi = parseInt(opt.dataset.qi);
      const oi = parseInt(opt.dataset.oi);
      container.querySelectorAll(`.ec-option[data-qi="${qi}"]`).forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
      state.quizAnswers[qi] = oi;
    });

    $('#ec-quiz-submit').addEventListener('click', submitQuiz);
    $('#ec-quiz-reset').addEventListener('click', resetQuiz);
  }

  function submitQuiz() {
    if (state.quizSubmitted) return;
    state.quizSubmitted = true;

    let correct = 0;
    state.quizQuestions.forEach((q, qi) => {
      const userAns = state.quizAnswers[qi];
      const correctAns = q.correct_index;

      document.querySelectorAll(`.ec-option[data-qi="${qi}"]`).forEach(opt => {
        const oi = parseInt(opt.dataset.oi);
        if (oi === correctAns) opt.classList.add('correct');
        else if (oi === userAns && oi !== correctAns) opt.classList.add('wrong');
      });

      const qEl = document.querySelectorAll('.ec-question')[qi];
      const expEl = qEl?.querySelector('.ec-explanation');
      if (expEl && q.explanation) expEl.style.display = 'block';

      if (userAns === correctAns) correct++;
    });

    const total = state.quizQuestions.length;
    const pct = Math.round((correct / total) * 100);

    const scoreEl = document.createElement('div');
    scoreEl.className = 'ec-score';
    scoreEl.innerHTML = `
      <div class="ec-score-num">${correct} / ${total}</div>
      <div class="ec-score-sub">${pct}% correct</div>
    `;
    $('#ec-quiz-questions').prepend(scoreEl);

    toast(`Score: ${correct}/${total} (${pct}%)`, pct >= 70 ? 'success' : 'info');
    $('#ec-quiz-submit').disabled = true;
  }

  function resetQuiz() {
    state.quizQuestions = [];
    state.quizAnswers = {};
    state.quizSubmitted = false;

    const container = $('#ec-quiz-questions');
    container.innerHTML = '';
    container.style.display = 'none';
    container.style.flexDirection = '';
    container.style.gap = '';

    // Show form as block (not flex) to avoid children laid out horizontally
    $('#ec-quiz-form').style.display = 'block';
  }

  // ── INIT ──────────────────────────────────────────────────────────────────
  buildUI();
  setupEvents();
  setInterval(checkBackend, 30000);

})();
