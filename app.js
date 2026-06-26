const $ = (selector) => document.querySelector(selector);

const state = {
  files: [],
  currentCase: null,
  pollTimer: null,
  cases: [],
  casePagination: { limit: 20, offset: 0, total: 0, has_more: false },
  logPagination: { limit: 50, offset: 0, total: 0, has_more: false },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(timestamp) {
  if (!timestamp) return "-";
  return new Date(timestamp).toLocaleString("zh-CN", { hour12: false });
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 2600);
}

function setStatus(text, tone = "") {
  $("#statusPill").textContent = text;
  $("#statusDot").className = `status-dot ${tone}`.trim();
}

async function fetchJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(options.method || "GET", url);
    xhr.responseType = "text";
    Object.entries(options.headers || {}).forEach(([key, value]) => xhr.setRequestHeader(key, value));
    xhr.onload = () => {
      let payload = {};
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch (error) {
        reject(new Error("接口返回格式异常。"));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new Error(payload.error || payload.detail || "请求失败。"));
        return;
      }
      resolve(payload);
    };
    xhr.onerror = () => reject(new Error("网络请求失败。"));
    xhr.send(options.body || null);
  });
}

function segmentForFile(file) {
  const name = file.name.toLowerCase();
  if (/chat|message|聊天|沟通|buyer/.test(name)) return "买家聊天";
  if (/logistics|tracking|express|carrier|物流|快递|签收/.test(name)) return "物流凭证";
  if (/order|detail|payment|订单|交易|付款/.test(name)) return "订单状态";
  if (/sku|spec|detail|商品|规格|实物|照片/.test(name)) return "商品规格";
  if (/refund|return|after|complaint|差评|退款|退货|投诉|售后/.test(name)) return "售后记录";
  return "证据组件";
}

function renderFileRows() {
  const body = $("#fileRows");
  if (!state.files.length) {
    body.innerHTML = '<tr class="empty-row"><td colspan="4">尚未选择证据组件。</td></tr>';
    return;
  }
  body.innerHTML = state.files.map((file, index) => `
    <tr>
      <td class="file-name">${escapeHtml(file.name)}</td>
      <td><span class="tag">${escapeHtml(segmentForFile(file))}</span></td>
      <td>${formatBytes(file.size)}</td>
      <td><button class="remove-row" type="button" data-remove="${index}">移除</button></td>
    </tr>
  `).join("");
}

function updateUploadState() {
  $("#imageCount").textContent = `${state.files.length} / 5`;
  $("#analyzeBtn").disabled = state.files.length < 1;
  $("#formError").textContent = "";
  renderFileRows();
}

function addFiles(fileList) {
  const images = [...fileList].filter((file) => file.type.startsWith("image/"));
  if (!images.length) {
    $("#formError").textContent = "请上传 PNG、JPG 或 WebP 图片。";
    return;
  }
  const room = Math.max(0, 5 - state.files.length);
  state.files.push(...images.slice(0, room));
  if (images.length > room) showToast("最多只能上传 5 张截图。");
  updateUploadState();
}

function statusLabel(status) {
  return {
    processing: "处理中",
    done: "完成",
    failed: "失败",
  }[status] || "未知";
}

function statusTone(status) {
  return {
    processing: "working",
    done: "ready",
    failed: "failed",
  }[status] || "";
}

function renderCaseList() {
  const list = $("#caseList");
  if (!state.cases.length) {
    list.innerHTML = '<p class="muted">暂无历史案件。</p>';
    return;
  }
  list.innerHTML = state.cases.map((item) => `
    <button class="case-item ${state.currentCase?.id === item.id ? "active" : ""}" type="button" data-case-id="${escapeHtml(item.id)}">
      <span class="case-status ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      <strong>${escapeHtml(item.id)}</strong>
      <small>${formatTime(item.created_at)} · ${item.files?.length || 0} 张截图</small>
      <p>${escapeHtml(item.result?.judgment || "等待分析结果")}</p>
    </button>
  `).join("");
  renderCasePager();
}

async function loadCases() {
  const query = new URLSearchParams({
    limit: String(state.casePagination.limit),
    offset: String(state.casePagination.offset),
  });
  const payload = await fetchJson(`/cases?${query.toString()}`);
  state.cases = payload.cases || [];
  state.casePagination = payload.pagination || state.casePagination;
  renderCaseList();
}

function renderCasePager() {
  const page = Math.floor(state.casePagination.offset / state.casePagination.limit) + 1;
  const totalPages = Math.max(1, Math.ceil((state.casePagination.total || 0) / state.casePagination.limit));
  $("#casePageText").textContent = `${page} / ${totalPages}`;
  $("#casePrevBtn").disabled = state.casePagination.offset <= 0;
  $("#caseNextBtn").disabled = !state.casePagination.has_more;
}

