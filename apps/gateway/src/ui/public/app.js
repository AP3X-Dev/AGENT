/**
 * AG3NT Control Panel - Frontend Application
 */

const API_BASE = '/api';
const WS_URL = `ws://${location.host}/ws?debug=true`;

let ws = null;
let sessionId = `panel:${Date.now()}`;

// =============================================================================
// Toast Notification System
// =============================================================================

const toastContainer = document.getElementById('toast-container');

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - Toast type: 'info', 'success', 'warning', 'error'
 * @param {Object} options - Additional options
 * @param {string} options.title - Optional title
 * @param {number} options.timeout - Auto-dismiss timeout in ms (0 = no auto-dismiss)
 * @returns {HTMLElement} The toast element
 */
function showToast(message, type = 'info', options = {}) {
  const icons = {
    info: 'ℹ️',
    success: '✓',
    warning: '⚠️',
    error: '✗'
  };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  toast.innerHTML = `
    <div class="toast-header">
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span class="toast-title">${options.title || type.charAt(0).toUpperCase() + type.slice(1)}</span>
      <button class="toast-close" onclick="dismissToast(this.closest('.toast'))">×</button>
    </div>
    <div class="toast-body">${message}</div>
  `;

  toastContainer.appendChild(toast);

  if (options.timeout) {
    setTimeout(() => dismissToast(toast), options.timeout);
  }

  return toast;
}

/**
 * Dismiss a toast notification
 * @param {HTMLElement} toast - The toast element to dismiss
 */
function dismissToast(toast) {
  if (!toast || toast.classList.contains('removing')) return;

  toast.classList.add('removing');
  setTimeout(() => {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 300); // Match animation duration
}

/**
 * Show an approval request toast
 * @param {string} sessionId - The session ID needing approval
 * @param {string} pairingCode - The pairing code to display
 * @param {string} channelType - The channel type (cli, panel, etc)
 * @param {string} userName - The user name if available
 */
function showApprovalToast(sessionId, pairingCode, channelType = 'unknown', userName = '') {
  const toast = document.createElement('div');
  toast.className = 'toast toast-approval';
  toast.dataset.sessionId = sessionId;

  const userInfo = userName ? ` from <strong>${userName}</strong>` : '';
  const channelInfo = channelType ? ` (${channelType})` : '';

  toast.innerHTML = `
    <div class="toast-header">
      <span class="toast-icon">🔒</span>
      <span class="toast-title">Session Approval Required</span>
      <button class="toast-close" onclick="dismissToast(this.closest('.toast'))">×</button>
    </div>
    <div class="toast-body">
      A new session${userInfo}${channelInfo} is requesting access.<br>
      Pairing code: <span class="toast-code">${pairingCode}</span>
    </div>
    <div class="toast-actions">
      <button class="toast-btn toast-btn-deny" onclick="handleToastDeny('${sessionId}', this)">Deny</button>
      <button class="toast-btn toast-btn-approve" onclick="handleToastApprove('${sessionId}', this)">Approve</button>
    </div>
  `;

  toastContainer.appendChild(toast);
  return toast;
}

/**
 * Handle approval from toast
 */
async function handleToastApprove(sid, button) {
  const toast = button.closest('.toast');
  button.disabled = true;
  button.textContent = 'Approving...';

  const encodedId = encodeURIComponent(sid);

  try {
    const result = await api(`/sessions/${encodedId}/approve`, { method: 'POST', body: {} });
    if (result.ok) {
      showToast('Session approved! You can now chat.', 'success', { title: 'Approved', timeout: 3000 });
      dismissToast(toast);
      loadSessions(); // Refresh sessions list
      addLog({ level: 'info', source: 'Sessions', message: `Session approved: ${sid}`, timestamp: new Date() });
    } else {
      showToast(`Failed to approve: ${result.error}`, 'error', { title: 'Error' });
      button.disabled = false;
      button.textContent = 'Approve';
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error', { title: 'Error' });
    button.disabled = false;
    button.textContent = 'Approve';
  }
}

/**
 * Handle denial from toast
 */
async function handleToastDeny(sid, button) {
  const toast = button.closest('.toast');
  button.disabled = true;
  button.textContent = 'Denying...';

  const encodedId = encodeURIComponent(sid);

  try {
    // Delete the session to deny it
    const result = await api(`/sessions/${encodedId}`, { method: 'DELETE' });
    if (result.ok) {
      showToast('Session denied and removed.', 'warning', { title: 'Denied', timeout: 3000 });
      dismissToast(toast);
      loadSessions();
      addLog({ level: 'info', source: 'Sessions', message: `Session denied: ${sid}`, timestamp: new Date() });
    } else {
      showToast(`Failed to deny: ${result.error}`, 'error', { title: 'Error' });
      button.disabled = false;
      button.textContent = 'Deny';
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error', { title: 'Error' });
    button.disabled = false;
    button.textContent = 'Deny';
  }
}

// Track sessions that have shown toasts to avoid duplicates
const shownApprovalToasts = new Set();

/**
 * Check for pending sessions and show approval toasts
 */
async function checkPendingApprovals() {
  try {
    const { ok, sessions } = await api('/sessions');
    if (ok && sessions) {
      for (const s of sessions) {
        // Check if session is pending (not paired) and has a pairing code
        if (!s.paired && s.pairingCode && !shownApprovalToasts.has(s.id)) {
          shownApprovalToasts.add(s.id);
          showApprovalToast(s.id, s.pairingCode, s.channelType || 'unknown', s.userName || '');
        }
      }
      // Clean up old entries that are no longer in sessions
      const currentIds = new Set(sessions.map(s => s.id));
      for (const id of shownApprovalToasts) {
        const session = sessions.find(s => s.id === id);
        // Remove from tracking if session no longer exists or is now paired
        if (!currentIds.has(id) || (session && session.paired)) {
          shownApprovalToasts.delete(id);
        }
      }
    }
  } catch (err) {
    // Silently ignore polling errors
  }
}

// Poll for pending approvals every 5 seconds
setInterval(checkPendingApprovals, 5000);

// Check once on page load
setTimeout(checkPendingApprovals, 1000);

// DOM Elements
const statusDot = document.querySelector('.status-dot');
const statusText = document.querySelector('.status-text');
const logsContainer = document.getElementById('logs-container');
const autoScroll = document.getElementById('auto-scroll');

// Tab Navigation
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');

    // Refresh data when switching to certain tabs
    if (btn.dataset.tab === 'sessions') {
      loadSessions();
    } else if (btn.dataset.tab === 'nodes') {
      loadNodes();
      loadApprovedNodes();
      loadPairingCode();
    } else if (btn.dataset.tab === 'subagents') {
      loadSubagents();
    }
  });
});

