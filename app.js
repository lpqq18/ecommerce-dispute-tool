const $ = (selector) => document.querySelector(selector);

const state = {
  files: [],
  currentCase: null,
  pollTimer: null,
  cases: [],
  caseFilter: "all",
  casePagination: { limit: 20, offset: 0, total: 0, has_more: false },
  logPagination: { limit: 50, offset: 0, total: 0, has_more: false },
};

const ROUTE_PREFIXES = new Set(["", "admin", "api", "case", "cases", "logs"]);
const firstPathSegment = location.pathname.split("/").filter(Boolean)[0] || "";
const APP_BASE_PATH = window.APP_BASE_PATH || (ROUTE_PREFIXES.has(firstPathSegment) ? "" : `/${firstPathSegment}`);

function appUrl(path) {
  if (!APP_BASE_PATH) return path;
  if (path === "/") return `${APP_BASE_PATH}/`;
  return `${APP_BASE_PATH}${path}`;
}

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

function formatShortDate(timestamp) {
  if (!timestamp) return "-";
  const date = new Date(timestamp);
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
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
    xhr.open(options.method || "GET", appUrl(url));
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
  if (/chat|message|buyer|聊天|对话/.test(name)) return "聊天记录";
  if (/logistics|tracking|express|carrier|物流|快递|签收/.test(name)) return "物流凭证";
  if (/order|detail|payment|订单|交易|付款/.test(name)) return "订单详情";
  if (/sku|spec|product|商品|规格|实物|照片/.test(name)) return "商品规格";
  if (/refund|return|after|complaint|review|差评|退款|退货|投诉|售后/.test(name)) return "售后/差评";
  return "证据组件";
}

function statusLabel(status) {
  return {
    queued: "排队中",
    processing: "处理中",
    retrying: "重试中",
    done: "完成",
    failed: "失败",
  }[status] || "未知";
}

function statusTone(status) {
  return {
    queued: "working",
    processing: "working",
    retrying: "working",
    done: "ready",
    failed: "failed",
  }[status] || "";
}

function judgementLabel(value) {
  return {
    support_buyer: "不建议申诉",
    support_seller: "建议申诉",
    insufficient_evidence: "建议补证",
  }[value] || value || "等待判断";
}

function appealTone(score) {
  if (score >= 70) return "high";
  if (score >= 50) return "medium";
  return "low";
}

function actionBadge(score) {
  if (score >= 70) return { text: "建议申诉", tone: "good" };
  if (score >= 50) return { text: "建议补证", tone: "warn" };
  return { text: "不建议申诉", tone: "bad" };
}