function renderCurrentCase(item) {
  const target = $("#currentCase");
  if (!item) {
    target.innerHTML = '<p class="muted">还没有当前案件。上传证据后会自动生成 Case。</p>';
    renderPipeline(null);
    return;
  }
  target.innerHTML = `
    <div class="case-meta">
      <span class="case-status ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      <strong>${escapeHtml(item.id)}</strong>
      <small>创建：${formatTime(item.created_at)} / 更新：${formatTime(item.updated_at)}</small>
    </div>
    <div class="file-chip-list">
      ${(item.files || []).map((file) => `<span>${escapeHtml(file.name)} · ${formatBytes(file.size)}</span>`).join("") || '<span>暂无文件</span>'}
    </div>
    ${item.result ? `<p class="case-result-line">结论：${escapeHtml(item.result.judgment)} / 分数：${Number(item.result.score || 0)}</p>` : '<p class="muted">分析任务正在处理或等待启动。</p>'}
  `;
  renderPipeline(item);
}

function renderPipeline(item) {
  const traceSteps = item?.trace?.steps || [];
  const names = ["Case创建", "OCR解析", "证据抽取", "最终判断"];
  $("#pipelineSteps").innerHTML = names.map((name, index) => {
    const done = name === "Case创建" ? !!item : traceSteps.some((step) => step.step === name && step.status === "success");
    const failed = traceSteps.some((step) => step.status === "failed");
    const active = item?.status === "processing" && !done && !failed;
    return `<div class="pipeline-step ${done ? "done" : ""} ${active ? "active" : ""} ${failed ? "failed" : ""}">
      <span>${done ? "[✓]" : failed ? "[!]" : active ? "[→]" : "[ ]"}</span><p>${escapeHtml(done ? `${name}完成` : `等待${name}`)}</p>
    </div>`;
  }).join("");
}

function riskTone(score) {
  if (score >= 70) return ["高纠纷风险", "high"];
  if (score >= 30) return ["中等纠纷风险", "medium"];
  return ["低纠纷风险", "low"];
}