// Sessions polling - refresh every 5 seconds when on sessions tab
setInterval(() => {
  const sessionsTab = document.querySelector('.nav-btn[data-tab="sessions"]');
  if (sessionsTab && sessionsTab.classList.contains('active')) {
    loadSessions();
  }
}, 5000);

// API Helpers
async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  return res.json();
}

// WebSocket Connection
let wsReconnectAttempts = 0;
let wsReconnectTimer = null;

function connectWS() {
  // Clear any pending reconnect
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }

  // Don't create new connection if one exists and is connecting/open
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    wsReconnectAttempts = 0;
    statusDot.classList.add('online');
    statusText.textContent = 'Connected';
    addLog({ level: 'info', source: 'Panel', message: 'Connected to Gateway', timestamp: new Date() });
  };

  ws.onclose = (event) => {
    statusDot.classList.remove('online');
    statusText.textContent = 'Disconnected';

    // Exponential backoff for reconnection (1s, 2s, 4s, 8s, max 30s)
    const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts), 30000);
    wsReconnectAttempts++;

    // Only log if it was an unexpected close
    if (event.code !== 1000 && event.code !== 1001) {
      console.log(`WebSocket closed (code: ${event.code}), reconnecting in ${delay}ms...`);
    }

    wsReconnectTimer = setTimeout(connectWS, delay);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'log') addLog(data);
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    statusText.textContent = 'Error';
  };
}

// Activity Feed (Dashboard)
const MAX_ACTIVITY_ITEMS = 20;
let activityItems = [];

function addActivityItem(entry) {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  // Remove empty state
  const empty = feed.querySelector('.dash-activity-empty');
  if (empty) empty.remove();

  // Add to array (limit size)
  activityItems.unshift(entry);
  if (activityItems.length > MAX_ACTIVITY_ITEMS) {
    activityItems.pop();
  }

  // Create item element
  const time = new Date(entry.timestamp).toLocaleTimeString();
  const div = document.createElement('div');
  div.className = 'dash-activity-item';
  div.innerHTML = `
    <span class="dash-activity-time">${time}</span>
    <span class="dash-activity-source">${entry.source || 'System'}</span>
    <span class="dash-activity-msg">${escapeHtml(entry.message)}</span>
  `;

  // Insert at top
  if (feed.firstChild) {
    feed.insertBefore(div, feed.firstChild);
  } else {
    feed.appendChild(div);
  }

  // Limit DOM elements
  while (feed.children.length > MAX_ACTIVITY_ITEMS) {
    feed.removeChild(feed.lastChild);
  }
}

function clearActivity() {
  const feed = document.getElementById('activity-feed');
  if (feed) {
    feed.innerHTML = '<div class="dash-activity-empty">No recent activity</div>';
    activityItems = [];
  }
}

// Logs
function addLog(entry) {
  const logLevel = document.getElementById('log-level').value;
  const levels = ['debug', 'info', 'warn', 'error'];
  if (levels.indexOf(entry.level) < levels.indexOf(logLevel)) return;

  const time = new Date(entry.timestamp).toLocaleTimeString();
  const div = document.createElement('div');
  div.className = 'log-entry';
  div.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-level ${entry.level}">${entry.level}</span>
    <span class="log-source">${entry.source || '-'}</span>
    <span class="log-message">${escapeHtml(entry.message)}</span>
  `;
  logsContainer.appendChild(div);
  if (autoScroll.checked) logsContainer.scrollTop = logsContainer.scrollHeight;

  // Also add to activity feed (info level and above)
  if (levels.indexOf(entry.level) >= levels.indexOf('info')) {
    addActivityItem(entry);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Dashboard
async function loadDashboard() {
  try {
    const status = await api('/status');
    if (status.ok) {
      document.getElementById('agent-status').textContent = status.status;
      document.getElementById('session-count').textContent = status.sessions;
      document.getElementById('heartbeat-status').textContent = status.scheduler?.heartbeatRunning ? 'Running' : 'Paused';
      document.getElementById('job-count').textContent = status.scheduler?.jobCount || 0;

      // Nodes - simplified for config card
      const nodesList = document.getElementById('nodes-list');
      const nodeCount = status.nodes?.nodes?.length || 0;
      if (nodesList) {
        nodesList.textContent = nodeCount > 0 ? `${nodeCount} connected` : 'None';
      }

      // Channels - simplified for config card
      const channelsList = document.getElementById('channels-list');
      if (channelsList) {
        const channelCount = status.channels?.length || 0;
        channelsList.textContent = channelCount > 0 ? `${channelCount} active` : 'CLI only';
      }

      // Scheduler info
      const schedulerInfo = document.getElementById('scheduler-info');
      if (schedulerInfo) {
        schedulerInfo.textContent = status.scheduler?.heartbeatRunning ? 'Running' : 'Paused';
      }

      // Update system health
      const isOnline = status.status === 'online';
      updateSystemHealth(
        isOnline,
        isOnline ? 'All Systems Operational' : 'System Offline',
        isOnline ? `Gateway connected • ${status.sessions} sessions` : 'Check agent worker status'
      );
    }
  } catch (err) {
    console.error('Failed to load dashboard:', err);
    updateSystemHealth(false, 'Connection Error', 'Unable to reach Gateway');
  }
}

// Model Selector
let modelOptions = {};
let currentProvider = '';
let currentModel = '';

async function loadModelConfig() {
  try {
    const { ok, provider, model, options } = await api('/model/config');
    if (ok) {
      modelOptions = options;
      currentProvider = provider;
      currentModel = model;

      // Populate provider dropdown
      const providerSelect = document.getElementById('model-provider');
      providerSelect.innerHTML = Object.entries(options).map(([key, val]) =>
        `<option value="${key}" ${key === provider ? 'selected' : ''}>${val.name}</option>`
      ).join('');

      // Populate model dropdown
      updateModelDropdown(provider);

      // Show current config as badge
      const providerName = options[provider]?.name || provider;
      const modelName = options[provider]?.models?.find(m => m.id === model)?.name || model;
      document.getElementById('model-current').textContent = `${providerName} • ${modelName}`;
    }
  } catch (err) {
    console.error('Failed to load model config:', err);
  }
}

function updateModelDropdown(provider) {
  const modelSelect = document.getElementById('model-name');
  const models = modelOptions[provider]?.models || [];

  modelSelect.innerHTML = models.map(m =>
    `<option value="${m.id}" ${m.id === currentModel ? 'selected' : ''}>${m.name}</option>`
  ).join('');
}

document.getElementById('model-provider').addEventListener('change', (e) => {
  updateModelDropdown(e.target.value);
});

document.getElementById('save-model').addEventListener('click', async () => {
  const btn = document.getElementById('save-model');
  const provider = document.getElementById('model-provider').value;
  const model = document.getElementById('model-name').value;

  if (!provider || !model) {
    alert('Please select a provider and model');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const result = await api('/model/config', {
      method: 'POST',
      body: { provider, model }
    });

    if (result.ok) {
      btn.textContent = 'Saved!';
      addLog({ level: 'info', source: 'Model', message: `Model updated to ${provider}/${model}`, timestamp: new Date() });

      // Update current display as badge
      const providerName = modelOptions[provider]?.name || provider;
      const modelDisplayName = modelOptions[provider]?.models?.find(m => m.id === model)?.name || model;
      document.getElementById('model-current').textContent = `${providerName} • ${modelDisplayName}`;

      // Prompt to restart agent
      if (confirm('Model configuration saved. Restart agent worker now?')) {
        // TODO: Add agent restart endpoint
        addLog({ level: 'warn', source: 'Model', message: 'Please restart agent worker manually', timestamp: new Date() });
      }
    } else {
      btn.textContent = 'Failed';
      addLog({ level: 'error', source: 'Model', message: `Failed to save: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    btn.textContent = 'Failed';
    addLog({ level: 'error', source: 'Model', message: `Error: ${err.message}`, timestamp: new Date() });
  }

  setTimeout(() => {
    btn.textContent = 'Save Model';
    btn.disabled = false;
  }, 2000);
});

