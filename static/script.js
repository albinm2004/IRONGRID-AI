/* ═══════════════════════════════════════════════════════════
   IRONGRID AI — Chat Logic
   Handles messaging, API calls, UI rendering, and animations
   ═══════════════════════════════════════════════════════════ */

// ── DOM Elements ───────────────────────────────────────────
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const statusBadge = document.getElementById('statusBadge');

// ── State ──────────────────────────────────────────────────
let sessionId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
let isProcessing = false;

// ── Open / Closed Status ───────────────────────────────────
function updateStatus() {
  const now = new Date();
  const day = now.getDay(); // 0 = Sunday
  const hour = now.getHours() + now.getMinutes() / 60;
  let isOpen;

  if (day === 0) {
    isOpen = hour >= 6 && hour < 21;
  } else {
    isOpen = hour >= 5 && hour < 23;
  }

  statusBadge.className = 'status-badge ' + (isOpen ? 'open' : 'closed');
  statusBadge.innerHTML = '<span class="status-dot"></span>' + (isOpen ? 'OPEN NOW' : 'CLOSED NOW');
}

updateStatus();
setInterval(updateStatus, 60000); // Update every minute

// ── Time Greeting ──────────────────────────────────────────
function getTimeGreeting() {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) return 'Good morning';
  if (hour >= 12 && hour < 17) return 'Good afternoon';
  if (hour >= 17 && hour < 21) return 'Good evening';
  return 'Hey there';
}

// ── Escape HTML ────────────────────────────────────────────
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Markdown-ish Renderer ──────────────────────────────────
function renderContent(text) {
  const lines = text.split('\n');
  let html = '';
  let inList = false;
  let listType = null; // 'ul' or 'ol'

  for (const raw of lines) {
    const line = raw.trim();
    if (line === '') {
      if (inList) { html += `</${listType}>`; inList = false; listType = null; }
      continue;
    }

    // Bullet list
    const bulletMatch = line.match(/^[-•*]\s+(.*)/);
    if (bulletMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) html += `</${listType}>`;
        html += '<ul>';
        inList = true;
        listType = 'ul';
      }
      html += '<li>' + inlineFormat(bulletMatch[1]) + '</li>';
      continue;
    }

    // Numbered list
    const numMatch = line.match(/^\d+[\.\)]\s+(.*)/);
    if (numMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) html += `</${listType}>`;
        html += '<ol>';
        inList = true;
        listType = 'ol';
      }
      html += '<li>' + inlineFormat(numMatch[1]) + '</li>';
      continue;
    }

    // Regular paragraph
    if (inList) { html += `</${listType}>`; inList = false; listType = null; }
    html += '<p>' + inlineFormat(line) + '</p>';
  }

  if (inList) html += `</${listType}>`;
  return html;
}

function inlineFormat(str) {
  let s = escapeHtml(str);
  // Bold **text**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic *text* (but not inside bold)
  s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
  // Inline code `text`
  s = s.replace(/`(.+?)`/g, '<code>$1</code>');
  // ₹ symbol highlighting
  s = s.replace(/(₹[\d,]+)/g, '<strong>$1</strong>');
  return s;
}

// ── Timestamp ──────────────────────────────────────────────
function formatTime() {
  const now = new Date();
  return now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
}

// ── Add Message ────────────────────────────────────────────
function addMessage(role, text, meta = {}) {
  const row = document.createElement('div');
  row.className = 'row ' + (role === 'user' ? 'user' : 'bot');

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = role === 'user' ? 'U' : 'IG';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = renderContent(text);

  // Confidence badge (bot only)
  if (role === 'bot' && meta.confidence_level) {
    const badge = document.createElement('div');
    badge.className = 'confidence-badge ' + meta.confidence_level;
    badge.innerHTML = `<span class="confidence-dot"></span>${meta.confidence_level} confidence`;
    bubble.appendChild(badge);
  }

  // Source tags (bot only)
  if (role === 'bot' && meta.sources && meta.sources.length > 0) {
    const tags = document.createElement('div');
    tags.className = 'source-tags';
    meta.sources.forEach(src => {
      const tag = document.createElement('span');
      tag.className = 'source-tag';
      tag.textContent = src.subcategory || src.category;
      tags.appendChild(tag);
    });
    bubble.appendChild(tags);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);

  // Timestamp
  const timeEl = document.createElement('div');
  timeEl.className = 'msg-time';
  timeEl.textContent = formatTime();
  messagesEl.appendChild(timeEl);

  scrollToBottom();
  return bubble;
}

