// DOM Elements
const $ = (q) => document.querySelector(q);
const $$ = (q) => document.querySelectorAll(q);

// Main Elements
const formContainer = $("#formContainer");
const tokenInput = $("#token");
const saveTokenBtn = $("#saveTokenBtn");
const tokenStatusBadge = $("#tokenStatusBadge");
const tokenStatusText = $("#tokenStatusText");
const runBtn = $("#runBtn");
const pageTitle = $("#pageTitle");
const pageDesc = $("#pageDesc");

// Cards
const authCard = $("#authCard");
const extractionCard = $("#extractionCard");
const progressCard = $("#progressCard");
const resultsCard = $("#resultsCard");

// Progress Elements
const bar = $("#bar");
const progressPercent = $("#progressPercent");
const progressMsg = $("#progressMsg");
const progressStatus = $("#progressStatus");
const logEl = $("#log");
const clearLogBtn = $("#clearLogBtn");
const outputsEl = $("#outputs");

// Modal Elements
const auditModal = $("#auditModal");
const settingsModal = $("#settingsModal");
const auditLogBtn = $("#auditLogBtn");
const settingsBtn = $("#settingsBtn");
const closeAuditBtn = $("#closeAuditBtn");
const closeSettingsBtn = $("#closeSettingsBtn");
const refreshAuditBtn = $("#refreshAudit");
const auditList = $("#auditList");
const viewAuditBtn = $("#viewAuditBtn");

// Navigation
const navBtns = $$(".nav-btn[data-tool]");

// Current state
let currentTool = "file-commit-history";
let currentJobId = null;

// Form configurations
const FORMS = {
  "file-commit-history": {
    title: "File Commit History",
    desc: "Extract commit history for specific files across repositories",
    html: `
      <div class="form-row">
        <div class="form-group">
          <label for="org">Organization</label>
          <input id="org" class="form-input" placeholder="e.g., name-of-organisation" value="name-of-organisation"/>
        </div>
        <div class="form-group">
          <label for="repos">Repositories <span class="help-text">(space or comma separated)</span></label>
          <input id="repos" class="form-input" placeholder="e.g., repo-in-org repo-in-org-2"/>
        </div>
      </div>
      <div class="form-group">
        <label for="file_path">File Path <span class="help-text">(required)</span></label>
        <input id="file_path" class="form-input" placeholder="e.g., .github/workflows/service-deployment.yml"/>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="sha">Branch / SHA <span class="help-text">(optional)</span></label>
          <input id="sha" class="form-input" placeholder="e.g., main"/>
        </div>
        <div class="form-group">
          <label for="since">Date Range</label>
          <div style="display: flex; gap: 10px;">
            <input id="since" class="form-input" placeholder="From (YYYY-MM-DD)"/>
            <input id="until" class="form-input" placeholder="To (YYYY-MM-DD)"/>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label for="verbose">
          <input type="checkbox" id="verbose" style="margin-right: 8px;"/>
          Enable verbose logging
        </label>
      </div>
    `
  },
  "pull-request-extractor": {
    title: "Pull Request Extractor",
    desc: "Extract and analyze pull request data from repositories",
    html: `
      <div class="form-row">
        <div class="form-group">
          <label for="org">Organization</label>
          <input id="org" class="form-input" placeholder="e.g., name-of-organisation" value="name-of-organisation"/>
        </div>
        <div class="form-group">
          <label for="repos">Repositories <span class="help-text">(space or comma separated)</span></label>
          <input id="repos" class="form-input" placeholder="e.g., repo-in-org-2 repo-in-org-3"/>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="state">PR State</label>
          <select id="state" class="form-select">
            <option value="closed" selected>Closed</option>
            <option value="open">Open</option>
            <option value="all">All</option>
          </select>
        </div>
        <div class="form-group">
          <label for="merged_only">Filter</label>
          <select id="merged_only" class="form-select">
            <option value="true" selected>Merged PRs only</option>
            <option value="false">All PRs</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label for="since">Date Range <span class="help-text">(optional)</span></label>
          <div style="display: flex; gap: 10px;">
            <input id="since" class="form-input" placeholder="From (YYYY-MM-DD)"/>
            <input id="until" class="form-input" placeholder="To (YYYY-MM-DD)"/>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label for="verbose">
          <input type="checkbox" id="verbose" style="margin-right: 8px;"/>
          Enable verbose logging
        </label>
      </div>
    `
  }
};

// Initialize
function init() {
  loadToken();
  setupNavigation();
  setupModals();
  renderForm();
  
  // Event Listeners
  saveTokenBtn.addEventListener("click", saveToken);
  runBtn.addEventListener("click", runExtraction);
  clearLogBtn.addEventListener("click", clearLog);
  refreshAuditBtn.addEventListener("click", refreshAudit);
  viewAuditBtn.addEventListener("click", () => showAuditForJob(currentJobId));
}

// Navigation Setup
function setupNavigation() {
  navBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      const tool = btn.dataset.tool;
      if (tool) {
        switchTool(tool);
      }
    });
  });
}