// Agent Control
async function checkAgentStatus() {
  const statusEl = document.getElementById('agent-worker-status');
  statusEl.textContent = 'Checking...';
  statusEl.className = 'checking';

  try {
    const { ok, status, message } = await api('/agent/health');
    if (ok) {
      statusEl.textContent = status === 'online' ? 'Online' : status === 'offline' ? 'Offline' : status;
      statusEl.className = status;
    } else {
      statusEl.textContent = 'Unknown';
      statusEl.className = '';
    }
  } catch (err) {
    statusEl.textContent = 'Error';
    statusEl.className = 'offline';
  }
}

document.getElementById('check-agent').addEventListener('click', checkAgentStatus);

document.getElementById('restart-agent').addEventListener('click', async () => {
  if (!confirm('Restart the agent worker? This will open a new terminal window.')) {
    return;
  }

  const btn = document.getElementById('restart-agent');
  btn.disabled = true;
  btn.textContent = 'Restarting...';

  try {
    const result = await api('/agent/restart', { method: 'POST' });
    if (result.ok) {
      btn.textContent = 'Started!';
      addLog({ level: 'info', source: 'Agent', message: 'Agent worker restart initiated', timestamp: new Date() });

      // Check status after a delay
      setTimeout(checkAgentStatus, 3000);
    } else {
      btn.textContent = 'Failed';
      addLog({ level: 'error', source: 'Agent', message: `Restart failed: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    btn.textContent = 'Failed';
    addLog({ level: 'error', source: 'Agent', message: `Error: ${err.message}`, timestamp: new Date() });
  }

  setTimeout(() => {
    btn.textContent = 'Restart Agent Worker';
    btn.disabled = false;
  }, 3000);
});

// Sessions Manager
async function loadSessions() {
  const sessionsList = document.getElementById('sessions-list');
  sessionsList.innerHTML = '<tr><td colspan="7" class="loading">Loading sessions...</td></tr>';

  try {
    const { ok, sessions } = await api('/sessions');
    if (ok && sessions) {
      if (sessions.length === 0) {
        sessionsList.innerHTML = '<tr><td colspan="7" class="loading">No active sessions</td></tr>';
        return;
      }

      sessionsList.innerHTML = sessions.map(s => {
        const createdAt = new Date(s.createdAt).toLocaleString();
        const lastActivity = new Date(s.lastActivityAt).toLocaleString();
        const statusClass = s.paired ? 'paired' : 'pending';
        const statusText = s.paired ? 'Paired' : (s.pairingCode ? `Pending (${s.pairingCode})` : 'Unpaired');

        return `
          <tr>
            <td><span class="session-id" title="${escapeHtml(s.id)}">${escapeHtml(s.id)}</span></td>
            <td>${escapeHtml(s.channelType || '-')}</td>
            <td>${escapeHtml(s.userName || s.userId || '-')}</td>
            <td><span class="session-status ${statusClass}">${statusText}</span></td>
            <td>${createdAt}</td>
            <td>${lastActivity}</td>
            <td class="session-actions">
              ${!s.paired ? `<button class="btn btn-sm" onclick="approveSession('${encodeURIComponent(s.id)}')">Approve</button>` : ''}
              <button class="btn btn-sm btn-danger" onclick="deleteSession('${encodeURIComponent(s.id)}')">×</button>
            </td>
          </tr>
        `;
      }).join('');
    } else {
      sessionsList.innerHTML = '<tr><td colspan="7" class="loading">Failed to load sessions</td></tr>';
    }
  } catch (err) {
    sessionsList.innerHTML = '<tr><td colspan="7" class="loading">Error loading sessions</td></tr>';
  }
}

async function approveSession(encodedId) {
  const sessionId = decodeURIComponent(encodedId);
  try {
    const result = await api(`/sessions/${encodedId}/approve`, { method: 'POST', body: {} });
    if (result.ok) {
      addLog({ level: 'info', source: 'Sessions', message: `Session approved: ${sessionId}`, timestamp: new Date() });
      loadSessions();
    } else {
      addLog({ level: 'error', source: 'Sessions', message: `Failed to approve: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    addLog({ level: 'error', source: 'Sessions', message: `Error: ${err.message}`, timestamp: new Date() });
  }
}

async function deleteSession(encodedId) {
  const sessionId = decodeURIComponent(encodedId);
  if (!confirm(`Delete session: ${sessionId}?`)) return;

  try {
    const result = await api(`/sessions/${encodedId}`, { method: 'DELETE' });
    if (result.ok) {
      addLog({ level: 'info', source: 'Sessions', message: `Session deleted: ${sessionId}`, timestamp: new Date() });
      loadSessions();
    } else {
      addLog({ level: 'error', source: 'Sessions', message: `Failed to delete: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    addLog({ level: 'error', source: 'Sessions', message: `Error: ${err.message}`, timestamp: new Date() });
  }
}

document.getElementById('refresh-sessions').addEventListener('click', loadSessions);

document.getElementById('clear-sessions').addEventListener('click', async () => {
  if (!confirm('Clear all sessions? This cannot be undone.')) return;

  try {
    const result = await api('/sessions/clear', { method: 'POST' });
    if (result.ok) {
      addLog({ level: 'info', source: 'Sessions', message: `Cleared ${result.cleared} sessions`, timestamp: new Date() });
      loadSessions();
    } else {
      addLog({ level: 'error', source: 'Sessions', message: `Failed to clear: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    addLog({ level: 'error', source: 'Sessions', message: `Error: ${err.message}`, timestamp: new Date() });
  }
});

// Memory Viewer
let currentMemoryFile = null;
let memoryModified = false;

async function loadMemoryFiles() {
  const filesContainer = document.getElementById('memory-files');
  filesContainer.innerHTML = 'Loading...';

  try {
    const { ok, files } = await api('/memory/files');
    if (ok && files) {
      if (files.length === 0) {
        filesContainer.innerHTML = '<div class="text-muted">No memory files found</div>';
        return;
      }

      filesContainer.innerHTML = files.map(f => {
        const modified = new Date(f.modified).toLocaleDateString();
        const sizeStr = f.size < 1024 ? `${f.size}B` : `${(f.size/1024).toFixed(1)}KB`;
        return `
          <div class="memory-file-item" data-path="${escapeHtml(f.path)}">
            <span class="memory-file-name">
              ${escapeHtml(f.name)}
              <span class="memory-file-type ${f.type}">${f.type}</span>
            </span>
            <span class="memory-file-meta">${modified} • ${sizeStr}</span>
          </div>
        `;
      }).join('');

      // Add click handlers
      filesContainer.querySelectorAll('.memory-file-item').forEach(item => {
        item.addEventListener('click', () => selectMemoryFile(item.dataset.path, item));
      });
    } else {
      filesContainer.innerHTML = '<div class="text-muted">Failed to load</div>';
    }
  } catch (err) {
    filesContainer.innerHTML = '<div class="text-muted">Error loading files</div>';
  }
}

async function selectMemoryFile(filePath, element) {
  // Check for unsaved changes
  if (memoryModified && currentMemoryFile) {
    if (!confirm('You have unsaved changes. Discard them?')) {
      return;
    }
  }

  // Update UI
  document.querySelectorAll('.memory-file-item.active').forEach(el => el.classList.remove('active'));
  element.classList.add('active');

  currentMemoryFile = filePath;
  memoryModified = false;

  document.getElementById('memory-filename').textContent = filePath;
  document.getElementById('save-memory').style.display = 'inline-block';

  const contentArea = document.getElementById('memory-content');
  contentArea.value = 'Loading...';
  contentArea.disabled = true;

  try {
    const { ok, content, error } = await api(`/memory/file?path=${encodeURIComponent(filePath)}`);
    if (ok) {
      contentArea.value = content;
      contentArea.disabled = false;
    } else {
      contentArea.value = `Error: ${error}`;
    }
  } catch (err) {
    contentArea.value = `Failed to load: ${err.message}`;
  }
}

document.getElementById('memory-content').addEventListener('input', () => {
  memoryModified = true;
});

document.getElementById('refresh-memory').addEventListener('click', loadMemoryFiles);

document.getElementById('save-memory').addEventListener('click', async () => {
  if (!currentMemoryFile) return;

  const btn = document.getElementById('save-memory');
  const content = document.getElementById('memory-content').value;

  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const result = await api('/memory/file', {
      method: 'POST',
      body: { path: currentMemoryFile, content }
    });

    if (result.ok) {
      btn.textContent = 'Saved!';
      memoryModified = false;
      addLog({ level: 'info', source: 'Memory', message: `Saved: ${currentMemoryFile}`, timestamp: new Date() });
    } else {
      btn.textContent = 'Failed';
      addLog({ level: 'error', source: 'Memory', message: `Save failed: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    btn.textContent = 'Failed';
    addLog({ level: 'error', source: 'Memory', message: `Error: ${err.message}`, timestamp: new Date() });
  }

  setTimeout(() => {
    btn.textContent = 'Save';
    btn.disabled = false;
  }, 2000);
});

// Skills
let allSkills = [];

async function loadSkillCategories() {
  try {
    const { ok, categories } = await api('/skills/categories');
    if (ok && categories) {
      const select = document.getElementById('skills-category-filter');
      select.innerHTML = '<option value="">All Categories</option>' +
        categories.map(c => `<option value="${c}">${c}</option>`).join('');
    }
  } catch (err) {
    console.error('Failed to load categories:', err);
  }
}

function renderSkills(skills) {
  const skillsList = document.getElementById('skills-list');
  if (!skills || skills.length === 0) {
    skillsList.innerHTML = '<div class="text-secondary">No skills found</div>';
    return;
  }

  skillsList.innerHTML = skills.map(s => `
    <div class="skill-card ${s.enabled ? '' : 'disabled'}" data-skill-id="${s.id}">
      <div class="skill-header">
        <span class="skill-name">${escapeHtml(s.name)}</span>
        <label class="toggle" onclick="event.stopPropagation()">
          <input type="checkbox" ${s.enabled ? 'checked' : ''} data-skill="${s.id}">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="skill-meta">
        <span class="skill-version">v${escapeHtml(s.version)}</span>
        <span class="skill-category">${escapeHtml(s.category || 'general')}</span>
        <span class="skill-source ${s.source || 'bundled'}">${s.source || 'bundled'}</span>
      </div>
      <div class="skill-desc">${escapeHtml(s.description || 'No description')}</div>
      <div class="skill-triggers">
        ${(s.triggers || []).slice(0, 4).map(t => `<span class="skill-trigger">${escapeHtml(t)}</span>`).join('')}
        ${(s.triggers || []).length > 4 ? `<span class="skill-trigger">+${s.triggers.length - 4} more</span>` : ''}
      </div>
      ${(s.tags || []).length > 0 ? `
        <div class="skill-tags">
          ${s.tags.slice(0, 5).map(t => `<span class="skill-tag">${escapeHtml(t)}</span>`).join('')}
        </div>
      ` : ''}
    </div>
  `).join('');

  // Add toggle handlers
  skillsList.querySelectorAll('input[data-skill]').forEach(input => {
    input.addEventListener('change', async (e) => {
      e.stopPropagation();
      const skillId = e.target.dataset.skill;
      await api(`/skills/${skillId}/toggle`, { method: 'POST', body: { enabled: e.target.checked } });
      loadSkills();
    });
  });

  // Add click handlers for detail modal
  skillsList.querySelectorAll('.skill-card').forEach(card => {
    card.addEventListener('click', () => openSkillModal(card.dataset.skillId));
  });
}

function filterSkills() {
  const searchTerm = (document.getElementById('skills-search')?.value || '').toLowerCase();
  const category = document.getElementById('skills-category-filter')?.value || '';
  const source = document.getElementById('skills-source-filter')?.value || '';

  const filtered = allSkills.filter(s => {
    const matchesSearch = !searchTerm ||
      s.name.toLowerCase().includes(searchTerm) ||
      (s.description || '').toLowerCase().includes(searchTerm) ||
      (s.triggers || []).some(t => t.toLowerCase().includes(searchTerm)) ||
      (s.tags || []).some(t => t.toLowerCase().includes(searchTerm));
    const matchesCategory = !category || s.category === category;
    const matchesSource = !source || s.source === source;
    return matchesSearch && matchesCategory && matchesSource;
  });

  renderSkills(filtered);
}

async function loadSkills() {
  const skillsList = document.getElementById('skills-list');
  try {
    const { ok, skills } = await api('/skills');
    if (ok && skills) {
      allSkills = skills;
      renderSkills(skills);
      loadSkillCategories();
    }
  } catch (err) {
    skillsList.innerHTML = '<div>Failed to load skills</div>';
  }
}

async function openSkillModal(skillId) {
  const modal = document.getElementById('skill-modal');
  const title = document.getElementById('skill-modal-title');
  const body = document.getElementById('skill-modal-body');

  try {
    const { ok, skill } = await api(`/skills/${skillId}`);
    if (!ok || !skill) {
      body.innerHTML = '<div class="text-secondary">Skill not found</div>';
      modal.classList.add('active');
      return;
    }

    title.textContent = skill.name;
    body.innerHTML = `
      <div class="modal-section">
        <div class="modal-section-title">Description</div>
        <div class="modal-section-content">${escapeHtml(skill.description || 'No description')}</div>
      </div>
      <div class="modal-section">
        <div class="modal-section-title">Details</div>
        <div class="modal-section-content">
          <div><strong>Version:</strong> ${escapeHtml(skill.version)}</div>
          <div><strong>Category:</strong> ${escapeHtml(skill.category || 'general')}</div>
          <div><strong>Source:</strong> ${skill.source || 'bundled'}</div>
          ${skill.author ? `<div><strong>Author:</strong> ${escapeHtml(skill.author)}</div>` : ''}
          ${skill.license ? `<div><strong>License:</strong> ${escapeHtml(skill.license)}</div>` : ''}
          <div><strong>Status:</strong> ${skill.enabled ? '<span style="color: var(--success)">Enabled</span>' : '<span style="color: var(--text-muted)">Disabled</span>'}</div>
        </div>
      </div>
      ${(skill.triggers || []).length > 0 ? `
        <div class="modal-section">
          <div class="modal-section-title">Triggers</div>
          <div class="skill-triggers">
            ${skill.triggers.map(t => `<span class="skill-trigger">${escapeHtml(t)}</span>`).join('')}
          </div>
        </div>
      ` : ''}
      ${(skill.tags || []).length > 0 ? `
        <div class="modal-section">
          <div class="modal-section-title">Tags</div>
          <div class="skill-tags">
            ${skill.tags.map(t => `<span class="skill-tag">${escapeHtml(t)}</span>`).join('')}
          </div>
        </div>
      ` : ''}
      ${(skill.entrypoints || []).length > 0 ? `
        <div class="modal-section">
          <div class="modal-section-title">Entrypoints</div>
          <ul class="modal-entrypoints">
            ${skill.entrypoints.map(e => `
              <li class="modal-entrypoint">
                <div class="modal-entrypoint-name">${escapeHtml(e.name)}</div>
                <div class="modal-entrypoint-desc">${escapeHtml(e.description || '')}</div>
              </li>
            `).join('')}
          </ul>
        </div>
      ` : ''}
      ${(skill.requiredPermissions || []).length > 0 ? `
        <div class="modal-section">
          <div class="modal-section-title">Required Permissions</div>
          <div class="modal-section-content">${skill.requiredPermissions.map(p => escapeHtml(p)).join(', ')}</div>
        </div>
      ` : ''}
      <div class="modal-section">
        <div class="modal-section-title">Path</div>
        <div class="modal-section-content" style="word-break: break-all; font-family: monospace; font-size: 0.8rem;">${escapeHtml(skill.path)}</div>
      </div>
    `;
    modal.classList.add('active');
  } catch (err) {
    body.innerHTML = '<div class="text-secondary">Failed to load skill details</div>';
    modal.classList.add('active');
  }
}

function closeSkillModal() {
  document.getElementById('skill-modal')?.classList.remove('active');
}

// Skills event listeners
document.getElementById('skills-search')?.addEventListener('input', filterSkills);
document.getElementById('skills-category-filter')?.addEventListener('change', filterSkills);
document.getElementById('skills-source-filter')?.addEventListener('change', filterSkills);
document.getElementById('skill-modal-close')?.addEventListener('click', closeSkillModal);
document.getElementById('skill-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'skill-modal') closeSkillModal();
});

// Helper function to escape HTML
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Workspace Browser
let selectedFilePath = null;

function renderFileTree(files, container) {
  if (!files || files.length === 0) {
    container.innerHTML = '<div class="file-tree-empty">No files in workspace</div>';
    return;
  }

  container.innerHTML = '';

  function createTreeItem(file) {
    const item = document.createElement('div');

    if (file.type === 'directory') {
      const dirItem = document.createElement('div');
      dirItem.className = 'file-tree-item directory';
      dirItem.innerHTML = `<span class="file-icon">📁</span>${file.name}`;
      dirItem.addEventListener('click', () => {
        const children = item.querySelector('.file-tree-children');
        if (children) {
          children.style.display = children.style.display === 'none' ? 'block' : 'none';
        }
      });
      item.appendChild(dirItem);

      if (file.children && file.children.length > 0) {
        const childContainer = document.createElement('div');
        childContainer.className = 'file-tree-children';
        file.children.forEach(child => {
          childContainer.appendChild(createTreeItem(child));
        });
        item.appendChild(childContainer);
      }
    } else {
      item.className = 'file-tree-item';
      const sizeStr = file.size < 1024 ? `${file.size}B` :
                     file.size < 1024*1024 ? `${(file.size/1024).toFixed(1)}KB` :
                     `${(file.size/1024/1024).toFixed(1)}MB`;
      item.innerHTML = `<span class="file-icon">📄</span>${file.name} <span style="margin-left:auto;color:var(--text-muted);font-size:0.75rem">${sizeStr}</span>`;
      item.dataset.path = file.path;
      item.addEventListener('click', () => selectFile(file.path, item));
    }

    return item;
  }

  files.forEach(file => {
    container.appendChild(createTreeItem(file));
  });
}

async function loadWorkspace() {
  const fileTree = document.getElementById('file-tree');
  fileTree.innerHTML = 'Loading...';

  try {
    const { ok, files, error } = await api('/workspace/files');
    if (ok) {
      renderFileTree(files, fileTree);
    } else {
      fileTree.innerHTML = `<div class="file-tree-empty">Error: ${error}</div>`;
    }
  } catch (err) {
    fileTree.innerHTML = `<div class="file-tree-empty">Failed to load workspace</div>`;
  }
}

async function selectFile(filePath, element) {
  // Update UI
  document.querySelectorAll('.file-tree-item.active').forEach(el => el.classList.remove('active'));
  element.classList.add('active');

  selectedFilePath = filePath;
  document.getElementById('preview-filename').textContent = filePath;
  document.getElementById('download-file').style.display = 'inline-block';

  const previewContent = document.getElementById('preview-content');
  previewContent.textContent = 'Loading...';

  try {
    const { ok, content, truncated, message, error } = await api(`/workspace/file?path=${encodeURIComponent(filePath)}`);
    if (ok) {
      if (truncated) {
        previewContent.textContent = message || 'File too large to preview';
      } else {
        previewContent.textContent = content;
      }
    } else {
      previewContent.textContent = `Error: ${error}`;
    }
  } catch (err) {
    previewContent.textContent = `Failed to load file: ${err.message}`;
  }
}

document.getElementById('refresh-workspace').addEventListener('click', loadWorkspace);

document.getElementById('download-file').addEventListener('click', () => {
  if (selectedFilePath) {
    window.open(`${API_BASE}/workspace/download?path=${encodeURIComponent(selectedFilePath)}`, '_blank');
  }
});

// Chat
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

// Store chat history for export
const chatHistory = [];

function addChatMessage(text, isUser = false) {
  const div = document.createElement('div');
  div.className = `chat-msg ${isUser ? 'user' : 'assistant'}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  // Store for export
  chatHistory.push({
    role: isUser ? 'user' : 'assistant',
    content: text,
    timestamp: new Date().toISOString()
  });
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;

  addChatMessage(text, true);
  chatInput.value = '';
  sendBtn.disabled = true;

  try {
    const response = await api('/chat', {
      method: 'POST',
      body: { text, session_id: sessionId }
    });

    // Check if pairing is required
    if (response.pairingRequired) {
      // Show approval toast
      showApprovalToast(
        response.session_id || sessionId,
        response.pairingCode,
        'panel',
        ''
      );
      // Also show the message in chat for clarity
      addChatMessage(response.text || '🔒 Session approval required. Please approve the session to continue.');
    } else if (response.ok && response.text) {
      addChatMessage(response.text);
    } else if (response.error) {
      addChatMessage(`Error: ${response.error}`);
    } else if (response.text) {
      // Fallback for responses that have text but no ok flag
      addChatMessage(response.text);
    }
  } catch (err) {
    addChatMessage(`Error: ${err.message}`);
  }

  // Refresh sessions in case a new one was created
  loadSessions();

  sendBtn.disabled = false;
  chatInput.focus();
}

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') sendMessage();
});

// Clear chat
document.getElementById('clear-chat').addEventListener('click', () => {
  if (chatHistory.length === 0 || confirm('Clear chat history?')) {
    chatMessages.innerHTML = '';
    chatHistory.length = 0;
    addLog({ level: 'info', source: 'Chat', message: 'Chat cleared', timestamp: new Date() });
  }
});

// Export chat
document.getElementById('export-chat').addEventListener('click', () => {
  if (chatHistory.length === 0) {
    alert('No messages to export');
    return;
  }

  const format = document.getElementById('export-format').value;
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  let content, filename, mimeType;

  if (format === 'json') {
    content = JSON.stringify({
      exported: new Date().toISOString(),
      sessionId: sessionId,
      messages: chatHistory
    }, null, 2);
    filename = `chat-export-${timestamp}.json`;
    mimeType = 'application/json';
  } else {
    // Markdown format
    const lines = [
      `# Chat Export`,
      ``,
      `**Session:** ${sessionId}`,
      `**Exported:** ${new Date().toLocaleString()}`,
      ``,
      `---`,
      ``
    ];

    for (const msg of chatHistory) {
      const time = new Date(msg.timestamp).toLocaleTimeString();
      const role = msg.role === 'user' ? '**You**' : '**AP3X**';
      lines.push(`### ${role} (${time})`);
      lines.push(``);
      lines.push(msg.content);
      lines.push(``);
    }

    content = lines.join('\n');
    filename = `chat-export-${timestamp}.md`;
    mimeType = 'text/markdown';
  }

  // Trigger download
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  addLog({ level: 'info', source: 'Chat', message: `Exported ${chatHistory.length} messages as ${format.toUpperCase()}`, timestamp: new Date() });
});

// Event Handlers
document.getElementById('trigger-heartbeat').addEventListener('click', async () => {
  const btn = document.getElementById('trigger-heartbeat');
  btn.disabled = true;
  btn.textContent = 'Triggering...';

  try {
    await api('/scheduler/heartbeat/trigger', { method: 'POST' });
    btn.textContent = 'Triggered!';
    setTimeout(() => {
      btn.textContent = 'Trigger Heartbeat';
      btn.disabled = false;
    }, 2000);
  } catch (err) {
    btn.textContent = 'Failed';
    setTimeout(() => {
      btn.textContent = 'Trigger Heartbeat';
      btn.disabled = false;
    }, 2000);
  }
});

document.getElementById('pause-heartbeat').addEventListener('click', async () => {
  await api('/scheduler/heartbeat/pause', { method: 'POST' });
  loadDashboard();
});

document.getElementById('resume-heartbeat').addEventListener('click', async () => {
  await api('/scheduler/heartbeat/resume', { method: 'POST' });
  loadDashboard();
});

document.getElementById('clear-logs').addEventListener('click', async () => {
  logsContainer.innerHTML = '';
  await api('/logs/clear', { method: 'POST' });
});

document.getElementById('launch-tui').addEventListener('click', async () => {
  const btn = document.getElementById('launch-tui');
  btn.disabled = true;
  btn.textContent = 'Launching...';

  try {
    const result = await api('/tui/launch', { method: 'POST' });
    if (result.ok) {
      btn.textContent = 'Launched!';
      addLog({ level: 'info', source: 'Panel', message: 'TUI launched successfully', timestamp: new Date() });
    } else {
      btn.textContent = 'Failed';
      addLog({ level: 'error', source: 'Panel', message: `TUI launch failed: ${result.error}`, timestamp: new Date() });
    }
  } catch (err) {
    btn.textContent = 'Failed';
    addLog({ level: 'error', source: 'Panel', message: `TUI launch error: ${err.message}`, timestamp: new Date() });
  }

  setTimeout(() => {
    btn.textContent = 'Launch TUI';
    btn.disabled = false;
  }, 2000);
});

// Quick Actions (Dashboard)
document.getElementById('quick-new-chat')?.addEventListener('click', () => {
  // Switch to chat tab
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector('[data-tab="chat"]')?.classList.add('active');
  document.getElementById('chat')?.classList.add('active');
  document.getElementById('chat-input')?.focus();
});

document.getElementById('quick-view-logs')?.addEventListener('click', () => {
  // Switch to debug logs tab
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelector('[data-tab="logs"]')?.classList.add('active');
  document.getElementById('logs')?.classList.add('active');
});

document.getElementById('quick-restart')?.addEventListener('click', () => {
  // Trigger agent restart
  document.getElementById('restart-agent')?.click();
});

document.getElementById('clear-activity')?.addEventListener('click', clearActivity);

// Update system health indicator
function updateSystemHealth(isHealthy, statusText, subText) {
  const indicator = document.getElementById('system-health-indicator');
  const healthText = document.getElementById('system-health-text');
  const healthSub = document.getElementById('system-health-sub');

  if (indicator) {
    if (isHealthy) {
      indicator.classList.remove('error');
      indicator.querySelector('.dash-status-icon').textContent = '✓';
    } else {
      indicator.classList.add('error');
      indicator.querySelector('.dash-status-icon').textContent = '!';
    }
  }
  if (healthText) healthText.textContent = statusText;
  if (healthSub) healthSub.textContent = subText;
}

// ==================== NODES TAB ====================

async function loadNodes() {
  try {
    const data = await api('/nodes');
    const nodesGrid = document.getElementById('nodes-grid');

    if (!data.ok || !data.nodes || data.nodes.length === 0) {
      nodesGrid.innerHTML = '<div class="nodes-empty">No nodes connected</div>';
      return;
    }

    nodesGrid.innerHTML = data.nodes.map(node => `
      <div class="node-card">
        <div class="node-card-header">
          <div class="node-card-title">
            <span class="node-card-name">${escapeHtml(node.name)}</span>
            <span class="node-card-type">${node.type}</span>
          </div>
          <span class="node-status ${node.status}">${node.status}</span>
        </div>
        <div class="node-card-body">
          <div class="node-info-row">
            <span class="node-info-label">Platform:</span>
            <span class="node-info-value">${node.platform?.os || 'Unknown'} ${node.platform?.arch || ''}</span>
          </div>
          <div class="node-info-row">
            <span class="node-info-label">Capabilities:</span>
            <span class="node-info-value">${node.capabilities?.length || 0}</span>
          </div>
          ${node.capabilities && node.capabilities.length > 0 ? `
            <div class="node-capabilities">
              ${node.capabilities.map(cap => `<span class="capability-badge">${cap}</span>`).join('')}
            </div>
          ` : ''}
          ${node.lastSeen ? `
            <div class="node-info-row">
              <span class="node-info-label">Last Seen:</span>
              <span class="node-info-value">${new Date(node.lastSeen).toLocaleString()}</span>
            </div>
          ` : ''}
        </div>
        ${node.type === 'companion' ? `
          <div class="node-card-actions">
            <button class="btn btn-sm btn-danger" onclick="disconnectNode('${node.id}')">Disconnect</button>
          </div>
        ` : ''}
      </div>
    `).join('');
  } catch (err) {
    console.error('Failed to load nodes:', err);
    document.getElementById('nodes-grid').innerHTML = '<div class="nodes-error">Failed to load nodes</div>';
  }
}

async function loadApprovedNodes() {
  try {
    const data = await api('/nodes/approved');
    const approvedList = document.getElementById('approved-nodes-list');

    if (!data.ok || !data.nodes || data.nodes.length === 0) {
      approvedList.innerHTML = '<div class="nodes-empty">No approved nodes</div>';
      return;
    }

    approvedList.innerHTML = data.nodes.map(node => `
      <div class="approved-node-item">
        <div class="approved-node-info">
          <span class="approved-node-name">${escapeHtml(node.name)}</span>
          <span class="approved-node-id">${node.nodeId}</span>
          <span class="approved-node-date">Approved: ${new Date(node.approvedAt).toLocaleString()}</span>
        </div>
        <button class="btn btn-sm btn-danger" onclick="removeNodeApproval('${node.nodeId}')">Remove</button>
      </div>
    `).join('');
  } catch (err) {
    console.error('Failed to load approved nodes:', err);
    document.getElementById('approved-nodes-list').innerHTML = '<div class="nodes-error">Failed to load approved nodes</div>';
  }
}

async function loadPairingCode() {
  try {
    const data = await api('/nodes/pairing/active');
    const display = document.getElementById('pairing-code-display');

    if (data.ok && data.code) {
      display.innerHTML = `
        <div class="pairing-code-active">
          <div class="pairing-code-label">Pairing Code:</div>
          <div class="pairing-code-value">${data.code}</div>
          <div class="pairing-code-hint">Enter this code on your companion device</div>
          <div class="pairing-code-expiry">Expires in 5 minutes</div>
        </div>
      `;
    } else {
      display.innerHTML = '<div class="pairing-code-empty">No active pairing code</div>';
    }
  } catch (err) {
    console.error('Failed to load pairing code:', err);
  }
}

async function generatePairingCode() {
  try {
    const data = await api('/nodes/pairing/generate', { method: 'POST' });
    if (data.ok && data.code) {
      await loadPairingCode();
      addActivityItem({ level: 'info', source: 'Nodes', message: `Pairing code generated: ${data.code}`, timestamp: new Date() });
    }
  } catch (err) {
    console.error('Failed to generate pairing code:', err);
    addActivityItem({ level: 'error', source: 'Nodes', message: 'Failed to generate pairing code', timestamp: new Date() });
  }
}

async function disconnectNode(nodeId) {
  if (!confirm('Are you sure you want to disconnect this node?')) return;

  try {
    await api(`/nodes/${nodeId}/approval`, { method: 'DELETE' });
    await loadNodes();
    await loadApprovedNodes();
    addActivityItem({ level: 'info', source: 'Nodes', message: `Node ${nodeId} disconnected`, timestamp: new Date() });
  } catch (err) {
    console.error('Failed to disconnect node:', err);
    addActivityItem({ level: 'error', source: 'Nodes', message: 'Failed to disconnect node', timestamp: new Date() });
  }
}

async function removeNodeApproval(nodeId) {
  if (!confirm('Are you sure you want to remove approval for this node?')) return;

  try {
    await api(`/nodes/${nodeId}/approval`, { method: 'DELETE' });
    await loadApprovedNodes();
    await loadNodes();
    addActivityItem({ level: 'info', source: 'Nodes', message: `Node approval removed: ${nodeId}`, timestamp: new Date() });
  } catch (err) {
    console.error('Failed to remove node approval:', err);
    addActivityItem({ level: 'error', source: 'Nodes', message: 'Failed to remove node approval', timestamp: new Date() });
  }
}

// Nodes tab event listeners
document.getElementById('generate-pairing-code')?.addEventListener('click', generatePairingCode);
document.getElementById('refresh-nodes')?.addEventListener('click', () => {
  loadNodes();
  loadApprovedNodes();
  loadPairingCode();
});

// ==================== SUBAGENTS TAB ====================

let allSubagents = [];

async function loadSubagents() {
  const subagentsList = document.getElementById('subagents-list');
  try {
    const data = await api('/subagents');
    if (data.subagents) {
      allSubagents = data.subagents;
      renderSubagents(data.subagents);
    }
  } catch (err) {
    subagentsList.innerHTML = '<div class="error">Failed to load subagents</div>';
    console.error('Failed to load subagents:', err);
  }
}

function renderSubagents(subagents) {
  const subagentsList = document.getElementById('subagents-list');

  if (!subagents || subagents.length === 0) {
    subagentsList.innerHTML = '<div class="subagents-empty">No subagents registered</div>';
    return;
  }

  const html = subagents.map(s => `
    <div class="subagent-card" data-name="${s.name}" data-source="${s.source}">
      <div class="subagent-header">
        <h3 class="subagent-name">${s.name}</h3>
        <span class="subagent-source source-${s.source}">${s.source}</span>
      </div>
      <p class="subagent-description">${s.description}</p>
      <div class="subagent-meta">
        <span class="subagent-tools">${s.tools?.length || 0} tools</span>
        <span class="subagent-tokens">${s.max_tokens} tokens</span>
      </div>
      ${s.source === 'user' ? `<button class="btn btn-sm btn-danger subagent-delete" data-name="${s.name}">Delete</button>` : ''}
    </div>
  `).join('');

  subagentsList.innerHTML = html;

  // Add click handlers for viewing details
  subagentsList.querySelectorAll('.subagent-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (!e.target.classList.contains('subagent-delete')) {
        openSubagentModal(card.dataset.name);
      }
    });
  });

  // Add delete handlers
  subagentsList.querySelectorAll('.subagent-delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm(`Delete subagent "${btn.dataset.name}"?`)) {
        await deleteSubagent(btn.dataset.name);
      }
    });
  });
}