function listMarkup(items, emptyText) {
  const values = (items || []).filter(Boolean);
  if (!values.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return values.map((item) => `<p>${escapeHtml(item)}</p>`).join("");
}

function caseMatchesFilter(item) {
  const result = item.raw_result || {};
  const judgement = result.judgement_direction || "";
  if (state.caseFilter === "active") return ["queued", "processing", "retrying"].includes(item.status);
  if (state.caseFilter === "won") return item.status === "done" && (judgement === "support_seller" || item.result?.judgment === "支持申诉");
  if (state.caseFilter === "rejected") return item.status === "failed" || judgement === "support_buyer" || judgement === "insufficient_evidence";
  return true;
}

function filteredCases() {
  const keyword = ($("#caseSearchInput")?.value || "").trim().toLowerCase();
  return state.cases.filter((item) => {
    const haystack = [
      item.id,
      item.status,
      item.result?.judgment,
      item.raw_result?.dispute_type,
      ...(item.files || []).map((file) => file.name),
    ].join(" ").toLowerCase();
    return caseMatchesFilter(item) && (!keyword || haystack.includes(keyword));
  });
}

function renderCaseList() {
  const list = $("#caseList");
  const cases = filteredCases();
  if (!cases.length) {
    list.innerHTML = `
      <div class="case-empty">
        <strong>暂无匹配案件</strong>
        <p>上传聊天、订单或物流截图后，系统会自动创建可追踪 Case。</p>
      </div>
    `;
    renderCasePager();
    return;
  }
  list.innerHTML = cases.map((item) => {
    const result = item.raw_result || {};
    const winScore = Number(result.appeal_win_score || item.result?.score || 0);
    const disputeType = result.dispute_type || "等待识别";
    const platform = platformLabel(item.files || []);
    return `
      <button class="case-item ${state.currentCase?.id === item.id ? "active" : ""}" type="button" data-case-id="${escapeHtml(item.id)}">
        <span class="case-row">
          <em>${escapeHtml(platform)}</em>
          <code>${escapeHtml(item.id)}</code>
        </span>
        <span class="case-row main">
          <strong>${escapeHtml(disputeType)}</strong>
          <b>${Number.isFinite(winScore) ? winScore : 0}%</b>
        </span>
        <span class="case-row">
          <small>${formatShortDate(item.created_at)}</small>
          <i class="case-status ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</i>
        </span>
      </button>
    `;
  }).join("");
  renderCasePager();
}

function platformLabel(files) {
  const text = files.map((file) => file.name || "").join(" ").toLowerCase();
  if (/pdd|拼多多/.test(text)) return "拼多多";
  if (/taobao|tmall|淘宝|天猫/.test(text)) return "淘宝";
  if (/douyin|抖音/.test(text)) return "抖音";
  return "平台";
}

async function loadCases() {
  const query = new URLSearchParams({
    limit: String(state.casePagination.limit),
    offset: String(state.casePagination.offset),
  });
  try {
    const payload = await fetchJson(`/cases?${query.toString()}`);
    state.cases = payload.cases || [];
    state.casePagination = payload.pagination || state.casePagination;
  } catch (error) {
    state.cases = state.cases || [];
  }
  renderCaseList();
}

function renderCasePager() {
  const page = Math.floor(state.casePagination.offset / state.casePagination.limit) + 1;
  const totalPages = Math.max(1, Math.ceil((state.casePagination.total || 0) / state.casePagination.limit));
  $("#casePageText").textContent = `${page} / ${totalPages}`;
  $("#casePrevBtn").disabled = state.casePagination.offset <= 0;
  $("#caseNextBtn").disabled = !state.casePagination.has_more;
}

function renderFileTags() {
  const target = $("#fileTagFlow");
  if (!state.files.length) {
    target.innerHTML = '<p class="muted">尚未选择证据组件。</p>';
    return;
  }
  target.innerHTML = state.files.map((file, index) => `
    <span class="file-tag">
      <b>${escapeHtml(segmentForFile(file))}</b>
      ${escapeHtml(file.name)}
      <button type="button" data-remove="${index}" aria-label="移除文件">x</button>
    </span>
  `).join("");
}

function updateUploadState() {
  $("#imageCount").textContent = `${state.files.length} / 5`;
  $("#analyzeBtn").disabled = state.files.length < 1;
  $("#formError").textContent = "";
  renderFileTags();
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
    ${item.workflow_state ? `<p class="muted">当前节点：${escapeHtml(item.workflow_state.current_node || "-")} / attempt ${Number(item.workflow_state.attempt || 0)}</p>` : ""}
    ${item.result ? `<p class="case-result-line">结论：${escapeHtml(item.result.judgment)} / 分数：${Number(item.result.score || 0)}</p>` : '<p class="muted">分析任务正在处理或等待启动。</p>'}
    ${item.status === "failed" && !String(item.id).startsWith("INLINE-") ? `<button class="retry-btn" type="button" data-retry-case="${escapeHtml(item.id)}">重试分析</button>` : ""}
  `;
  renderPipeline(item);
}

function renderPipeline(item) {
  const traceSteps = item?.trace?.steps || [];
  const names = ["Case创建", "OCR解析", "证据抽取", "冲突分析", "最终判断"];
  $("#pipelineSteps").innerHTML = names.map((name) => {
    const done = name === "Case创建" ? !!item : traceSteps.some((step) => String(step.step || "").includes(name) && step.status === "success");
    const failed = item?.status === "failed" && traceSteps.some((step) => step.status === "failed");
    const active = ["queued", "processing", "retrying"].includes(item?.status) && !done && !failed;
    return `<div class="pipeline-step ${done ? "done" : ""} ${active ? "active" : ""} ${failed ? "failed" : ""}">
      <span>${done ? "[ok]" : failed ? "[!]" : active ? "[..]" : "[ ]"}</span><p>${escapeHtml(done ? `${name}完成` : `等待${name}`)}</p>
    </div>`;
  }).join("");
}

function setResultTab(tab) {
  const reportActive = tab === "report";
  $("#reportTabBtn").classList.toggle("active", reportActive);
  $("#appealTabBtn").classList.toggle("active", !reportActive);
  $("#reportTabPanel").classList.toggle("active", reportActive);
  $("#appealTabPanel").classList.toggle("active", !reportActive);
}

function renderResult(result) {
  const hasResult = Boolean(result);
  $("#resultPanel").classList.toggle("is-disabled", !hasResult);
  $("#resultPanel").setAttribute("aria-disabled", String(!hasResult));
  $("#resultEmptyState").hidden = hasResult;

  if (!result) {
    $("#appealWinScore").textContent = "--";
    $("#scoreExplanation").textContent = "风险高不等于申诉胜率高。";
    $("#riskHeadline").textContent = "等待分析";
    $("#judgementText").textContent = "等待分析";
    $("#actionBadge").className = "action-badge neutral";
    $("#actionBadge").textContent = "等待上传";
    $("#summaryText").textContent = "-";
    $("#keyEvidenceList").innerHTML = '<p class="muted">暂无证据链摘要。</p>';
    $("#reasonList").innerHTML = '<p class="muted">暂无风险原因。</p>';
    $("#gapList").innerHTML = '<p class="muted">暂无证据缺口。</p>';
    $("#appealText").textContent = "系统生成的申诉文本将显示在这里。";
    renderStructuredEvidence(null);
    setResultTab("report");
    return;
  }

  const appealWin = Number(result.appeal_win_score ?? 0);
  const badge = actionBadge(appealWin);
  $("#appealWinScore").textContent = `${appealWin}%`;
  $("#scoreExplanation").textContent = result.score_explanation || "风险高不等于申诉胜率高。";
  $("#riskHeadline").textContent = result.dispute_type || "纠纷风险评估";
  $("#judgementText").textContent = judgementLabel(result.judgement_direction);
  $("#actionBadge").className = `action-badge ${badge.tone}`;
  $("#actionBadge").textContent = badge.text;
  $("#summaryText").textContent = result.dispute_summary || "未识别到足够证据形成纠纷总结。";
  $("#keyEvidenceList").innerHTML = listMarkup(result.evidence_order, "暂无证据链摘要。");
  $("#reasonList").innerHTML = listMarkup(result.risk_reasons, "未识别到直接风险原因。");
  $("#gapList").innerHTML = listMarkup(result.evidence_gaps, "当前证据链暂未发现明显缺口。");
  $("#appealText").textContent = result.appeal_text || "";
  renderStructuredEvidence(result.structured_evidence);
}

function renderStructuredEvidence(structured) {
  const target = $("#structuredEvidence");
  if (!structured) {
    target.innerHTML = '<p class="muted">等待证据结构化。</p>';
    return;
  }
  const rows = [
    ["订单状态", structured.order_status || "-"],
    ["物流状态", structured.logistics_status || "-"],
    ["买家主张", (structured.user_claims || []).join("；") || "-"],
    ["商家动作", (structured.seller_actions || []).join("；") || "-"],
    ["时间节点", (structured.timestamps || []).join("；") || "-"],
  ];
  target.innerHTML = rows.map(([label, value]) => `
    <article>
      <span>${escapeHtml(label)}</span>
      <p>${escapeHtml(value)}</p>
    </article>
  `).join("");
}

function renderOcrAudit(ocrResult) {
  const target = $("#ocrAudit");
  if (!ocrResult) {
    target.innerHTML = '<p class="muted">等待 OCR 解析。</p>';
    return;
  }
  const images = ocrResult.images || [];
  const totalBlocks = images.reduce((sum, item) => sum + Number(item.block_count || item.blocks?.length || 0), 0);
  const warnings = ocrResult.warnings || [];
  target.innerHTML = `
    <div class="ocr-meta">
      <span class="case-status ${ocrResult.real_ocr ? "done" : "processing"}">${ocrResult.real_ocr ? "真实 OCR" : "演示兜底"}</span>
      <strong>${escapeHtml(ocrResult.provider || "unknown")}</strong>
      <small>${images.length} 张图片 · ${totalBlocks} 个文本块 · ${Number(ocrResult.duration_ms || 0)} ms</small>
    </div>
    ${warnings.length ? `<div class="ocr-warning">${warnings.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
    <div class="ocr-image-list">
      ${images.map((item) => `
        <article>
          <div class="ocr-image-head">
            <strong>${escapeHtml(item.filename || "未命名图片")}</strong>
            <span>${Number(item.block_count || item.blocks?.length || 0)} blocks</span>
          </div>
          <pre>${escapeHtml(item.text || "暂无 OCR 文本。")}</pre>
        </article>
      `).join("") || '<p class="muted">暂无 OCR 图片结果。</p>'}
    </div>
  `;
}

function renderTrace(item) {
  const steps = item?.trace?.steps || [];
  $("#traceFeed").innerHTML = steps.map((step) => `
    <article class="${escapeHtml(step.status)}">
      <time>${formatTime(step.timestamp)}</time>
      <strong>${step.status === "success" ? "OK" : "!"} ${escapeHtml(step.step)}</strong>
      <p>${escapeHtml(step.output || "")}</p>
      <small>${Number(step.duration_ms || 0)} ms${step.confidence !== undefined ? ` · confidence ${Number(step.confidence)}%` : ""}</small>
    </article>
  `).join("") || '<p class="muted">暂无 AI 分析过程。</p>';
}

function logMessage(item) {
  if (item.type === "user") return item.action;
  if (item.type === "ai") return item.reasoning || item.model_output || "AI推理日志";
  if (item.type === "observability") return `${item.name || item.node_id || "观测事件"} · ${item.status || "-"} · ${item.external_delivery || "local"}`;
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
  try {
    const [user, system, ai, observability] = await Promise.all([
      fetchJson(`/logs/user?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
      fetchJson(`/logs/system?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
      fetchJson(`/logs/ai?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
      fetchJson(`/logs/observability?case_id=${encodeURIComponent(caseId)}&limit=20`, { headers }),
    ]);
    const logs = [...(user.logs || []), ...(system.logs || []), ...(ai.logs || []), ...(observability.logs || [])]
      .sort((a, b) => Number(b.timestamp || 0) - Number(a.timestamp || 0));
    renderMiniLogs(logs);
    return logs;
  } catch (error) {
    renderMiniLogs([]);
    return [];
  }
}

async function selectCase(caseId) {
  const inlineCase = state.cases.find((item) => item.id === caseId && String(item.id).startsWith("INLINE-"));
  if (inlineCase) {
    state.currentCase = inlineCase;
    renderCurrentCase(state.currentCase);
    renderResult(state.currentCase.raw_result);
    renderOcrAudit(state.currentCase.ocr_result || state.currentCase.raw_result?.ocr_result);
    renderTrace(state.currentCase);
    renderMiniLogs([]);
    renderCaseList();
    setStatus(statusLabel(state.currentCase.status), statusTone(state.currentCase.status));
    return;
  }
  const payload = await fetchJson(`/case/${encodeURIComponent(caseId)}`);
  state.currentCase = payload.case;
  renderCurrentCase(state.currentCase);
  renderResult(state.currentCase.raw_result);
  renderOcrAudit(state.currentCase.ocr_result || state.currentCase.raw_result?.ocr_result);
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
      if (!["queued", "processing", "retrying"].includes(state.currentCase?.status)) {
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
    try {
      const payload = await fetchJson("/case/analyze", { method: "POST", body: formData });
      state.currentCase = payload.case;
      renderCurrentCase(state.currentCase);
      renderResult(null);
      renderOcrAudit(null);
      renderTrace(state.currentCase);
      await loadCases();
      await loadCaseLogs(state.currentCase.id);
      setStatus("分析中", "working");
      showToast(`已创建 ${state.currentCase.id}，开始后台分析。`);
      startPolling(state.currentCase.id);
    } catch (caseError) {
      const fallbackForm = new FormData();
      state.files.forEach((file) => fallbackForm.append("images", file));
      const payload = await fetchJson("/api/analyze", { method: "POST", body: fallbackForm });
      state.currentCase = buildInlineCase(payload);
      state.cases = [state.currentCase, ...state.cases.filter((item) => item.id !== state.currentCase.id)];
      renderCurrentCase(state.currentCase);
      renderResult(payload);
      renderOcrAudit(payload.ocr_result);
      renderTrace(state.currentCase);
      renderMiniLogs([]);
      renderCaseList();
      setStatus("完成", "ready");
      showToast("已完成单次分析。当前环境未启用完整 Case 后端。");
    }
  } catch (error) {
    setStatus("分析失败", "failed");
    $("#formError").textContent = error.message;
    showToast(error.message);
  } finally {
    $("#analyzeBtn").disabled = state.files.length < 1;
  }
}

async function retryCase(caseId) {
  if (!caseId) return;
  clearInterval(state.pollTimer);
  setStatus("重试中", "working");
  try {
    const payload = await fetchJson("/case/retry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId }),
    });
    state.currentCase = payload.case;
    renderCurrentCase(state.currentCase);
    renderTrace(state.currentCase);
    renderOcrAudit(state.currentCase.ocr_result);
    await loadCaseLogs(caseId);
    showToast(`已重新提交 ${caseId} 的分析任务。`);
    startPolling(caseId);
  } catch (error) {
    setStatus("重试失败", "failed");
    showToast(error.message);
  }
}

function buildInlineCase(result) {
  const timestamp = Date.now();
  const caseId = result.case_id || `INLINE-${timestamp}`;
  return {
    id: caseId,
    created_at: timestamp,
    updated_at: timestamp,
    status: "done",
    files: state.files.map((file) => ({ name: file.name, type: file.type, size: file.size, url: "" })),
    ocr_result: result.ocr_result || null,
    raw_result: result,
    result: {
      judgment: judgementLabel(result.judgement_direction),
      score: Number(result.appeal_win_score || result.risk_score || 0),
      reasoning: result.score_explanation || result.judgement_reason || "",
      key_evidence: result.evidence_order || result.risk_reasons || [],
    },
    trace: {
      case_id: caseId,
      steps: [
        {
          step: "OCR解析",
          status: "success",
          duration_ms: Number(result.ocr_result?.duration_ms || 1),
          output: result.ocr_result?.summary || "OCR 解析完成。",
          timestamp,
        },
        {
          step: "最终判断",
          status: "success",
          duration_ms: 1,
          output: result.judgement_reason || result.recommendation || "最终判断已生成。",
          confidence: Number(result.appeal_win_score || 0),
          timestamp,
        },
      ],
    },
  };
}

async function loadAdminLogs() {
  const caseId = $("#logCaseFilter").value.trim();
  const type = $("#logTypeFilter").value;
  const types = type === "all" ? ["user", "system", "ai", "observability"] : [type];
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
  showToast("复制成功，可直接前往平台粘贴。");
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
  history.replaceState(null, "", appUrl("/"));
}

async function showLogs() {
  $("#workspaceView").hidden = true;
  $("#logsView").hidden = false;
  $("#workspaceNav").classList.remove("active");
  $("#logsNav").classList.add("active");
  history.replaceState(null, "", appUrl("/admin/logs"));
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
  $("#caseSearchInput").addEventListener("input", renderCaseList);
  $("#caseStatusTabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-case-filter]");
    if (!button) return;
    state.caseFilter = button.dataset.caseFilter;
    $("#caseStatusTabs").querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    renderCaseList();
  });
  document.querySelectorAll("[data-result-tab]").forEach((button) => {
    button.addEventListener("click", () => setResultTab(button.dataset.resultTab));
  });
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
  $("#currentCase").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-retry-case]");
    if (button) await retryCase(button.dataset.retryCase);
  });
  $("#fileTagFlow").addEventListener("click", (event) => {
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
  renderOcrAudit(null);
  renderTrace(null);
  renderMiniLogs([]);
  await loadCases();
  if (location.pathname === appUrl("/admin/logs")) await showLogs();
}

init().catch((error) => showToast(error.message));
