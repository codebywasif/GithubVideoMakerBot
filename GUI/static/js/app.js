/**
 * GitHub Video Maker Bot — SPA Application
 * 
 * Hash-based SPA router with API client, state management,
 * SSE progress streaming, and component rendering.
 */

// ═══════════════════════════════════════════════════════
//   API Client
// ═══════════════════════════════════════════════════════

const API = {
  async get(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`);
    return res.json();
  },

  async post(url, data = {}) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async del(url) {
    const res = await fetch(url, { method: 'DELETE' });
    return res.json();
  },

  async upload(url, formData) {
    const res = await fetch(url, { method: 'POST', body: formData });
    return res.json();
  },
};


// ═══════════════════════════════════════════════════════
//   Toast Notifications
// ═══════════════════════════════════════════════════════

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('fadeout');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}


// ═══════════════════════════════════════════════════════
//   Utility Functions
// ═══════════════════════════════════════════════════════

function timeSince(timestamp) {
  const seconds = Math.floor(Date.now() / 1000 - parseInt(timestamp));
  const intervals = [
    { label: 'year', seconds: 31536000 },
    { label: 'month', seconds: 2592000 },
    { label: 'day', seconds: 86400 },
    { label: 'hour', seconds: 3600 },
    { label: 'minute', seconds: 60 },
    { label: 'second', seconds: 1 },
  ];
  for (const interval of intervals) {
    const count = Math.floor(seconds / interval.seconds);
    if (count >= 1) {
      return `${count} ${interval.label}${count !== 1 ? 's' : ''} ago`;
    }
  }
  return 'just now';
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function wordCount(text) {
  return text.trim().split(/\s+/).filter(w => w.length > 0).length;
}


// ═══════════════════════════════════════════════════════
//   Router
// ═══════════════════════════════════════════════════════

const routes = {
  '/': renderDashboard,
  '/create': renderCreateWizard,
  '/history': renderVideoHistory,
  '/backgrounds': renderBackgrounds,
  '/settings': renderSettings,
};

function navigate(path) {
  window.location.hash = '#' + path;
}

function initRouter() {
  window.addEventListener('hashchange', handleRoute);
  handleRoute();
}

function handleRoute() {
  const hash = window.location.hash.slice(1) || '/';
  const renderFn = routes[hash] || renderDashboard;

  // Update active nav link
  document.querySelectorAll('.nav-link').forEach(link => {
    const href = link.getAttribute('data-route');
    link.classList.toggle('active', href === hash);
  });

  // Render
  const main = document.getElementById('main-content');
  main.innerHTML = '<div class="page-view" id="page-view"></div>';
  renderFn(document.getElementById('page-view'));
}


// ═══════════════════════════════════════════════════════
//   Status Polling
// ═══════════════════════════════════════════════════════

let statusInterval = null;

function startStatusPolling() {
  updateStatusBadge();
  statusInterval = setInterval(updateStatusBadge, 5000);
}

async function updateStatusBadge() {
  try {
    const status = await API.get('/api/status');
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    if (!dot || !text) return;

    const stateLabels = {
      idle: 'Ready',
      fetching: 'Fetching...',
      script_ready: 'Script Ready',
      awaiting_approval: 'Awaiting Approval',
      generating_tts: 'Generating TTS...',
      screenshots: 'Screenshots...',
      background: 'Background...',
      rendering: 'Rendering...',
      complete: 'Complete',
      error: 'Error',
    };

    dot.className = 'status-dot';
    if (['fetching', 'generating_tts', 'screenshots', 'background', 'rendering', 'awaiting_approval', 'script_ready'].includes(status.state)) {
      dot.classList.add('busy');
    } else if (status.state === 'error') {
      dot.classList.add('error');
    }

    text.textContent = stateLabels[status.state] || status.state;
  } catch (e) {
    // ignore
  }
}


// ═══════════════════════════════════════════════════════
//   Page: Dashboard
// ═══════════════════════════════════════════════════════

async function renderDashboard(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1><span class="text-gradient">Dashboard</span></h1>
      <p class="subtitle">Overview of your GitHub Video Maker Bot</p>
    </div>
    <div class="stats-grid" id="dash-stats">
      <div class="card stat-card">
        <div class="stat-icon purple">🎬</div>
        <div class="stat-value" id="stat-total">—</div>
        <div class="stat-label">Videos Created</div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon cyan">📅</div>
        <div class="stat-value" id="stat-last">—</div>
        <div class="stat-label">Last Created</div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon green">💾</div>
        <div class="stat-value" id="stat-size">—</div>
        <div class="stat-label">Total Size</div>
      </div>
      <div class="card stat-card">
        <div class="stat-icon orange">⚡</div>
        <div class="stat-value" id="stat-status">—</div>
        <div class="stat-label">Pipeline Status</div>
      </div>
    </div>

    <div class="flex gap-2 mb-3">
      <button class="btn btn-primary btn-lg" onclick="navigate('/create')">
        ▶ Create New Video
      </button>
      <button class="btn btn-secondary btn-lg" id="btn-trending">
        🔥 Preview Trending Repos
      </button>
    </div>

    <div class="card card-flat mb-3" id="trending-preview" style="display:none">
      <h3 class="mb-2">🔥 Trending Repos Right Now</h3>
      <div id="trending-list"></div>
    </div>

    <h2 class="mb-2">Recent Videos</h2>
    <div class="video-grid" id="recent-videos">
      <div class="empty-state">
        <div class="spinner spinner-lg" style="margin:0 auto"></div>
        <p class="mt-2 text-muted">Loading...</p>
      </div>
    </div>
  `;

  // Load stats
  try {
    const [videos, status] = await Promise.all([
      API.get('/api/videos'),
      API.get('/api/status'),
    ]);

    document.getElementById('stat-total').textContent = videos.length;
    document.getElementById('stat-last').textContent = videos.length > 0
      ? timeSince(videos[0].time)
      : 'Never';
    const totalSize = videos.reduce((sum, v) => sum + (v.file_size || 0), 0);
    document.getElementById('stat-size').textContent = formatBytes(totalSize);

    const stateLabels = {
      idle: 'Idle ✓',
      fetching: 'Running ◌',
      awaiting_approval: 'Needs Input ⚠',
      generating_tts: 'Running ◌',
      screenshots: 'Running ◌',
      background: 'Running ◌',
      rendering: 'Running ◌',
      complete: 'Complete ✓',
      error: 'Error ✕',
    };
    document.getElementById('stat-status').textContent = stateLabels[status.state] || status.state;

    // Render recent videos
    const recentContainer = document.getElementById('recent-videos');
    if (videos.length === 0) {
      recentContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1/-1">
          <div class="empty-icon">🎬</div>
          <div class="empty-title">No videos yet</div>
          <div class="empty-desc">Create your first video to see it here!</div>
          <button class="btn btn-primary" onclick="navigate('/create')">Create Video</button>
        </div>
      `;
    } else {
      recentContainer.innerHTML = videos.slice(0, 6).map(v => renderVideoCard(v)).join('');
    }
  } catch (e) {
    showToast('Failed to load dashboard data', 'error');
  }

  // Trending preview
  document.getElementById('btn-trending').addEventListener('click', async () => {
    const panel = document.getElementById('trending-preview');
    const list = document.getElementById('trending-list');
    if (panel.style.display !== 'none') {
      panel.style.display = 'none';
      return;
    }
    panel.style.display = 'block';
    list.innerHTML = '<div class="flex items-center gap-1"><div class="spinner"></div> Fetching trending repos...</div>';

    try {
      const repos = await API.get('/api/trending');
      if (repos.length === 0) {
        list.innerHTML = '<p class="text-muted">No trending repos found.</p>';
        return;
      }
      list.innerHTML = repos.slice(0, 10).map((r, i) => `
        <div class="flex items-center justify-between" style="padding:0.6rem 0; border-bottom:1px solid var(--border-subtle)">
          <div>
            <span class="text-muted mono" style="margin-right:0.5rem">#${i + 1}</span>
            <a href="${escapeHtml(r.url)}" target="_blank" style="color:var(--text-accent);text-decoration:none;font-weight:600">${escapeHtml(r.full_name)}</a>
            <span class="text-muted" style="margin-left:0.5rem">— ${escapeHtml(r.description || '').slice(0, 80)}</span>
          </div>
          <div class="flex items-center gap-1">
            <span class="badge badge-purple">⭐ ${(r.stars || 0).toLocaleString()}</span>
            ${r.language ? `<span class="badge badge-cyan">${escapeHtml(r.language)}</span>` : ''}
          </div>
        </div>
      `).join('');
    } catch (e) {
      list.innerHTML = '<p class="text-danger">Failed to fetch trending repos.</p>';
    }
  });
}


// ═══════════════════════════════════════════════════════
//   Video Card Component
// ═══════════════════════════════════════════════════════

function renderVideoCard(video) {
  const title = video.video_title || video.filename || 'Untitled';
  const displayTitle = title.length > 80 ? title.slice(0, 80) + '…' : title;

  return `
    <div class="card video-card">
      <div class="video-card-header">
        <div class="video-title">${escapeHtml(displayTitle)}</div>
        <div class="video-meta">
          <span>📅 ${timeSince(video.time)}</span>
          <span>💾 ${video.file_size_mb || 0} MB</span>
          ${video.background_credit ? `<span>🎮 ${escapeHtml(video.background_credit)}</span>` : ''}
        </div>
      </div>
      <div class="video-card-actions">
        <a href="/api/videos/${encodeURIComponent(video.filename)}" 
           download class="btn btn-primary btn-sm" ${!video.exists ? 'style="opacity:0.4;pointer-events:none"' : ''}>
          ⬇ Download
        </a>
        <button class="btn btn-secondary btn-sm" onclick="redoVideo('${escapeHtml(video.id)}')">
          🔄 Redo
        </button>
        <button class="btn btn-ghost btn-sm text-danger" onclick="deleteVideo('${escapeHtml(video.id)}')">
          🗑 Delete
        </button>
      </div>
    </div>
  `;
}

async function deleteVideo(id) {
  if (!confirm('Are you sure you want to delete this video?')) return;
  try {
    const res = await API.del(`/api/videos/${id}`);
    if (res.ok) {
      showToast('Video deleted', 'success');
      handleRoute(); // Refresh current page
    } else {
      showToast(res.error || 'Failed to delete', 'error');
    }
  } catch (e) {
    showToast('Failed to delete video', 'error');
  }
}

async function redoVideo(id) {
  if (!confirm('This will delete the old video and create a new one. Continue?')) return;
  try {
    const res = await API.post(`/api/videos/${id}/redo`);
    if (res.ok) {
      showToast('Redo started! Redirecting to creation wizard...', 'success');
      navigate('/create');
    } else {
      showToast(res.error || 'Failed to start redo', 'error');
    }
  } catch (e) {
    showToast('Failed to start redo', 'error');
  }
}


// ═══════════════════════════════════════════════════════
//   Page: Create Video Wizard
// ═══════════════════════════════════════════════════════

let sseSource = null;

async function renderCreateWizard(container) {
  // Check current state first
  let status;
  try {
    status = await API.get('/api/status');
  } catch (e) {
    status = { state: 'idle' };
  }

  container.innerHTML = `
    <div class="page-header">
      <h1><span class="text-gradient">Create Video</span></h1>
      <p class="subtitle">Generate a new short-form video about a trending GitHub repo</p>
    </div>

    <div class="wizard-steps" id="wizard-steps">
      <div class="wizard-step active" data-step="1">
        <span class="step-number">1</span>
        <span class="step-label">Start</span>
      </div>
      <div class="wizard-step" data-step="2">
        <span class="step-number">2</span>
        <span class="step-label">Script</span>
      </div>
      <div class="wizard-step" data-step="3">
        <span class="step-number">3</span>
        <span class="step-label">Render</span>
      </div>
      <div class="wizard-step" data-step="4">
        <span class="step-number">4</span>
        <span class="step-label">Done</span>
      </div>
    </div>

    <div id="wizard-content"></div>
  `;

  // Determine which step to show based on current state
  if (status.state === 'awaiting_approval') {
    setWizardStep(2);
    renderScriptApprovalStep(status);
  } else if (['generating_tts', 'screenshots', 'background', 'rendering'].includes(status.state)) {
    setWizardStep(3);
    renderRenderingStep(status);
  } else if (status.state === 'complete') {
    setWizardStep(4);
    renderCompleteStep(status);
  } else if (status.state === 'fetching' || status.state === 'script_ready') {
    setWizardStep(1);
    renderFetchingState(status);
  } else {
    renderStartStep();
  }
}

function setWizardStep(activeStep) {
  document.querySelectorAll('.wizard-step').forEach(el => {
    const step = parseInt(el.dataset.step);
    el.classList.remove('active', 'completed');
    if (step < activeStep) el.classList.add('completed');
    if (step === activeStep) el.classList.add('active');
  });
}

function renderStartStep() {
  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div class="card card-flat" style="max-width:700px">
      <h2 class="mb-2">Ready to create a new video?</h2>
      <p class="text-secondary mb-3">
        The bot will fetch trending GitHub repos, select one that hasn't been processed yet,
        generate a narration script using AI, and then create a short-form video.
      </p>
      
      <div class="mb-3">
        <p class="text-muted" style="font-size:0.85rem">
          ℹ You'll get a chance to review and edit the generated script before the video is rendered.
        </p>
      </div>

      <button class="btn btn-primary btn-lg" id="btn-start-creation">
        🚀 Start Video Creation
      </button>
    </div>
  `;

  document.getElementById('btn-start-creation').addEventListener('click', startCreation);
}

async function startCreation() {
  const btn = document.getElementById('btn-start-creation');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px"></div> Starting...';

  try {
    const res = await API.post('/api/create');
    if (!res.ok) {
      showToast(res.error || 'Failed to start', 'error');
      btn.disabled = false;
      btn.innerHTML = '🚀 Start Video Creation';
      return;
    }

    showToast('Video creation started!', 'success');
    renderFetchingState({ state: 'fetching', progress: 0, message: 'Starting...' });
    connectSSE();
  } catch (e) {
    showToast('Failed to start creation', 'error');
    btn.disabled = false;
    btn.innerHTML = '🚀 Start Video Creation';
  }
}

function renderFetchingState(status) {
  setWizardStep(1);
  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div class="card card-flat" style="max-width:700px">
      <div class="flex items-center gap-2 mb-2">
        <div class="spinner"></div>
        <h2>Processing...</h2>
      </div>
      <div class="progress-label">
        <span class="progress-text" id="progress-msg">${escapeHtml(status.message || 'Working...')}</span>
        <span class="progress-percent" id="progress-pct">${status.progress || 0}%</span>
      </div>
      <div class="progress-bar-container">
        <div class="progress-bar-fill" id="progress-bar" style="width:${status.progress || 0}%"></div>
      </div>
    </div>
  `;

  if (!sseSource) connectSSE();
}

function connectSSE() {
  if (sseSource) {
    sseSource.close();
  }

  sseSource = new EventSource('/api/progress');

  sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleProgressUpdate(data);
    } catch (e) {
      // Ignore parse errors
    }
  };

  sseSource.onerror = () => {
    // Reconnect after delay
    setTimeout(() => {
      if (sseSource) {
        sseSource.close();
        sseSource = null;
      }
    }, 5000);
  };
}

function handleProgressUpdate(data) {
  // Update progress elements if they exist
  const bar = document.getElementById('progress-bar');
  const msg = document.getElementById('progress-msg');
  const pct = document.getElementById('progress-pct');

  if (bar) bar.style.width = (data.progress || 0) + '%';
  if (msg) msg.textContent = data.message || '';
  if (pct) pct.textContent = (data.progress || 0) + '%';

  updateStatusBadge();

  // Handle state transitions
  if (data.state === 'awaiting_approval') {
    if (sseSource) { sseSource.close(); sseSource = null; }
    setWizardStep(2);
    renderScriptApprovalStep(data);
  } else if (['generating_tts', 'screenshots', 'background', 'rendering'].includes(data.state)) {
    setWizardStep(3);
    // Only re-render if we're not already on this step
    if (!document.getElementById('render-progress-bar')) {
      renderRenderingStep(data);
    } else {
      // Just update progress
      const rBar = document.getElementById('render-progress-bar');
      const rMsg = document.getElementById('render-progress-msg');
      const rPct = document.getElementById('render-progress-pct');
      if (rBar) rBar.style.width = data.progress + '%';
      if (rMsg) rMsg.textContent = data.message || '';
      if (rPct) rPct.textContent = data.progress + '%';

      // Update step indicators
      const stageMap = {
        generating_tts: 0,
        screenshots: 1,
        background: 2,
        rendering: 3,
      };
      const currentStage = stageMap[data.state] ?? -1;
      document.querySelectorAll('.render-stage').forEach((el, i) => {
        el.classList.toggle('stage-active', i === currentStage);
        el.classList.toggle('stage-done', i < currentStage);
      });
    }
  } else if (data.state === 'complete') {
    if (sseSource) { sseSource.close(); sseSource = null; }
    setWizardStep(4);
    renderCompleteStep(data);
  } else if (data.state === 'error') {
    if (sseSource) { sseSource.close(); sseSource = null; }
    renderErrorState(data);
  }
}

async function renderScriptApprovalStep(status) {
  // Fetch full pending script data
  let scriptData;
  try {
    scriptData = await API.get('/api/script/pending');
  } catch (e) {
    scriptData = { script: status.script || '', repo: status.repo || {}, segments: status.segments || [] };
  }

  const script = scriptData.script || status.script || '';
  const repo = scriptData.repo || status.repo || {};

  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div style="display:grid; grid-template-columns:1fr 340px; gap:1.5rem; align-items:start">
      <div>
        <div class="card card-flat">
          <h2 class="mb-2">📝 Review Generated Script</h2>
          <p class="text-secondary mb-2">
            Edit the script below if needed, then approve to continue with video creation.
          </p>
          
          <div class="script-editor">
            <textarea class="script-textarea" id="script-textarea">${escapeHtml(script)}</textarea>
            <div class="script-meta">
              <span>Edit freely — changes will be used for the narration</span>
              <span class="word-count" id="word-count">${wordCount(script)} words</span>
            </div>
          </div>

          <div class="flex gap-1 mt-3">
            <button class="btn btn-success btn-lg" id="btn-approve">
              ✓ Approve & Continue
            </button>
            <button class="btn btn-secondary" id="btn-regenerate">
              🔄 Regenerate Script
            </button>
          </div>
        </div>
      </div>

      <div>
        <div class="repo-panel">
          <div class="repo-name">
            📦 ${escapeHtml(repo.full_name || 'Unknown Repo')}
          </div>
          <div class="repo-desc">${escapeHtml(repo.description || 'No description')}</div>
          <div class="repo-stats">
            <div class="repo-stat">⭐ <span class="stat-val">${(repo.stars || 0).toLocaleString()}</span></div>
            ${repo.language ? `<div class="repo-stat">💻 <span class="stat-val">${escapeHtml(repo.language)}</span></div>` : ''}
          </div>
          ${repo.url ? `<a href="${escapeHtml(repo.url)}" target="_blank" class="btn btn-ghost btn-sm mt-2" style="color:var(--text-accent)">View on GitHub →</a>` : ''}
        </div>
      </div>
    </div>
  `;

  // Word count updater
  const textarea = document.getElementById('script-textarea');
  const wcEl = document.getElementById('word-count');
  textarea.addEventListener('input', () => {
    wcEl.textContent = wordCount(textarea.value) + ' words';
  });

  // Approve
  document.getElementById('btn-approve').addEventListener('click', async () => {
    const btn = document.getElementById('btn-approve');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px"></div> Approving...';

    try {
      const editedScript = textarea.value;
      const res = await API.post('/api/script/approve', { script: editedScript });
      if (res.ok) {
        showToast('Script approved! Rendering video...', 'success');
        setWizardStep(3);
        renderRenderingStep({ state: 'generating_tts', progress: 30, message: 'Converting script to speech...' });
        connectSSE();
      } else {
        showToast(res.error || 'Failed to approve', 'error');
        btn.disabled = false;
        btn.innerHTML = '✓ Approve & Continue';
      }
    } catch (e) {
      showToast('Failed to approve script', 'error');
      btn.disabled = false;
      btn.innerHTML = '✓ Approve & Continue';
    }
  });

  // Regenerate
  document.getElementById('btn-regenerate').addEventListener('click', async () => {
    const btn = document.getElementById('btn-regenerate');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px"></div> Regenerating...';

    try {
      const res = await API.post('/api/script/reject');
      if (res.ok) {
        showToast('Regenerating script...', 'info');
        // Wait for new script, reconnect SSE
        connectSSE();
      } else {
        showToast(res.error || 'Failed to regenerate', 'error');
      }
    } catch (e) {
      showToast('Failed to regenerate', 'error');
    }
    btn.disabled = false;
    btn.innerHTML = '🔄 Regenerate Script';
  });
}

function renderRenderingStep(data) {
  const content = document.getElementById('wizard-content');

  const stages = ['TTS Audio', 'Screenshots', 'Background', 'Final Render'];
  const stageMap = {
    generating_tts: 0,
    screenshots: 1,
    background: 2,
    rendering: 3,
  };
  const currentStage = stageMap[data.state] ?? 0;

  content.innerHTML = `
    <div class="card card-flat" style="max-width:700px">
      <h2 class="mb-2">🎬 Rendering Video</h2>
      <p class="text-secondary mb-3">Your video is being created. This usually takes a few minutes.</p>

      <div class="progress-label">
        <span class="progress-text" id="render-progress-msg">${escapeHtml(data.message || 'Processing...')}</span>
        <span class="progress-percent" id="render-progress-pct">${data.progress || 30}%</span>
      </div>
      <div class="progress-bar-container">
        <div class="progress-bar-fill" id="render-progress-bar" style="width:${data.progress || 30}%"></div>
      </div>

      <div class="flex gap-2 mt-3">
        ${stages.map((label, i) => `
          <div class="badge render-stage ${i === currentStage ? 'badge-purple stage-active' : i < currentStage ? 'badge-green stage-done' : 'badge-cyan'}" 
               style="padding:0.4rem 0.8rem; font-size:0.8rem">
            ${i < currentStage ? '✓' : i === currentStage ? '◌' : '○'} ${label}
          </div>
        `).join('')}
      </div>
    </div>
  `;

  if (!sseSource) connectSSE();
}

function renderCompleteStep(data) {
  const content = document.getElementById('wizard-content');
  const filename = data.result_filename || '';

  content.innerHTML = `
    <div class="card card-flat" style="max-width:700px; text-align:center">
      <div style="font-size:4rem; margin-bottom:1rem">🎉</div>
      <h2 class="mb-1">Video Created Successfully!</h2>
      <p class="text-secondary mb-3">${escapeHtml(data.message || 'Your video is ready to download.')}</p>

      ${filename ? `
        <div class="flex gap-1" style="justify-content:center">
          <a href="/api/videos/${encodeURIComponent(filename)}" download class="btn btn-primary btn-lg">
            ⬇ Download Video
          </a>
          <button class="btn btn-secondary btn-lg" onclick="navigate('/history')">
            📚 View Library
          </button>
        </div>
        <p class="text-muted mt-2" style="font-size:0.82rem">File: ${escapeHtml(filename)}</p>
      ` : `
        <div class="flex gap-1" style="justify-content:center">
          <button class="btn btn-secondary btn-lg" onclick="navigate('/history')">
            📚 View Library
          </button>
        </div>
      `}

      <div class="divider"></div>
      <button class="btn btn-primary" onclick="navigate('/create'); setTimeout(renderStartStep, 100)">
        ▶ Create Another Video
      </button>
    </div>
  `;
}

function renderErrorState(data) {
  const content = document.getElementById('wizard-content');
  content.innerHTML = `
    <div class="card card-flat" style="max-width:700px; text-align:center">
      <div style="font-size:3rem; margin-bottom:1rem">❌</div>
      <h2 class="mb-1 text-danger">Something went wrong</h2>
      <p class="text-secondary mb-2">${escapeHtml(data.error || data.message || 'An error occurred during video creation.')}</p>
      <button class="btn btn-primary" onclick="renderStartStep()">
        🔄 Try Again
      </button>
    </div>
  `;
}


// ═══════════════════════════════════════════════════════
//   Page: Video History
// ═══════════════════════════════════════════════════════

async function renderVideoHistory(container) {
  container.innerHTML = `
    <div class="page-header flex justify-between items-center">
      <div>
        <h1><span class="text-gradient">Video Library</span></h1>
        <p class="subtitle">All your generated videos</p>
      </div>
      <button class="btn btn-primary" onclick="navigate('/create')">▶ Create New</button>
    </div>

    <div class="flex justify-between items-center mb-2">
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input class="form-input" type="text" placeholder="Search videos..." id="video-search">
      </div>
      <div class="btn-group">
        <button class="btn btn-ghost btn-sm active" id="sort-date" onclick="sortVideos('date')">📅 Date</button>
        <button class="btn btn-ghost btn-sm" id="sort-name" onclick="sortVideos('name')">🔤 Name</button>
        <button class="btn btn-ghost btn-sm" id="sort-size" onclick="sortVideos('size')">💾 Size</button>
      </div>
    </div>

    <div class="video-grid" id="video-list">
      <div class="empty-state" style="grid-column:1/-1">
        <div class="spinner spinner-lg" style="margin:0 auto"></div>
        <p class="mt-2 text-muted">Loading videos...</p>
      </div>
    </div>
  `;

  let allVideos = [];
  let sortBy = 'date';

  try {
    allVideos = await API.get('/api/videos');
    renderVideoList(allVideos);
  } catch (e) {
    document.getElementById('video-list').innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Failed to load videos</div>
      </div>
    `;
  }

  // Search
  document.getElementById('video-search').addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = allVideos.filter(v =>
      (v.video_title || v.filename || '').toLowerCase().includes(q) ||
      (v.id || '').toLowerCase().includes(q)
    );
    renderVideoList(filtered);
  });

  // Sort (attach to window for onclick)
  window.sortVideos = (by) => {
    sortBy = by;
    document.querySelectorAll('.btn-group .btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`sort-${by}`)?.classList.add('active');

    const sorted = [...allVideos];
    if (by === 'date') sorted.sort((a, b) => parseInt(b.time) - parseInt(a.time));
    else if (by === 'name') sorted.sort((a, b) => (a.video_title || '').localeCompare(b.video_title || ''));
    else if (by === 'size') sorted.sort((a, b) => (b.file_size || 0) - (a.file_size || 0));
    renderVideoList(sorted);
  };

  function renderVideoList(videos) {
    const el = document.getElementById('video-list');
    if (videos.length === 0) {
      el.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1">
          <div class="empty-icon">📭</div>
          <div class="empty-title">No videos found</div>
          <div class="empty-desc">Try adjusting your search or create a new video.</div>
        </div>
      `;
      return;
    }
    el.innerHTML = videos.map(v => renderVideoCard(v)).join('');
  }
}


// ═══════════════════════════════════════════════════════
//   Page: Backgrounds
// ═══════════════════════════════════════════════════════

async function renderBackgrounds(container) {
  container.innerHTML = `
    <div class="page-header">
      <h1><span class="text-gradient">Backgrounds</span></h1>
      <p class="subtitle">Manage background videos, audio, and custom uploads</p>
    </div>

    <!-- Upload Zone -->
    <div class="card card-flat mb-3">
      <h3 class="mb-2">📤 Upload Custom Background</h3>
      <div class="upload-zone" id="upload-zone">
        <div class="upload-icon">📁</div>
        <div class="upload-text">Drag & drop a video or image here, or click to browse</div>
        <div class="upload-hint">Supports: MP4, WebM, AVI, MOV, MKV, JPG, PNG, GIF (max 500MB)</div>
        <input type="file" id="upload-input" style="display:none" accept=".mp4,.webm,.avi,.mov,.mkv,.jpg,.jpeg,.png,.gif,.webp">
      </div>
      <div id="upload-status" class="mt-1"></div>
    </div>

    <!-- Custom Uploads -->
    <div class="card card-flat mb-3" id="custom-section" style="display:none">
      <h3 class="mb-2">🎨 Custom Uploads</h3>
      <div class="bg-grid" id="custom-bg-list"></div>
    </div>

    <!-- Video Backgrounds -->
    <div class="card card-flat mb-3">
      <h3 class="mb-2">🎮 Background Videos</h3>
      <div class="bg-grid" id="bg-videos-list">
        <div class="flex items-center gap-1"><div class="spinner"></div> Loading...</div>
      </div>
    </div>

    <!-- Audio Backgrounds -->
    <div class="card card-flat">
      <h3 class="mb-2">🎵 Background Audio</h3>
      <div class="bg-grid" id="bg-audios-list">
        <div class="flex items-center gap-1"><div class="spinner"></div> Loading...</div>
      </div>
    </div>
  `;

  // Upload handlers
  const zone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('upload-input');

  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragover');
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) uploadFile(fileInput.files[0]);
  });

  async function uploadFile(file) {
    const statusEl = document.getElementById('upload-status');
    statusEl.innerHTML = `<div class="flex items-center gap-1"><div class="spinner"></div> Uploading ${escapeHtml(file.name)}...</div>`;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await API.upload('/api/backgrounds/upload', formData);
      if (res.ok) {
        showToast(`Uploaded ${res.filename}`, 'success');
        statusEl.innerHTML = `<span class="text-success">✓ Uploaded ${escapeHtml(res.filename)}</span>`;
        loadCustomBackgrounds();
      } else {
        statusEl.innerHTML = `<span class="text-danger">✕ ${escapeHtml(res.error)}</span>`;
      }
    } catch (e) {
      statusEl.innerHTML = '<span class="text-danger">✕ Upload failed</span>';
    }
  }

  // Load backgrounds
  try {
    const videos = await API.get('/api/backgrounds/videos');
    const list = document.getElementById('bg-videos-list');
    if (videos.length === 0) {
      list.innerHTML = '<p class="text-muted">No background videos configured.</p>';
    } else {
      list.innerHTML = videos.map(bg => `
        <div class="card bg-card">
          <div class="bg-icon video">🎮</div>
          <div class="bg-info">
            <div class="bg-name">${escapeHtml(bg.key)}</div>
            <div class="bg-credit">by ${escapeHtml(bg.credit)}</div>
          </div>
          <button class="btn btn-ghost btn-sm text-danger" onclick="deleteBackground('${escapeHtml(bg.key)}')">🗑</button>
        </div>
      `).join('');
    }
  } catch (e) {
    document.getElementById('bg-videos-list').innerHTML = '<p class="text-danger">Failed to load.</p>';
  }

  try {
    const audios = await API.get('/api/backgrounds/audios');
    const list = document.getElementById('bg-audios-list');
    if (audios.length === 0) {
      list.innerHTML = '<p class="text-muted">No background audio configured.</p>';
    } else {
      list.innerHTML = audios.map(bg => `
        <div class="card bg-card">
          <div class="bg-icon audio">🎵</div>
          <div class="bg-info">
            <div class="bg-name">${escapeHtml(bg.key)}</div>
            <div class="bg-credit">by ${escapeHtml(bg.credit)}</div>
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    document.getElementById('bg-audios-list').innerHTML = '<p class="text-danger">Failed to load.</p>';
  }

  loadCustomBackgrounds();
}

async function loadCustomBackgrounds() {
  try {
    const files = await API.get('/api/backgrounds/custom');
    const section = document.getElementById('custom-section');
    const list = document.getElementById('custom-bg-list');
    if (!section || !list) return;

    if (files.length > 0) {
      section.style.display = 'block';
      list.innerHTML = files.map(f => `
        <div class="card bg-card">
          <div class="bg-icon ${f.is_video ? 'video' : 'audio'}">${f.is_video ? '🎬' : '🖼️'}</div>
          <div class="bg-info">
            <div class="bg-name">${escapeHtml(f.filename)}</div>
            <div class="bg-credit">${f.size_mb} MB • ${escapeHtml(f.ext)}</div>
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    // ignore
  }
}

async function deleteBackground(key) {
  if (!confirm(`Delete background "${key}"?`)) return;
  try {
    const res = await API.del(`/api/backgrounds/${key}`);
    if (res.ok) {
      showToast(`Deleted "${key}"`, 'success');
      handleRoute();
    } else {
      showToast(res.error || 'Failed to delete', 'error');
    }
  } catch (e) {
    showToast('Failed to delete background', 'error');
  }
}


// ═══════════════════════════════════════════════════════
//   Page: Settings
// ═══════════════════════════════════════════════════════

async function renderSettings(container) {
  container.innerHTML = `
    <div class="page-header flex justify-between items-center">
      <div>
        <h1><span class="text-gradient">Settings</span></h1>
        <p class="subtitle">Configure your video creation pipeline</p>
      </div>
      <button class="btn btn-primary" id="btn-save-settings">💾 Save Settings</button>
    </div>

    <div id="settings-form">
      <div class="flex items-center gap-1 mb-3">
        <div class="spinner"></div>
        <span class="text-muted">Loading settings...</span>
      </div>
    </div>
  `;

  let config;
  try {
    config = await API.get('/api/settings?reveal=true');
  } catch (e) {
    document.getElementById('settings-form').innerHTML = '<p class="text-danger">Failed to load settings.</p>';
    return;
  }

  const form = document.getElementById('settings-form');
  form.innerHTML = `
    <!-- GitHub Section -->
    <div class="settings-section">
      <div class="section-title">🐙 GitHub Settings</div>
      <div class="settings-grid">
        <div class="form-group">
          <label class="form-label">Trending Language</label>
          <input class="form-input" type="text" id="set-github-trending_language" 
                 value="${escapeHtml(config.github?.trending_language || '')}" placeholder="e.g. python (empty for all)">
          <div class="form-hint">Filter trending repos by language. Leave empty for all.</div>
        </div>
        <div class="form-group">
          <label class="form-label">Trending Since</label>
          <select class="form-select" id="set-github-trending_since">
            <option value="daily" ${config.github?.trending_since === 'daily' ? 'selected' : ''}>Daily</option>
            <option value="weekly" ${config.github?.trending_since === 'weekly' ? 'selected' : ''}>Weekly</option>
            <option value="monthly" ${config.github?.trending_since === 'monthly' ? 'selected' : ''}>Monthly</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Minimum Stars</label>
          <input class="form-input" type="number" id="set-github-min_stars" value="${config.github?.min_stars || 100}">
        </div>
        <div class="form-group">
          <label class="form-label">Repos Per Run</label>
          <input class="form-input" type="number" id="set-github-repos_per_run" value="${config.github?.repos_per_run || 1}" min="1" max="10">
        </div>
        <div class="form-group">
          <label class="form-label">GitHub Token</label>
          <div class="input-reveal-wrapper">
            <input class="form-input" type="password" id="set-github-api-token" 
                   value="${escapeHtml(config.github?.api?.token || '')}">
            <button class="input-reveal-btn" type="button" onclick="toggleReveal(this)">👁</button>
          </div>
          <div class="form-hint">Optional PAT for higher API rate limits</div>
        </div>
      </div>
    </div>

    <!-- Script Section -->
    <div class="settings-section">
      <div class="section-title">✍️ Script Generation</div>
      <div class="settings-grid">
        <div class="form-group">
          <label class="form-label">Provider</label>
          <select class="form-select" id="set-script-provider">
            <option value="openai" ${config.script?.provider === 'openai' ? 'selected' : ''}>OpenAI</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">OpenAI API Key</label>
          <div class="input-reveal-wrapper">
            <input class="form-input" type="password" id="set-script-openai_api_key" 
                   value="${escapeHtml(config.script?.openai_api_key || '')}">
            <button class="input-reveal-btn" type="button" onclick="toggleReveal(this)">👁</button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">OpenAI Model</label>
          <input class="form-input" type="text" id="set-script-openai_model" 
                 value="${escapeHtml(config.script?.openai_model || 'gpt-4o-mini')}">
        </div>
        <div class="form-group">
          <label class="form-label">Max Script Words</label>
          <input class="form-input" type="number" id="set-script-max_script_words" 
                 value="${config.script?.max_script_words || 75}" min="30" max="500">
        </div>
        <div class="form-group" style="grid-column: 1 / -1">
          <label class="form-label">Custom Prompt</label>
          <textarea class="form-textarea" id="set-script-custom_prompt" rows="3"
                    placeholder="Leave empty to use the default prompt">${escapeHtml(config.script?.custom_prompt || '')}</textarea>
        </div>
      </div>
    </div>

    <!-- Video Settings -->
    <div class="settings-section">
      <div class="section-title">🎬 Video Settings</div>
      <div class="settings-grid">
        <div class="form-group">
          <label class="form-label">Channel Name</label>
          <input class="form-input" type="text" id="set-settings-channel_name" 
                 value="${escapeHtml(config.settings?.channel_name || '')}">
        </div>
        <div class="form-group">
          <label class="form-label">Resolution Width</label>
          <input class="form-input" type="number" id="set-settings-resolution_w" 
                 value="${config.settings?.resolution_w || 1080}">
        </div>
        <div class="form-group">
          <label class="form-label">Resolution Height</label>
          <input class="form-input" type="number" id="set-settings-resolution_h" 
                 value="${config.settings?.resolution_h || 1920}">
        </div>
        <div class="form-group">
          <label class="form-label">Opacity</label>
          <input class="form-input" type="number" id="set-settings-opacity" 
                 value="${config.settings?.opacity || 0.9}" min="0" max="1" step="0.1">
        </div>
        <div class="form-group">
          <label class="form-label">Zoom</label>
          <input class="form-input" type="number" id="set-settings-zoom" 
                 value="${config.settings?.zoom || 1.0}" min="0.5" max="3" step="0.1">
        </div>
        <div class="form-group">
          <label class="form-label">Theme</label>
          <select class="form-select" id="set-settings-theme">
            <option value="dark" ${config.settings?.theme === 'dark' ? 'selected' : ''}>Dark</option>
            <option value="light" ${config.settings?.theme === 'light' ? 'selected' : ''}>Light</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Times to Run</label>
          <input class="form-input" type="number" id="set-settings-times_to_run" 
                 value="${config.settings?.times_to_run || 1}" min="1">
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <input type="checkbox" class="toggle" id="set-settings-storymode" 
                   ${config.settings?.storymode !== false ? 'checked' : ''}>
            <label class="form-label" for="set-settings-storymode" style="margin-bottom:0">Story Mode</label>
          </div>
        </div>
      </div>
    </div>

    <!-- Background Settings -->
    <div class="settings-section">
      <div class="section-title">🎨 Background Settings</div>
      <div class="settings-grid">
        <div class="form-group">
          <label class="form-label">Background Video</label>
          <input class="form-input" type="text" id="set-settings-background-background_video" 
                 value="${escapeHtml(config.settings?.background?.background_video || 'minecraft')}">
        </div>
        <div class="form-group">
          <label class="form-label">Background Audio</label>
          <input class="form-input" type="text" id="set-settings-background-background_audio" 
                 value="${escapeHtml(config.settings?.background?.background_audio || 'lofi')}">
        </div>
        <div class="form-group">
          <label class="form-label">Audio Volume</label>
          <input class="form-input" type="number" id="set-settings-background-background_audio_volume" 
                 value="${config.settings?.background?.background_audio_volume || 0.4}" min="0" max="1" step="0.1">
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <input type="checkbox" class="toggle" id="set-settings-background-enable_extra_audio" 
                   ${config.settings?.background?.enable_extra_audio ? 'checked' : ''}>
            <label class="form-label" for="set-settings-background-enable_extra_audio" style="margin-bottom:0">Enable Extra Audio</label>
          </div>
        </div>
      </div>
    </div>

    <!-- TTS Settings -->
    <div class="settings-section">
      <div class="section-title">🔊 Text-to-Speech Settings</div>
      <div class="settings-grid">
        <div class="form-group">
          <label class="form-label">Voice Choice</label>
          <select class="form-select" id="set-settings-tts-voice_choice">
            ${['googletranslate', 'tiktok', 'pyttsx', 'elevenlabs', 'awspolly', 'streamlabspolly', 'openai'].map(v =>
              `<option value="${v}" ${(config.settings?.tts?.voice_choice || '').toLowerCase() === v ? 'selected' : ''}>${v}</option>`
            ).join('')}
          </select>
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <input type="checkbox" class="toggle" id="set-settings-tts-random_voice" 
                   ${config.settings?.tts?.random_voice ? 'checked' : ''}>
            <label class="form-label" for="set-settings-tts-random_voice" style="margin-bottom:0">Random Voice</label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">ElevenLabs Voice Name</label>
          <input class="form-input" type="text" id="set-settings-tts-elevenlabs_voice_name" 
                 value="${escapeHtml(config.settings?.tts?.elevenlabs_voice_name || 'Bella')}">
        </div>
        <div class="form-group">
          <label class="form-label">ElevenLabs API Key</label>
          <div class="input-reveal-wrapper">
            <input class="form-input" type="password" id="set-settings-tts-elevenlabs_api_key" 
                   value="${escapeHtml(config.settings?.tts?.elevenlabs_api_key || '')}">
            <button class="input-reveal-btn" type="button" onclick="toggleReveal(this)">👁</button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">TikTok Voice</label>
          <input class="form-input" type="text" id="set-settings-tts-tiktok_voice" 
                 value="${escapeHtml(config.settings?.tts?.tiktok_voice || 'en_us_001')}">
        </div>
        <div class="form-group">
          <label class="form-label">TikTok Session ID</label>
          <div class="input-reveal-wrapper">
            <input class="form-input" type="password" id="set-settings-tts-tiktok_sessionid" 
                   value="${escapeHtml(config.settings?.tts?.tiktok_sessionid || '')}">
            <button class="input-reveal-btn" type="button" onclick="toggleReveal(this)">👁</button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Silence Duration</label>
          <input class="form-input" type="number" id="set-settings-tts-silence_duration" 
                 value="${config.settings?.tts?.silence_duration || 0.3}" min="0" max="2" step="0.1">
        </div>
        <div class="form-group">
          <div class="toggle-wrapper">
            <input type="checkbox" class="toggle" id="set-settings-tts-no_emojis" 
                   ${config.settings?.tts?.no_emojis !== false ? 'checked' : ''}>
            <label class="form-label" for="set-settings-tts-no_emojis" style="margin-bottom:0">Strip Emojis</label>
          </div>
        </div>
      </div>
    </div>
  `;

  // Save handler
  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
}

function toggleReveal(btn) {
  const input = btn.parentElement.querySelector('input');
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
}

async function saveSettings() {
  const btn = document.getElementById('btn-save-settings');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px"></div> Saving...';

  // Build config object from form
  const getValue = (id) => {
    const el = document.getElementById(id);
    if (!el) return undefined;
    if (el.type === 'checkbox') return el.checked;
    if (el.type === 'number') return parseFloat(el.value) || 0;
    return el.value;
  };

  const config = {
    github: {
      trending_language: getValue('set-github-trending_language'),
      trending_since: getValue('set-github-trending_since'),
      min_stars: getValue('set-github-min_stars'),
      repos_per_run: getValue('set-github-repos_per_run'),
      api: {
        token: getValue('set-github-api-token'),
      },
    },
    script: {
      provider: getValue('set-script-provider'),
      openai_api_key: getValue('set-script-openai_api_key'),
      openai_model: getValue('set-script-openai_model'),
      max_script_words: getValue('set-script-max_script_words'),
      custom_prompt: getValue('set-script-custom_prompt'),
    },
    settings: {
      channel_name: getValue('set-settings-channel_name'),
      resolution_w: getValue('set-settings-resolution_w'),
      resolution_h: getValue('set-settings-resolution_h'),
      opacity: getValue('set-settings-opacity'),
      zoom: getValue('set-settings-zoom'),
      theme: getValue('set-settings-theme'),
      times_to_run: getValue('set-settings-times_to_run'),
      storymode: getValue('set-settings-storymode'),
      background: {
        background_video: getValue('set-settings-background-background_video'),
        background_audio: getValue('set-settings-background-background_audio'),
        background_audio_volume: getValue('set-settings-background-background_audio_volume'),
        enable_extra_audio: getValue('set-settings-background-enable_extra_audio'),
      },
      tts: {
        voice_choice: getValue('set-settings-tts-voice_choice'),
        random_voice: getValue('set-settings-tts-random_voice'),
        elevenlabs_voice_name: getValue('set-settings-tts-elevenlabs_voice_name'),
        elevenlabs_api_key: getValue('set-settings-tts-elevenlabs_api_key'),
        tiktok_voice: getValue('set-settings-tts-tiktok_voice'),
        tiktok_sessionid: getValue('set-settings-tts-tiktok_sessionid'),
        silence_duration: getValue('set-settings-tts-silence_duration'),
        no_emojis: getValue('set-settings-tts-no_emojis'),
      },
    },
  };

  try {
    const res = await API.post('/api/settings', config);
    if (res.ok) {
      showToast('Settings saved successfully!', 'success');
    } else {
      showToast(res.error || 'Failed to save', 'error');
    }
  } catch (e) {
    showToast('Failed to save settings', 'error');
  }

  btn.disabled = false;
  btn.innerHTML = '💾 Save Settings';
}


// ═══════════════════════════════════════════════════════
//   Initialization
// ═══════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  initRouter();
  startStatusPolling();
});