async function openSubagentModal(name) {
  const modal = document.getElementById('subagent-modal');
  const title = document.getElementById('subagent-modal-title');
  const body = document.getElementById('subagent-modal-body');

  try {
    const data = await api(`/subagents/${encodeURIComponent(name)}`);
    if (!data.ok) {
      body.innerHTML = '<div class="error">Failed to load subagent details</div>';
      return;
    }

    title.textContent = data.name;
    body.innerHTML = `
      <div class="subagent-detail">
        <div class="detail-row">
          <label>Source:</label>
          <span class="source-${data.source}">${data.source}</span>
        </div>
        <div class="detail-row">
          <label>Description:</label>
          <p>${data.description}</p>
        </div>
        <div class="detail-row">
          <label>Tools:</label>
          <p>${data.tools?.join(', ') || 'None'}</p>
        </div>
        <div class="detail-row">
          <label>Max Tokens:</label>
          <span>${data.max_tokens}</span>
        </div>
        <div class="detail-row">
          <label>Max Turns:</label>
          <span>${data.max_turns}</span>
        </div>
        <div class="detail-row">
          <label>Thinking Mode:</label>
          <span>${data.thinking_mode}</span>
        </div>
        <div class="detail-row">
          <label>System Prompt:</label>
          <pre class="system-prompt">${data.system_prompt}</pre>
        </div>
      </div>
    `;
    modal.classList.add('active');
  } catch (err) {
    console.error('Failed to load subagent:', err);
  }
}

