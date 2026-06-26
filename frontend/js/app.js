/* ═══════════════════════════════════════════════════════════════
   灵兰 · App — 登录、注册、聊天、会话管理
   ═══════════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────
let currentSessionId = null;
let sessions = [];

// ── Init ──────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (api.getToken()) {
    showApp();
    loadSessions();
  }
});

// ═══════════════════════════════════════════════════════════════
// Auth
// ═══════════════════════════════════════════════════════════════
function setupAuth() {
  const tabLogin = document.getElementById('tabLogin');
  const tabRegister = document.getElementById('tabRegister');
  const formLogin = document.getElementById('formLogin');
  const formRegister = document.getElementById('formRegister');
  const errEl = document.getElementById('authError');

  tabLogin.addEventListener('click', () => {
    tabLogin.classList.add('active'); tabRegister.classList.remove('active');
    formLogin.classList.remove('hidden'); formRegister.classList.add('hidden');
    errEl.textContent = '';
  });
  tabRegister.addEventListener('click', () => {
    tabRegister.classList.add('active'); tabLogin.classList.remove('active');
    formRegister.classList.remove('hidden'); formLogin.classList.add('hidden');
    errEl.textContent = '';
  });

  document.getElementById('btnLogin').addEventListener('click', async () => {
    const phone = document.getElementById('loginPhone').value.trim();
    const pw = document.getElementById('loginPw').value;
    errEl.textContent = '';
    if (!phone || !pw) { errEl.textContent = '请填写手机号和密码'; return; }
    try {
      const res = await api.login(phone, pw);
      api.setToken(res.access_token);
      showApp(); loadSessions();
    } catch (e) { errEl.textContent = e.detail || '手机号或密码错误'; }
  });

  document.getElementById('btnRegister').addEventListener('click', async () => {
    const phone = document.getElementById('regPhone').value.trim();
    const pw = document.getElementById('regPw').value;
    const nick = document.getElementById('regNick').value.trim();
    errEl.textContent = '';
    if (!phone || !pw || !nick) { errEl.textContent = '请填写所有字段'; return; }
    try {
      const res = await api.register(phone, pw, nick);
      api.setToken(res.access_token);
      showApp(); loadSessions();
    } catch (e) { errEl.textContent = e.detail || '注册失败，请重试'; }
  });
}
setupAuth();

function showApp() {
  document.getElementById('authPage').classList.add('hidden');
  document.getElementById('appPage').classList.remove('hidden');
  loadProfile();
}

// ═══════════════════════════════════════════════════════════════
// Sessions
// ═══════════════════════════════════════════════════════════════
async function loadSessions() {
  try {
    const res = await api.listSessions();
    sessions = res.data || [];
    renderSessions();
  } catch (e) { console.error('loadSessions:', e); }
}

function renderSessions() {
  const el = document.getElementById('sessionList');
  el.innerHTML = sessions.map(s => `
    <div class="sidebar-session${s.session_id === currentSessionId ? ' active' : ''}" data-sid="${s.session_id}">
      <span class="indicator"></span>
      <div class="info">
        <div class="title">${s.scenario || '健康咨询'}</div>
        <div class="meta">${fmtDate(s.updated_at)} · 第${s.round_count || 0}轮</div>
      </div>
      <button class="btn-del" data-del="${s.session_id}" title="删除">×</button>
    </div>
  `).join('');

  // Click: select session
  el.querySelectorAll('.sidebar-session').forEach(div => {
    div.addEventListener('click', e => {
      if (e.target.classList.contains('btn-del')) return;
      selectSession(div.dataset.sid);
    });
  });
  // Delete button
  el.querySelectorAll('.btn-del').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      await api.deleteSession(btn.dataset.del);
      if (currentSessionId === btn.dataset.del) { currentSessionId = null; clearChat(); }
      await loadSessions();
    });
  });
}

async function selectSession(sid) {
  currentSessionId = sid;
  renderSessions();
  clearChat();
  try {
    const res = await api.listMessages(sid);
    renderMessages(res.data || []);
  } catch (e) { console.error('loadMessages:', e); }
  updateStageUI();
}

document.getElementById('btnNewSession').addEventListener('click', async () => {
  try {
    const res = await api.createSession();
    currentSessionId = res.id;
    await loadSessions();
    clearChat();
    updateStageUI();
  } catch (e) { console.error('createSession:', e); }
});

// ═══════════════════════════════════════════════════════════════
// Chat
// ═══════════════════════════════════════════════════════════════
const chatEl = document.getElementById('chatMessages');
const inputEl = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const stageEl = document.getElementById('stageBadge');
const expertEl = document.getElementById('expertBadge');
const roundEl = document.getElementById('roundInfo');

function clearChat() { chatEl.innerHTML = ''; inputEl.disabled = false; sendBtn.disabled = false; inputEl.placeholder = '描述您的症状...'; }
function scrollChat() { chatEl.scrollTop = chatEl.scrollHeight; }

function updateStageUI() {
  stageEl.style.display = 'none'; expertEl.style.display = 'none';
  stageEl.classList.remove('expert');
  // Will be updated based on API response
}

function renderMessages(msgs) {
  chatEl.innerHTML = '';
  msgs.forEach(m => {
    const isReport = m.role === 'assistant' && (!m.options || m.options.length === 0) && m.content && m.content.length > 150;
    appendMessage(m.role, m.content, m.options, isReport);
  });
  scrollChat();
}

function appendMessage(role, content, options, isReport = false) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const avatar = document.createElement('div');
  avatar.className = 'avatar-icon';
  avatar.textContent = role === 'assistant' ? 'AI' : '我';
  div.appendChild(avatar);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (content) {
    if (isReport && content.length > 80) {
      // 诊断报告：解析章节，结构化渲染
      const reportDiv = document.createElement('div');
      reportDiv.className = 'report-card';
      reportDiv.innerHTML = parseReport(content);
      bubble.appendChild(reportDiv);
    } else {
      const p = document.createElement('p');
      p.textContent = content;
      bubble.appendChild(p);
    }
  }
  if (options && options.length > 0) {
    const cd = document.createElement('div'); cd.className = 'choices';
    const letters = 'ABCDEFGH';
    options.slice(0, 4).forEach((opt, i) => {
      const card = document.createElement('button'); card.className = 'choice-card';
      card.innerHTML = `<span class="choice-letter">${letters[i]}</span> ${opt.label}`;
      card.addEventListener('click', () => {
        cd.querySelectorAll('.choice-card').forEach(c => { c.style.pointerEvents = 'none'; c.style.opacity = '0.5'; });
        card.classList.add('selected');
        sendChoice(opt.value, opt.label);
      });
      cd.appendChild(card);
    });
    const hint = document.createElement('p'); hint.className = 'choice-hint';
    hint.textContent = '也可以直接在下方输入框描述您的情况';
    cd.appendChild(hint);
    bubble.appendChild(cd);
  }
  div.appendChild(bubble);
  chatEl.appendChild(div);
  scrollChat();
}

async function sendChoice(value, label) {
  if (!currentSessionId) return;
  appendMessage('user', label);
  try {
    const res = await api.sendMessage(currentSessionId, label);
    handleResponse(res);
  } catch (e) { console.error('sendChoice:', e); }
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || !currentSessionId) return;
  inputEl.value = ''; sendBtn.disabled = true;
  appendMessage('user', text);
  try {
    const res = await api.sendMessage(currentSessionId, text);
    handleResponse(res);
  } catch (e) { console.error('sendMessage:', e); }
  sendBtn.disabled = false; inputEl.focus();
}

function handleResponse(res) {
  // 诊断报告检测：next_action 标记 或 长文本无选项
  const isReport = res.next_action === 'diagnosis_ready'
    || res.current_stage === 'diagnose'
    || (res.response_content && res.response_content.length > 200 && (!res.options || res.options.length === 0));
  if (res.response_content) {
    appendMessage('assistant', res.response_content, res.options, isReport);
  }
  if (res.red_flag_raised) {
    stageEl.style.display = 'inline'; stageEl.textContent = '紧急';
    stageEl.style.background = 'var(--mauve-ghost)'; stageEl.style.color = 'var(--mauve)';
  } else if (isReport) {
    stageEl.style.display = 'inline'; stageEl.textContent = '诊断报告';
  } else if (res.current_stage === 'collect') {
    // Try to detect expert stage
    stageEl.style.display = 'inline'; stageEl.textContent = '问诊中';
  }
  if (res.round_count) roundEl.textContent = `第 ${res.round_count} / 10 轮`;

  // If diagnosis result in collected fields
  if (res.next_action === 'diagnosis_ready' || res.current_stage === 'diagnose') {
    inputEl.disabled = true; inputEl.placeholder = '诊断已完成，可新建会话继续';
    sendBtn.disabled = true;
  }
  loadSessions(); // refresh sidebar
}

sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', e => { if (e.key === 'Enter') sendMessage(); });

// ═══════════════════════════════════════════════════════════════
// Profile
// ═══════════════════════════════════════════════════════════════
async function loadProfile() {
  try {
    const p = await api.getProfile();
    document.getElementById('sidebarName').textContent = p.nickname || '用户';
    document.getElementById('sidebarPhone').textContent = p.phone.replace(/(\d{3})\d{4}(\d{4})/, '$1****$2');
    document.getElementById('sidebarAvatar').textContent = (p.nickname || '用')[0];
  } catch (e) { console.error('loadProfile:', e); }
}

document.getElementById('sidebarAvatar').addEventListener('click', () => {
  document.getElementById('profileModal').classList.remove('hidden');
  loadProfileForm();
});

document.getElementById('btnProfileSave').addEventListener('click', async () => {
  const data = {};
  const set = (k, v) => { if (v) data[k] = v; };
  set('nickname', document.getElementById('pfNick').value.trim());
  set('gender', document.getElementById('pfGender').value);
  set('height', parseFloat(document.getElementById('pfHeight').value) || undefined);
  set('weight', parseFloat(document.getElementById('pfWeight').value) || undefined);
  set('blood_type', document.getElementById('pfBlood').value);
  const allergies = document.getElementById('pfAllergies').value.trim();
  if (allergies) data.allergies = allergies.split(/[,，]/).map(s => s.trim());
  const chronic = document.getElementById('pfChronic').value.trim();
  if (chronic) data.chronic_diseases = chronic.split(/[,，]/).map(s => s.trim());
  try {
    await api.updateProfile(data);
    document.getElementById('profileModal').classList.add('hidden');
    loadProfile();
  } catch (e) { console.error('updateProfile:', e); }
});

document.getElementById('btnProfileCancel').addEventListener('click', () => {
  document.getElementById('profileModal').classList.add('hidden');
});

async function loadProfileForm() {
  try {
    const p = await api.getProfile();
    document.getElementById('pfNick').value = p.nickname || '';
    document.getElementById('pfGender').value = p.gender || '';
    document.getElementById('pfHeight').value = p.height || '';
    document.getElementById('pfWeight').value = p.weight || '';
    document.getElementById('pfBlood').value = p.blood_type || '';
    const mi = p.medical_info || {};
    document.getElementById('pfAllergies').value = (mi.allergies || []).join('，');
    document.getElementById('pfChronic').value = (mi.chronic_diseases || []).join('，');
  } catch (e) { console.error('loadProfileForm:', e); }
}

// ═══════════════════════════════════════════════════════════════
// Utils
// ═══════════════════════════════════════════════════════════════
function parseReport(text) {
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  // 按双换行分段
  const paras = text.split(/\n\n+/).filter(p => p.trim());
  if (paras.length <= 1) {
    return '<div class="report-title">诊断报告</div><p>' + esc(text).replace(/\n/g, '<br>') + '</p>';
  }
  let html = '<div class="report-title">诊断报告</div>';
  paras.forEach(p => {
    const trimmed = p.trim();
    // 检测免责声明段落
    if (/免责声明|不能替代|仅供参考|及时就医/.test(trimmed)) {
      html += '<div class="disclaimer">' + String.fromCharCode(0x2695) + '&nbsp;'
           + esc(trimmed).replace(/\n/g, '<br>') + '</div>';
    } else {
      html += '<p>' + esc(trimmed).replace(/\n/g, '<br>') + '</p>';
    }
  });
  return html;
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return `今天 ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
  return `${d.getMonth()+1}月${d.getDate()}日`;
}