// ── Follow-up Suggestions ──────────────────────────────────
function addFollowUps(suggestions) {
  if (!suggestions || suggestions.length === 0) return;

  // Remove existing follow-ups
  removeFollowUps();

  const container = document.createElement('div');
  container.className = 'follow-ups';
  container.id = 'followUps';

  suggestions.forEach(text => {
    const btn = document.createElement('button');
    btn.className = 'follow-up-btn';
    btn.textContent = text;
    btn.addEventListener('click', () => {
      removeFollowUps();
      sendMessage(text);
    });
    container.appendChild(btn);
  });

  messagesEl.appendChild(container);
  scrollToBottom();
}

function removeFollowUps() {
  const existing = document.getElementById('followUps');
  if (existing) existing.remove();
}

// ── Typing Indicator ───────────────────────────────────────
function addTyping() {
  const row = document.createElement('div');
  row.className = 'row bot';
  row.id = 'typingRow';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = 'IG';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const typing = document.createElement('div');
  typing.className = 'typing-indicator';
  typing.innerHTML = '<span></span><span></span><span></span>';

  bubble.appendChild(typing);
  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollToBottom();
}

function removeTyping() {
  const row = document.getElementById('typingRow');
  if (row) row.remove();
}

// ── Scroll ─────────────────────────────────────────────────
function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

// ── Send Message (API Call) ────────────────────────────────
async function sendMessage(text) {
  text = text.trim();
  if (!text || isProcessing) return;

  isProcessing = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  removeFollowUps();

  addMessage('user', text);
  addTyping();

  const startTime = Date.now();

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
      }),
    });

    // Ensure minimum typing animation time (400ms)
    const elapsed = Date.now() - startTime;
    if (elapsed < 400) {
      await new Promise(r => setTimeout(r, 400 - elapsed));
    }

    removeTyping();

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `Server error (${response.status})`);
    }

    const data = await response.json();

    // Render bot message with metadata
    addMessage('bot', data.answer || "I couldn't process that. Please try again.", {
      confidence_level: data.confidence_level,
      sources: data.sources,
    });

    // Add follow-up suggestions
    if (data.follow_ups && data.follow_ups.length > 0) {
      addFollowUps(data.follow_ups);
    }

    // Update session ID if returned
    if (data.session_id) {
      sessionId = data.session_id;
    }

  } catch (err) {
    removeTyping();
    console.error('Chat error:', err);
    addMessage('bot', "I'm having trouble connecting right now. Please make sure the server is running and try again.");
  } finally {
    isProcessing = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// ── Event Listeners ────────────────────────────────────────
sendBtn.addEventListener('click', () => sendMessage(inputEl.value));

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});

// Quick chips
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    sendMessage(chip.dataset.msg);
  });
});

// ── Initial Greeting ───────────────────────────────────────
async function init() {
  try {
    const response = await fetch('/api/greeting');
    if (response.ok) {
      const data = await response.json();
      if (data && data.message) {
        addMessage('bot', data.message);
        if (data.is_open !== undefined) {
          statusBadge.className = 'status-badge ' + (data.is_open ? 'open' : 'closed');
          statusBadge.innerHTML = '<span class="status-dot"></span>' + (data.is_open ? 'OPEN NOW' : 'CLOSED NOW');
        }
        return;
      }
    }
  } catch (err) {
    console.warn('Could not load greeting from API, using client fallback:', err);
  }

  // Fallback if backend greeting fails
  const greeting = getTimeGreeting();
  addMessage(
    'bot',
    `${greeting}! Welcome to **IRONGRID**. I'm your virtual front desk assistant.\n\nAsk me about **membership plans**, **equipment**, **timings**, **trainers**, **classes**, **safety**, or anything about the gym — or tap a quick option above!`
  );
}
init();