function openCreateSubagentModal() {
  const modal = document.getElementById('subagent-modal');
  const title = document.getElementById('subagent-modal-title');
  const body = document.getElementById('subagent-modal-body');

  title.textContent = 'Create New Subagent';
  body.innerHTML = `
    <form id="create-subagent-form" class="subagent-form">
      <div class="form-group">
        <label for="subagent-name">Name *</label>
        <input type="text" id="subagent-name" required placeholder="e.g., DEBUGGER">
      </div>
      <div class="form-group">
        <label for="subagent-desc">Description *</label>
        <input type="text" id="subagent-desc" required placeholder="Brief description of what this subagent does">
      </div>
      <div class="form-group">
        <label for="subagent-prompt">System Prompt *</label>
        <textarea id="subagent-prompt" rows="6" required placeholder="You are a specialized..."></textarea>
      </div>
      <div class="form-group">
        <label for="subagent-tools">Tools (comma-separated)</label>
        <input type="text" id="subagent-tools" placeholder="fetch_url, execute">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="subagent-max-tokens">Max Tokens</label>
          <input type="number" id="subagent-max-tokens" value="8000">
        </div>
        <div class="form-group">
          <label for="subagent-max-turns">Max Turns</label>
          <input type="number" id="subagent-max-turns" value="3">
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn" onclick="closeSubagentModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Create</button>
      </div>
    </form>
  `;

  document.getElementById('create-subagent-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await createSubagent();
  });

  modal.classList.add('active');
}