// Switch Tool
function switchTool(tool) {
  currentTool = tool;
  
  // Update navigation
  navBtns.forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tool === tool);
  });
  
  // Update page header
  const config = FORMS[tool];
  pageTitle.textContent = config.title;
  pageDesc.textContent = config.desc;
  
  // Reset and render form
  resetUI();
  renderForm();
}

// Render Form
function renderForm() {
  const config = FORMS[currentTool];
  formContainer.innerHTML = config.html;
}

// Modal Setup
function setupModals() {
  // Audit Log Modal
  auditLogBtn.addEventListener("click", () => {
    refreshAudit();
    showModal(auditModal);
  });
  
  closeAuditBtn.addEventListener("click", () => hideModal(auditModal));
  
  // Settings Modal
  settingsBtn.addEventListener("click", () => showModal(settingsModal));
  closeSettingsBtn.addEventListener("click", () => hideModal(settingsModal));
  
  // Close on backdrop click
  $$(".modal-backdrop").forEach(backdrop => {
    backdrop.addEventListener("click", (e) => {
      const modal = e.target.closest(".modal");
      if (modal) hideModal(modal);
    });
  });
}

// Modal Functions
function showModal(modal) {
  modal.classList.remove("hidden");
  modal.style.display = "flex";
  setTimeout(() => modal.style.opacity = "1", 10);
}

function hideModal(modal) {
  modal.style.opacity = "0";
  setTimeout(() => {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }, 200);
}

// Token Management
function loadToken() {
  const token = localStorage.getItem("gh_token") || "";
  tokenInput.value = token;
  updateTokenStatus(!!token);
}