function appealTone(score) {
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function judgementLabel(value) {
  return {
    support_buyer: "建议支持买家",
    support_seller: "建议支持商家",
    insufficient_evidence: "证据不足",
  }[value] || value || "等待判断";
}

function listMarkup(items, emptyText) {
  const values = (items || []).filter(Boolean);
  if (!values.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return values.map((item) => `<p>${escapeHtml(item)}</p>`).join("");
}

function renderResult(result) {
  if (!result) {
    $("#riskScore").textContent = "0";
    $("#appealWinScore").textContent = "0";
    $("#riskHeadline").textContent = "等待分析";
    $("#judgementText").textContent = "等待分析";
    $("#judgementReason").textContent = "";
    $("#summaryText").textContent = "-";
    $("#keyEvidenceList").innerHTML = '<p class="muted">暂无证据链摘要。</p>';
    $("#reasonList").innerHTML = '<p class="muted">暂无风险原因。</p>';
    $("#gapList").innerHTML = '<p class="muted">暂无证据缺口。</p>';
    $("#appealText").textContent = "系统生成的申诉文本将显示在这里。";
    return;
  }
  const disputeRisk = Number(result.dispute_risk_score ?? result.risk_score ?? 0);
  const appealWin = Number(result.appeal_win_score ?? 0);
  const [riskLabel, riskClass] = riskTone(disputeRisk);
  $("#riskCard").className = `score-card ${riskClass}`;
  $("#riskLevel").textContent = riskLabel;
  $("#riskScore").textContent = disputeRisk;
  $("#appealScoreCard").className = `score-card appeal ${appealTone(appealWin)}`;
  $("#appealWinScore").textContent = appealWin;
  $("#scoreExplanation").textContent = result.score_explanation || "风险高不等于申诉胜率高。";
  $("#riskHeadline").textContent = result.dispute_type || "纠纷风险评估";
  $("#recommendation").textContent = result.recommendation || "暂无建议。";
  $("#judgementText").textContent = judgementLabel(result.judgement_direction);
  $("#judgementReason").textContent = result.judgement_reason || "暂无判决方向说明。";
  $("#summaryText").textContent = result.dispute_summary || "未识别到足够证据形成纠纷总结。";
  $("#keyEvidenceList").innerHTML = listMarkup(result.evidence_order, "暂无证据链摘要。");
  $("#reasonList").innerHTML = listMarkup(result.risk_reasons, "未识别到直接风险原因。");
  $("#gapList").innerHTML = listMarkup(result.evidence_gaps, "当前证据链暂未发现明显缺口。");
  $("#appealText").textContent = result.appeal_text || "";
}

function renderTrace(item) {
  const steps = item?.trace?.steps || [];
  $("#traceFeed").innerHTML = steps.map((step) => `
    <article class="${escapeHtml(step.status)}">
      <time>${formatTime(step.timestamp)}</time>
      <strong>${step.status === "success" ? "✔" : "!"} ${escapeHtml(step.step)}</strong>
      <p>${escapeHtml(step.output || "")}</p>
      <small>${Number(step.duration_ms || 0)} ms${step.confidence !== undefined ? ` · confidence ${Number(step.confidence)}%` : ""}</small>
    </article>
  `).join("") || '<p class="muted">暂无 AI 分析过程。</p>';
}

function logMessage(item) {
  if (item.type === "user") return item.action;
  if (item.type === "ai") return item.reasoning || item.model_output || "AI推理日志";
  return item.message || item.step || "系统日志";
}

function renderMiniLogs(logs) {
  $("#caseLogFeed").innerHTML = logs.slice(0, 12).map((item) => `
    <article class="${escapeHtml(item.level || item.type)}">
      <span>${escapeHtml(item.type)} · ${formatTime(item.timestamp)}</span>
      <p>${escapeHtml(logMessage(item))}</p>
    </article>
  `).join("") || '<p class="muted">暂无 Case 相关日志。</p>';
}

async function loadCaseLogs(caseId) {
  if (!caseId) {
    renderMiniLogs([]);
    return [];
  }
  const headers = adminHeaders();
  const [user, system, ai] = await Promise.all([
    fetchJson(`/logs/user?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
    fetchJson(`/logs/system?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
    fetchJson(`/logs/ai?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
  ]);
  const logs = [...(user.logs || []), ...(system.logs || []), ...(ai.logs || [])]
    .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0));
  renderMiniLogs(logs);
  return logs;
}

async function selectCase(caseId) {
  const payload = await fetchJson(`/case/${encodeURIComponent(caseId)}`);
  state.currentCase = payload.case;
  renderCurrentCase(state.currentCase);
  renderResult(state.currentCase.raw_result);
  renderTrace(state.currentCase);
  await loadCaseLogs(caseId);
  renderCaseList();
  setStatus(statusLabel(state.currentCase.status), statusTone(state.currentCase.status));
}

function startPolling(caseId) {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      await selectCase(caseId);
      if (state.currentCase?.status !== "processing") {
        clearInterval(state.pollTimer);
        await loadCases();
      }
    } catch (error) {
      clearInterval(state.pollTimer);
      showToast(error.message);
    }
  }, 1300);
}

async function analyzeEvidence() {
  if (!state.files.length) return;
  const formData = new FormData();
  state.files.forEach((file) => formData.append("images", file));
  $("#analyzeBtn").disabled = true;
  setStatus("创建 Case", "working");
  try {
    const payload = await fetchJson("/case/analyze", { method: "POST", body: formData });
    state.currentCase = payload.case;
    renderCurrentCase(state.currentCase);
    renderResult(null);
    renderTrace(state.currentCase);
    await loadCases();
    await loadCaseLogs(state.currentCase.id);
    setStatus("分析中", "working");
    showToast(`已创建 ${state.currentCase.id}，开始后台分析。`);
    startPolling(state.currentCase.id);
  } catch (error) {
    setStatus("分析失败", "failed");
    $("#formError").textContent = error.message;
    showToast(error.message);
  } finally {
    $("#analyzeBtn").disabled = state.files.length < 1;
  }
}

async function loadAdminLogs() {
  const caseId = $("#logCaseFilter").value.trim();
  const type = $("#logTypeFilter").value;
  const types = type === "all" ? ["user", "system", "ai"] : [type];
  persistAdminToken();
  const queryBase = new URLSearchParams({
    limit: String(state.logPagination.limit),
    offset: String(state.logPagination.offset),
  });
  if (caseId) queryBase.set("case_id", caseId);
  const headers = adminHeaders();
  const results = await Promise.all(types.map((kind) => fetchJson(`/logs/${kind}?${queryBase.toString()}`, { headers })));
  const logs = results.flatMap((item) => item.logs || []).sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0));
  const total = results.reduce((sum, item) => sum + Number(item.pagination?.total || 0), 0);
  state.logPagination = {
    ...state.logPagination,
    total,
    has_more: results.some((item) => item.pagination?.has_more),
  };
  $("#adminLogRows").innerHTML = logs.map((item) => `
    <tr class="${item.level === "error" ? "error-row" : ""}">
      <td>${formatTime(item.timestamp)}</td>
      <td>${escapeHtml(item.type)}</td>
      <td class="file-name">${escapeHtml(item.case_id || "-")}</td>
      <td>${escapeHtml(item.level || item.action || "-")}</td>
      <td>${escapeHtml(logMessage(item)).slice(0, 240)}</td>
      <td>${item.duration_ms !== undefined ? `${Number(item.duration_ms)} ms` : "-"}</td>
    </tr>
  `).join("") || '<tr class="empty-row"><td colspan="6">暂无日志。</td></tr>';
  renderLogPager();
}

function adminHeaders() {
  const token = localStorage.getItem("admin_token") || "";
  return token ? { "X-Admin-Token": token } : {};
}

function persistAdminToken() {
  const input = $("#adminTokenInput");
  const token = input.value.trim();
  if (token) localStorage.setItem("admin_token", token);
}

function hydrateAdminToken() {
  $("#adminTokenInput").value = localStorage.getItem("admin_token") || "";
}

function renderLogPager() {
  const page = Math.floor(state.logPagination.offset / state.logPagination.limit) + 1;
  const totalPages = Math.max(1, Math.ceil((state.logPagination.total || 0) / state.logPagination.limit));
  $("#logPageText").textContent = `${page} / ${totalPages}`;
  $("#logPrevBtn").disabled = state.logPagination.offset <= 0;
  $("#logNextBtn").disabled = !state.logPagination.has_more;
}

async function copyAppeal() {
  const text = $("#appealText").textContent.trim();
  if (!text || text === "系统生成的申诉文本将显示在这里。") return;
  await navigator.clipboard.writeText(text);
  showToast("申诉文本已复制。");
}

function resetAll() {
  state.files = [];
  clearInterval(state.pollTimer);
  $("#fileInput").value = "";
  setStatus("等待上传");
  updateUploadState();
}

function showWorkspace() {
  $("#workspaceView").hidden = false;
  $("#logsView").hidden = true;
  $("#workspaceNav").classList.add("active");
  $("#logsNav").classList.remove("active");
  history.replaceState(null, "", "/");
}

async function showLogs() {
  $("#workspaceView").hidden = true;
  $("#logsView").hidden = false;
  $("#workspaceNav").classList.remove("active");
  $("#logsNav").classList.add("active");
  history.replaceState(null, "", "/admin/logs");
  await loadAdminLogs();
}

function bindEvents() {
  $("#fileInput").addEventListener("change", (event) => addFiles(event.target.files));
  $("#analyzeBtn").addEventListener("click", analyzeEvidence);
  $("#copyAppealBtn").addEventListener("click", copyAppeal);
  $("#resetBtn").addEventListener("click", resetAll);
  $("#refreshBtn").addEventListener("click", async () => {
    await loadCases();
    if (state.currentCase) await selectCase(state.currentCase.id);
  });
  $("#reloadCasesBtn").addEventListener("click", loadCases);
  $("#casePrevBtn").addEventListener("click", async () => {
    state.casePagination.offset = Math.max(0, state.casePagination.offset - state.casePagination.limit);
    await loadCases();
  });
  $("#caseNextBtn").addEventListener("click", async () => {
    if (!state.casePagination.has_more) return;
    state.casePagination.offset += state.casePagination.limit;
    await loadCases();
  });
  $("#workspaceNav").addEventListener("click", showWorkspace);
  $("#logsNav").addEventListener("click", showLogs);
  $("#loadLogsBtn").addEventListener("click", async () => {
    state.logPagination.offset = 0;
    await loadAdminLogs();
  });
  $("#logPrevBtn").addEventListener("click", async () => {
    state.logPagination.offset = Math.max(0, state.logPagination.offset - state.logPagination.limit);
    await loadAdminLogs();
  });
  $("#logNextBtn").addEventListener("click", async () => {
    if (!state.logPagination.has_more) return;
    state.logPagination.offset += state.logPagination.limit;
    await loadAdminLogs();
  });
  $("#caseList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-case-id]");
    if (button) await selectCase(button.dataset.caseId);
  });
  $("#fileRows").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove]");
    if (!button) return;
    state.files.splice(Number(button.dataset.remove), 1);
    updateUploadState();
  });
  const dropzone = $("#dropzone");
  ["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragging");
  }));
  dropzone.addEventListener("drop", (event) => addFiles(event.dataTransfer.files));
}

async function init() {
  bindEvents();
  hydrateAdminToken();
  updateUploadState();
  renderCurrentCase(null);
  renderResult(null);
  await loadCases();
  if (location.pathname === "/admin/logs") await showLogs();
}

init().catch((error) => showToast(error.message));
