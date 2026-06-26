const $ = (selector) => document.querySelector(selector);

const state = { files: [], result: null, progressTimer: null, activeStep: 0 };

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
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

function setProgress(index) {
  state.activeStep = index;
  document.querySelectorAll(".pipeline-step").forEach((step, stepIndex) => {
    const marker = step.querySelector("span");
    step.classList.toggle("active", stepIndex === index);
    step.classList.toggle("done", stepIndex < index);
    marker.textContent = stepIndex < index ? "[✓]" : stepIndex === index ? "[→]" : "[ ]";
  });
  $("#progressBar").style.width = `${Math.min(((index + 1) / 4) * 100, 100)}%`;
}

function startProgress() {
  $("#uploadPanel").hidden = true;
  $("#loadingPanel").hidden = false;
  $("#resultPanel").hidden = true;
  setStatus("分析中", "working");
  setProgress(0);
  clearInterval(state.progressTimer);
  state.progressTimer = setInterval(() => setProgress(Math.min(state.activeStep + 1, 3)), 1200);
}

function stopProgress() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
  setProgress(3);
  $("#loadingPanel").hidden = true;
}

async function analyzeEvidence() {
  if (!state.files.length) return;
  const formData = new FormData();
  state.files.forEach((file) => formData.append("images", file));
  $("#analyzeBtn").disabled = true;
  startProgress();
  try {
    const response = await fetch("/api/analyze", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "分析失败，请稍后重试。");
    state.result = payload;
    stopProgress();
    renderResult(payload);
    $("#resultPanel").hidden = false;
    setStatus("报告已生成", "ready");
    showToast(payload.demo_mode ? "演示报告已生成，可测试完整流程。" : "申诉包已生成。");
  } catch (error) {
    stopProgress();
    $("#uploadPanel").hidden = false;
    setStatus("分析失败", "failed");
    $("#formError").textContent = error.message;
    showToast(error.message);
  } finally {
    $("#analyzeBtn").disabled = state.files.length < 1;
  }
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
  }[value] || "等待判断";
}

function listMarkup(items, emptyText) {
  const values = (items || []).filter(Boolean);
  if (!values.length) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return values.map((item) => `<p>${escapeHtml(item)}</p>`).join("");
}

function renderCompleteness(completeness = {}) {
  const checks = [
    ["订单证据", completeness.order_evidence],
    ["物流证据", completeness.logistics_evidence],
    ["聊天证据", completeness.chat_evidence],
    ["商品规格证据", completeness.product_spec_evidence],
    ["退款流程证据", completeness.refund_process_evidence],
  ];
  $("#completenessScore").textContent = `${Number(completeness.overall_score ?? 0)}%`;
  $("#completenessSummary").textContent = completeness.summary || "暂无证据完整度结论。";
  $("#completenessList").innerHTML = checks.map(([label, passed]) => `
    <article class="${passed ? "passed" : "missing"}"><span>${passed ? "已覆盖" : "待补齐"}</span><strong>${escapeHtml(label)}</strong></article>
  `).join("");
}

function renderWeightRules(rules = []) {
  $("#weightRuleList").innerHTML = (rules || []).map((item) => `
    <article class="${item.present ? "present" : "missing"}">
      <div><span>权重 ${Number(item.weight ?? 0)}%</span><strong>${escapeHtml(item.evidence_type || "证据项")}</strong></div>
      <p>${escapeHtml(item.reason || "")}</p>
    </article>
  `).join("") || '<p class="muted">暂未生成证据权重规则。</p>';
}

function conflictLevelLabel(level) {
  return { high: "高冲突", medium: "中冲突", low: "低冲突", none: "无冲突" }[level] || "待判断";
}

function renderConflicts(conflicts = [], summary = "") {
  $("#conflictSummary").textContent = summary || "暂未发现明确冲突。";
  $("#conflictList").innerHTML = (conflicts || []).map((item) => `
    <article class="${escapeHtml(item.conflict_level || "none")}">
      <span>${escapeHtml(conflictLevelLabel(item.conflict_level))}</span>
      <strong>${escapeHtml(item.claim || "用户主张待补")}</strong>
      <p>客观凭证：${escapeHtml(item.objective_evidence || "待补")}</p>
      <p>${escapeHtml(item.conclusion || "")}</p>
    </article>
  `).join("") || '<p class="muted">暂无冲突检测结果。</p>';
}

function prefixForTimeline(item) {
  const text = `${item.event || ""} ${item.evidence || ""}`.toLowerCase();
  if (/订单|下单|order|payment/.test(text)) return "订单";
  if (/物流|签收|发货|快递|异常|tracking/.test(text)) return "物流";
  if (/聊天|买家|用户|投诉|退款|差评/.test(text)) return "聊天";
  if (/sku|规格|商品|实物/.test(text)) return "商品";
  return "证据";
}

function renderResult(result) {
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
  renderCompleteness(result.evidence_completeness || {});
  $("#summaryText").textContent = result.dispute_summary || "未识别到足够证据形成纠纷总结。";
  $("#reasonList").innerHTML = listMarkup(result.risk_reasons, "未识别到直接风险原因。");
  $("#gapList").innerHTML = listMarkup(result.evidence_gaps, "当前证据链暂未发现明显缺口。");
  $("#strategyText").textContent = result.suggested_strategy || result.malicious_likelihood || "建议先补齐关键凭证后再提交。";
  $("#appealText").textContent = result.appeal_text || "";
  $("#timeline").innerHTML = (result.timeline || []).map((item) => `
    <article><time>${escapeHtml(item.time || "时间待补")}</time><p><span>[${prefixForTimeline(item)}]</span> ${escapeHtml(item.event || "事件待补")}</p><small>${escapeHtml(item.evidence || "")}</small></article>
  `).join("") || '<p class="muted">暂未重建出有效时间线节点。</p>';
  renderWeightRules(result.evidence_weight_rules || []);
  renderConflicts(result.conflict_checks || [], result.conflict_summary || "");
  const structured = result.structured_evidence || {};
  const blocks = [
    ["订单", structured.order_status || "未识别"],
    ["物流", structured.logistics_status || "未识别"],
    ["用户主张", (structured.user_claims || []).join(" / ") || "未识别"],
    ["商家动作", (structured.seller_actions || []).join(" / ") || "未识别"],
    ["时间戳", (structured.timestamps || []).join(" / ") || "未识别"],
  ];
  $("#structuredGrid").innerHTML = blocks.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><p>${escapeHtml(value)}</p></article>`).join("");
}

async function copyAppeal() {
  const text = $("#appealText").textContent.trim();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast("申诉文本已复制。");
}

function resetAll() {
  state.files = [];
  state.result = null;
  stopProgress();
  $("#uploadPanel").hidden = false;
  $("#resultPanel").hidden = true;
  $("#fileInput").value = "";
  $("#progressBar").style.width = "0%";
  setStatus("等待上传");
  updateUploadState();
}

function bindEvents() {
  $("#fileInput").addEventListener("change", (event) => addFiles(event.target.files));
  $("#analyzeBtn").addEventListener("click", analyzeEvidence);
  $("#copyAppealBtn").addEventListener("click", copyAppeal);
  $("#resetBtn").addEventListener("click", resetAll);
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

bindEvents();
updateUploadState();