function saveToken() {
  const token = tokenInput.value.trim();
  localStorage.setItem("gh_token", token);
  updateTokenStatus(!!token);
  
  // Show feedback
  const originalText = saveTokenBtn.textContent;
  saveTokenBtn.textContent = token ? "✓ Token Saved" : "Token Cleared";
  setTimeout(() => {
    saveTokenBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
      </svg>
      Save Token
    `;
  }, 2000);
}

function updateTokenStatus(hasToken) {
  tokenStatusText.textContent = hasToken ? "Token Active" : "No Token";
  tokenStatusBadge.classList.toggle("active", hasToken);
}

// Run Extraction
async function runExtraction() {
  const token = tokenInput.value.trim();
  if (!token) {
    showNotification("Please enter your GitHub token first", "warning");
    tokenInput.focus();
    return;
  }
  
  const args = collectArgs();
  
  // Validate required fields
  if (currentTool === "file-commit-history" && !args.file_path) {
    showNotification("File path is required", "warning");
    $("#file_path").focus();
    return;
  }
  
  setUIState("loading");
  clearProgress();
  
  try {
    const res = await fetch("/api/extract", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ 
        type: currentTool, 
        token, 
        args 
      })
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      setUIState("ready");
      showNotification(data.error || "Failed to start extraction", "error");
      return;
    }
    
    currentJobId = data.job_id;
    progressCard.classList.remove("hidden");
    resultsCard.classList.add("hidden");
    pollStatus(currentJobId);
    
  } catch (err) {
    setUIState("ready");
    showNotification("Network error. Please try again.", "error");
  }
}

// Collect Form Arguments
function collectArgs() {
  const args = {};
  const inputs = formContainer.querySelectorAll("input, select");
  
  inputs.forEach(el => {
    const key = el.id;
    if (!key) return;
    
    if (el.type === "checkbox") {
      args[key] = el.checked;
    } else if (el.tagName === "SELECT" && (key === "merged_only" || key === "verbose")) {
      // Convert string "true"/"false" to actual boolean for these specific fields
      args[key] = el.value === "true";
    } else {
      const val = el.value.trim();
      if (val) args[key] = val;
    }
  });
  
  return args;
}

// Poll Job Status
async function pollStatus(jobId) {
  try {
    const res = await fetch(`/api/status/${jobId}`);
    const data = await res.json();
    
    if (!res.ok) {
      progressMsg.textContent = data.error || "Error querying job";
      setUIState("ready");
      return;
    }
    
    updateProgress(data);
    
    // Update log
    if (data.log && data.log.length > 0) {
      logEl.textContent = data.log.join("\n");
      logEl.scrollTop = logEl.scrollHeight;
    }
    
    // Check if completed
    if (data.status === "succeeded") {
      handleSuccess(data);
      return;
    } else if (data.status === "failed") {
      handleFailure(data);
      return;
    }
    
    // Continue polling
    setTimeout(() => pollStatus(jobId), 1000);
    
  } catch (err) {
    progressMsg.textContent = "Connection lost. Retrying...";
    setTimeout(() => pollStatus(jobId), 2000);
  }
}

// Update Progress Display
function updateProgress(data) {
  const percent = data.progress || 0;
  bar.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
  progressMsg.textContent = data.message || "";
  
  // Update status badge
  let statusHTML = '';
  if (data.status === "running") {
    statusHTML = '<span class="status-badge running">Running</span>';
  } else if (data.status === "queued") {
    statusHTML = '<span class="status-badge">Queued</span>';
  }
  progressStatus.innerHTML = statusHTML;
}

// Handle Success
function handleSuccess(data) {
  setUIState("ready");
  
  // Update progress card
  progressStatus.innerHTML = '<span class="status-badge completed">Completed</span>';
  bar.style.width = "100%";
  progressPercent.textContent = "100%";
  progressMsg.textContent = "Extraction completed successfully";
  
  // Show results card
  resultsCard.classList.remove("hidden");
  
  // Render downloads
  renderDownloads(data.outputs || []);
  
  // Show notification
  showNotification("Extraction completed successfully!", "success");
  
  // Refresh audit logs
  refreshAudit();
}

// Handle Failure
function handleFailure(data) {
  setUIState("ready");
  
  progressStatus.innerHTML = '<span class="status-badge failed">Failed</span>';
  progressMsg.textContent = data.message || "Extraction failed";
  
  showNotification("Extraction failed. Check the logs for details.", "error");
  
  // Refresh audit logs
  refreshAudit();
}

// Render Downloads
function renderDownloads(outputs) {
  outputsEl.innerHTML = "";
  
  if (outputs.length === 0) {
    outputsEl.innerHTML = '<p class="help-text" style="text-align: center; margin: 20px 0;">No files generated</p>';
    return;
  }
  
  outputs.forEach(filename => {
    const item = document.createElement("div");
    item.className = "download-item";
    
    item.innerHTML = `
      <div class="download-info">
        <div class="file-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        </div>
        <div class="file-details">
          <h5>${filename}</h5>
          <p>CSV File</p>
        </div>
      </div>
      <a href="/api/download/${currentJobId}/${encodeURIComponent(filename)}" 
         class="download-btn" download>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        Download
      </a>
    `;
    
    outputsEl.appendChild(item);
  });
}

// Refresh Audit Logs
async function refreshAudit() {
  try {
    const res = await fetch("/api/audit");
    const rows = await res.json();
    
    auditList.innerHTML = "";
    
    rows.slice().reverse().forEach(r => {
      const item = document.createElement("div");
      item.className = "audit-item";
      
      const when = new Date((r.ts || 0) * 1000).toLocaleString();
      const status = r.status || "";
      const statusClass = status === "succeeded" ? "success" : "";
      
      item.innerHTML = `
        <div class="audit-header">
          <span class="audit-badge">${r.tool || "?"}</span>
          <span class="audit-badge ${statusClass}">${status}</span>
          <span class="audit-time">${when}</span>
        </div>
        <div class="audit-details">${escapeHTML(JSON.stringify(r, null, 2))}</div>
      `;
      
      auditList.appendChild(item);
    });
    
    $("#auditCount").textContent = `Last ${rows.length} entries`;
    
  } catch (err) {
    console.error("Failed to fetch audit logs:", err);
  }
}

// Show Audit for Specific Job
function showAuditForJob(jobId) {
  if (!jobId) return;
  refreshAudit();
  showModal(auditModal);
  
  // Scroll to the job in audit list
  setTimeout(() => {
    const items = auditList.querySelectorAll(".audit-item");
    items.forEach(item => {
      if (item.textContent.includes(jobId)) {
        item.scrollIntoView({ behavior: "smooth", block: "center" });
        item.style.border = "2px solid var(--accent-primary)";
        setTimeout(() => {
          item.style.border = "";
        }, 3000);
      }
    });
  }, 100);
}

// UI State Management
function setUIState(state) {
  const isLoading = state === "loading";
  
  runBtn.disabled = isLoading;
  saveTokenBtn.disabled = isLoading;
  
  formContainer.querySelectorAll("input, select").forEach(el => {
    el.disabled = isLoading;
  });
  
  navBtns.forEach(btn => {
    btn.disabled = isLoading;
  });
  
  if (isLoading) {
    runBtn.innerHTML = `
      <svg class="animate-spin" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Starting...
    `;
  } else {
    runBtn.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      Start Extraction
    `;
  }
}

// Clear Progress
function clearProgress() {
  bar.style.width = "0%";
  progressPercent.textContent = "0%";
  progressMsg.textContent = "";
  logEl.textContent = "";
  outputsEl.innerHTML = "";
  progressStatus.innerHTML = "";
}

// Clear Log
function clearLog() {
  logEl.textContent = "";
}

// Reset UI
function resetUI() {
  progressCard.classList.add("hidden");
  resultsCard.classList.add("hidden");
  clearProgress();
  currentJobId = null;
}

// Show Notification
function showNotification(message, type = "info") {
  // This is a simple notification - you could enhance with a toast library
  console.log(`[${type.toUpperCase()}] ${message}`);
}

// Utility: Escape HTML
function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Add spinning animation CSS
const style = document.createElement("style");
style.textContent = `
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .animate-spin {
    animation: spin 1s linear infinite;
  }
`;
document.head.appendChild(style);

// Initialize on load
document.addEventListener("DOMContentLoaded", init);