async function createSubagent() {
  const name = document.getElementById('subagent-name').value.trim();
  const description = document.getElementById('subagent-desc').value.trim();
  const systemPrompt = document.getElementById('subagent-prompt').value.trim();
  const toolsStr = document.getElementById('subagent-tools').value.trim();
  const maxTokens = parseInt(document.getElementById('subagent-max-tokens').value) || 8000;
  const maxTurns = parseInt(document.getElementById('subagent-max-turns').value) || 3;

  const tools = toolsStr ? toolsStr.split(',').map(t => t.trim()).filter(t => t) : [];

  try {
    const result = await api('/subagents', {
      method: 'POST',
      body: {
        name,
        description,
        system_prompt: systemPrompt,
        tools,
        max_tokens: maxTokens,
        max_turns: maxTurns,
      }
    });

    if (result.ok !== false) {
      showToast(`Subagent "${name}" created successfully`, 'success', { timeout: 3000 });
      closeSubagentModal();
      loadSubagents();
    } else {
      showToast(result.error || 'Failed to create subagent', 'error');
    }
  } catch (err) {
    showToast('Failed to create subagent: ' + err.message, 'error');
  }
}

async function deleteSubagent(name) {
  try {
    const result = await api(`/subagents/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (result.ok !== false) {
      showToast(`Subagent "${name}" deleted`, 'success', { timeout: 3000 });
      loadSubagents();
    } else {
      showToast(result.error || 'Failed to delete subagent', 'error');
    }
  } catch (err) {
    showToast('Failed to delete subagent: ' + err.message, 'error');
  }
}

function closeSubagentModal() {
  document.getElementById('subagent-modal').classList.remove('active');
}

// Subagents tab event listeners
document.getElementById('refresh-subagents')?.addEventListener('click', loadSubagents);
document.getElementById('add-subagent')?.addEventListener('click', openCreateSubagentModal);
document.getElementById('subagent-modal-close')?.addEventListener('click', closeSubagentModal);

// Initialize
connectWS();
loadDashboard();
loadSkills();
loadSubagents();
loadWorkspace();
loadSessions();
loadMemoryFiles();
loadModelConfig();
checkAgentStatus();

// Add initial activity
addActivityItem({ level: 'info', source: 'Panel', message: 'Control Panel initialized', timestamp: new Date() });

// Refresh dashboard periodically
setInterval(loadDashboard, 10000);
setInterval(checkAgentStatus, 30000); // Check agent status every 30s

